from __future__ import annotations

import hashlib
import heapq
import html
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator
from urllib.parse import parse_qs, unquote, urlparse

_DIRECT_URL_PATTERN = re.compile(rb"https?://[A-Za-z0-9:/?.&=+%_~#;,@!\-*()]+")
_ENCODED_URL_PATTERN = re.compile(rb"https%3A%2F%2F[A-Za-z0-9%._~#;,@!\-*()+]+", re.IGNORECASE)
_SKIP_DIRECTORIES = {
    "video",
    "filestorage",
    "avatar",
    "image",
    "attachment",
    "music",
    "emoji",
    "crashpad",
    "gpucache",
}
_MAX_SCAN_FILE_BYTES = 64 * 1024 * 1024
_MAX_URL_BYTES = 16 * 1024
_ALLOWED_FIELDS = (
    "biz",
    "uin",
    "key",
    "pass_ticket",
    "appmsg_token",
    "poc_sid",
    "poc_token",
    "mid",
    "idx",
    "sessionid",
)


@dataclass(slots=True, repr=False)
class CaptureCandidate:
    request_url: str
    fields: dict[str, str]
    modified_at: float
    source_root: str

    def safe_summary(self) -> dict[str, object]:
        fingerprint_material = "|".join(self.fields.get(name, "") for name in _ALLOWED_FIELDS)
        return {
            "field_names": sorted(self.fields),
            "modified_at": self.modified_at,
            "source_root": self.source_root,
            "candidate_fingerprint": hashlib.sha256(fingerprint_material.encode("utf-8")).hexdigest()[:16],
        }

    def __repr__(self) -> str:
        return f"CaptureCandidate({self.safe_summary()!r})"


@dataclass(slots=True, repr=False)
class ScanReport:
    scanned_files: int
    scanned_bytes: int
    roots: list[str]
    candidates: list[CaptureCandidate]
    duration_seconds: float
    truncated: bool
    truncation_reasons: list[str]

    def safe_summary(self) -> dict[str, object]:
        return {
            "scanned_files": self.scanned_files,
            "scanned_bytes": self.scanned_bytes,
            "roots": self.roots,
            "candidate_count": len(self.candidates),
            "candidates": [candidate.safe_summary() for candidate in self.candidates],
            "duration_seconds": self.duration_seconds,
            "truncated": self.truncated,
            "truncation_reasons": list(self.truncation_reasons),
            "sensitive_values_returned": False,
        }

    def __repr__(self) -> str:
        return f"ScanReport({self.safe_summary()!r})"


def _root_label(path: Path) -> str:
    normalized = str(path).replace("\\", "/")
    marker = "/.xwechat/radium/web"
    if normalized.endswith(marker) or normalized == ".xwechat/radium/web":
        return ".xwechat/radium/web"
    if marker + "/" in normalized:
        return ".xwechat/radium/web"
    return path.name or "<root>"


def _urls_in_file(path: Path) -> Iterator[str]:
    overlap = b""
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                data = overlap + chunk
                seen: set[bytes] = set()
                for pattern in (_DIRECT_URL_PATTERN, _ENCODED_URL_PATTERN):
                    for match in pattern.finditer(data):
                        raw = match.group()
                        if raw in seen or len(raw) > _MAX_URL_BYTES:
                            continue
                        seen.add(raw)
                        yield raw.decode("ascii", errors="ignore")
                overlap = data[-_MAX_URL_BYTES:]
    except OSError:
        return


def _candidate_from_url(
    raw_url: str,
    target_biz: str | None,
    modified_at: float,
    root_label: str,
) -> CaptureCandidate | None:
    value = html.unescape(raw_url)
    for _ in range(3):
        decoded = unquote(value)
        if decoded == value:
            break
        value = decoded

    parsed = urlparse(value)
    if (parsed.hostname or "").lower() != "mp.weixin.qq.com":
        return None
    if parsed.path not in {"/mp/profile_ext", "/mp/relatedsearchword"}:
        return None

    query = parse_qs(parsed.query, keep_blank_values=True)
    biz = (query.get("__biz") or [""])[0]
    if not biz:
        return None
    if target_biz is not None and biz != target_biz:
        return None

    fields: dict[str, str] = {"biz": biz}
    for name in (
        "uin",
        "key",
        "pass_ticket",
        "appmsg_token",
        "poc_sid",
        "poc_token",
        "mid",
        "idx",
        "sessionid",
    ):
        values = query.get(name)
        if values and values[0]:
            fields[name] = values[0]

    if parsed.path == "/mp/relatedsearchword":
        required = ("biz", "uin", "key", "pass_ticket", "appmsg_token", "mid", "idx", "sessionid")
        if not all(fields.get(name) for name in required):
            return None
    else:
        legacy_ready = all(fields.get(name) for name in ("uin", "key", "pass_ticket"))
        token_ready = all(fields.get(name) for name in ("appmsg_token", "pass_ticket"))
        if not (legacy_ready or token_ready):
            return None

    return CaptureCandidate(
        request_url=value,
        fields=fields,
        modified_at=modified_at,
        source_root=root_label,
    )


def _recent_files(
    roots: list[Path],
    cutoff: float,
    max_files: int,
    *,
    max_directories: int,
    deadline: float,
) -> tuple[list[tuple[float, int, Path, str]], list[str]]:
    newest: list[tuple[float, int, str, Path, str]] = []
    reasons: list[str] = []
    directory_count = 0

    for root in roots:
        if not root.exists():
            continue
        label = _root_label(root)
        stack = [root]
        while stack:
            if time.monotonic() > deadline:
                reasons.append("enumeration_time_budget")
                stack.clear()
                break
            if directory_count >= max_directories:
                reasons.append("directory_budget")
                stack.clear()
                break
            directory = stack.pop()
            directory_count += 1
            try:
                entries = list(os.scandir(directory))
            except OSError:
                continue
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name.casefold() not in _SKIP_DIRECTORIES:
                            stack.append(Path(entry.path))
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    stat = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                if stat.st_mtime < cutoff or stat.st_size <= 0 or stat.st_size > _MAX_SCAN_FILE_BYTES:
                    continue
                path = Path(entry.path)
                item = (stat.st_mtime, stat.st_size, str(path), path, label)
                if len(newest) < max_files:
                    heapq.heappush(newest, item)
                elif item[:3] > newest[0][:3]:
                    heapq.heapreplace(newest, item)

    if len(newest) >= max_files:
        reasons.append("file_count_budget")
    rows = [
        (mtime, size, path, label)
        for mtime, size, _name, path, label in sorted(newest, reverse=True)
    ]
    return rows, reasons


def scan_credentials(
    target_biz: str | None,
    *,
    roots: list[Path],
    since_minutes: int = 60,
    max_files: int = 5000,
    max_total_bytes: int = 512 * 1024 * 1024,
    max_directories: int = 20_000,
    max_scan_seconds: float = 20.0,
) -> ScanReport:
    if target_biz is not None and (not target_biz or len(target_biz) > 256):
        raise ValueError("invalid_target_biz")
    if not 1 <= since_minutes <= 1440:
        raise ValueError("since_minutes_out_of_range")
    if max_files < 1:
        raise ValueError("max_files_out_of_range")
    if max_total_bytes < 1:
        raise ValueError("max_total_bytes_out_of_range")
    if max_directories < 1:
        raise ValueError("max_directories_out_of_range")
    if max_scan_seconds <= 0:
        raise ValueError("max_scan_seconds_out_of_range")

    started = time.monotonic()
    deadline = started + max_scan_seconds
    cutoff = time.time() - since_minutes * 60
    selected_roots = [Path(root) for root in roots]
    recent, reasons = _recent_files(
        selected_roots,
        cutoff,
        max_files,
        max_directories=max_directories,
        deadline=deadline,
    )

    scanned_files = 0
    scanned_bytes = 0
    candidates_by_identity: dict[tuple[str, ...], CaptureCandidate] = {}

    for modified_at, size, path, root_label in recent:
        if time.monotonic() > deadline:
            reasons.append("scan_time_budget")
            break
        if scanned_bytes + size > max_total_bytes:
            reasons.append("total_byte_budget")
            break
        scanned_files += 1
        scanned_bytes += size
        for request_url in _urls_in_file(path):
            candidate = _candidate_from_url(request_url, target_biz, modified_at, root_label)
            if candidate is None:
                continue
            identity = tuple(candidate.fields.get(name, "") for name in _ALLOWED_FIELDS)
            current = candidates_by_identity.get(identity)
            if current is None or candidate.modified_at > current.modified_at:
                candidates_by_identity[identity] = candidate

    candidates = sorted(candidates_by_identity.values(), key=lambda item: item.modified_at, reverse=True)
    unique_reasons = sorted(set(reasons))
    return ScanReport(
        scanned_files=scanned_files,
        scanned_bytes=scanned_bytes,
        roots=[_root_label(root) for root in selected_roots],
        candidates=candidates,
        duration_seconds=round(time.monotonic() - started, 3),
        truncated=bool(unique_reasons),
        truncation_reasons=unique_reasons,
    )
