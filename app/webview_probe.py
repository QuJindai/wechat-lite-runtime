from __future__ import annotations

import os
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

FIXED_MARKERS: tuple[bytes, ...] = (
    b"mp.weixin.qq.com",
    b"__biz",
    b"pass_ticket",
    b"appmsg_token",
)

_PROFILE_ID_RE = re.compile(r"^(multitab_).+$", re.IGNORECASE)
_KNOWN_PATH_SEGMENTS = {
    ".xwechat",
    "radium",
    "web",
    "profiles",
    "web_shell",
    "Network",
    "Local Storage",
    "leveldb",
    "Cache",
    "Code Cache",
    "GPUCache",
    "History",
    "Cookies",
    "xwechat_files",
    "Msg",
    "User Data",
    "Default",
}
_KNOWN_TABLES = {"cookies", "urls", "visits", "meta"}
_KNOWN_COLUMNS = {
    "host_key",
    "name",
    "encrypted_value",
    "expires_utc",
    "url",
    "title",
    "last_visit_time",
}
MAX_SCAN_BYTES_PER_FILE = 32 * 1024 * 1024
MAX_SCHEMA_TABLES = 32
MAX_SCHEMA_COLUMNS = 64


@dataclass
class _ScanBudget:
    max_files: int
    max_total_bytes: int
    max_directories: int
    max_scan_seconds: float
    started_at: float = field(default_factory=time.monotonic)
    scanned_files: int = 0
    scanned_bytes: int = 0
    scanned_directories: int = 0
    reasons: set[str] = field(default_factory=set)
    stopped: bool = False

    def check_time(self) -> bool:
        if time.monotonic() - self.started_at <= self.max_scan_seconds:
            return True
        self.reasons.add("scan_time_budget")
        self.stopped = True
        return False

    def remaining_seconds(self) -> float:
        return max(0.0, self.max_scan_seconds - (time.monotonic() - self.started_at))

    def admit_directory(self) -> bool:
        if not self.check_time():
            return False
        if self.scanned_directories >= self.max_directories:
            self.reasons.add("directory_budget")
            self.stopped = True
            return False
        self.scanned_directories += 1
        return True

    def admit_file(self, path: Path) -> bool:
        if not self.check_time():
            return False
        if self.scanned_files >= self.max_files:
            self.reasons.add("file_count_budget")
            self.stopped = True
            return False
        try:
            size = max(0, int(path.stat().st_size))
        except OSError:
            size = 0
        admitted_bytes = min(size, MAX_SCAN_BYTES_PER_FILE)
        if size > MAX_SCAN_BYTES_PER_FILE:
            self.reasons.add("per_file_byte_budget")
        if self.scanned_bytes + admitted_bytes > self.max_total_bytes:
            self.reasons.add("total_byte_budget")
            self.stopped = True
            return False
        self.scanned_files += 1
        self.scanned_bytes += admitted_bytes
        return True


def _sanitize_segment(segment: str) -> str:
    match = _PROFILE_ID_RE.match(segment)
    if match:
        return f"{match.group(1)}<redacted>"
    if segment in _KNOWN_PATH_SEGMENTS:
        return segment
    return "<redacted>"


def _sanitize_relative(path: Path, state_dir: Path) -> str:
    try:
        relative = path.relative_to(state_dir)
    except ValueError:
        return "<outside-state>"
    return "/".join(_sanitize_segment(part) for part in relative.parts)


def classify_webview_container(path: Path, web_root: Path) -> str | None:
    try:
        path.relative_to(web_root)
    except ValueError:
        return None

    if path.parent.name == "profiles":
        return "profile_root"
    if path.name == "leveldb" and path.parent.name == "Local Storage":
        return "local_storage_leveldb"
    if path.name == "Cookies":
        return "cookie_sqlite"
    if path.name == "History":
        return "history_sqlite"
    if path.name in {"Cache", "Code Cache", "GPUCache"}:
        return "cache_store"
    return None


def _marker_counts_in_file(
    path: Path,
    needles: Sequence[bytes],
    *,
    budget: _ScanBudget | None = None,
) -> dict[str, int]:
    counts = {needle.decode("ascii"): 0 for needle in needles}
    try:
        size = path.stat().st_size
    except OSError:
        return counts
    if size <= 0:
        return counts

    remaining = min(size, MAX_SCAN_BYTES_PER_FILE)
    tails = {needle: b"" for needle in needles}
    try:
        with path.open("rb") as handle:
            while remaining > 0:
                if budget is not None and not budget.check_time():
                    break
                chunk = handle.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                for needle in needles:
                    data = tails[needle] + chunk
                    counts[needle.decode("ascii")] += data.count(needle)
                    overlap = max(len(needle) - 1, 0)
                    tails[needle] = data[-overlap:] if overlap else b""
    except OSError:
        return counts
    return counts


def _file_marker_counts(path: Path, *, budget: _ScanBudget | None = None) -> dict[str, int]:
    return _marker_counts_in_file(path, FIXED_MARKERS, budget=budget)


def scan_fixed_markers(path: Path, needles: Sequence[bytes] = FIXED_MARKERS) -> dict[str, int]:
    result = {needle.decode("ascii"): 0 for needle in needles}
    if path.is_file():
        for key, value in _marker_counts_in_file(path, needles).items():
            result[key] += value
    elif path.is_dir():
        for directory, _subdirectories, filenames in os.walk(path):
            for filename in filenames:
                counts = _marker_counts_in_file(Path(directory) / filename, needles)
                for key, value in counts.items():
                    result[key] += value
    return result


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _safe_identifier(value: str, allowed: set[str], label: str, position: int) -> str:
    return value if value in allowed else f"<redacted-{label}-{position}>"


def inspect_sqlite_schema(
    path: Path,
    *,
    budget: _ScanBudget | None = None,
) -> dict[str, object]:
    if budget is not None and not budget.check_time():
        return {"status": "budget_exhausted", "tables": []}
    if not path.is_file():
        return {"status": "not_sqlite", "tables": []}
    try:
        with path.open("rb") as handle:
            header = handle.read(16)
    except OSError:
        return {"status": "unreadable", "tables": []}
    if header != b"SQLite format 3\x00":
        return {"status": "not_sqlite", "tables": []}
    if budget is not None and not budget.check_time():
        return {"status": "budget_exhausted", "tables": []}

    uri = f"file:{path.as_posix()}?mode=ro"
    timeout = 0.2 if budget is None else max(0.001, min(0.2, budget.remaining_seconds()))
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=timeout)
    except sqlite3.OperationalError:
        return {"status": "locked", "tables": []}
    except sqlite3.DatabaseError:
        return {"status": "corrupt", "tables": []}

    if budget is not None:
        conn.set_progress_handler(lambda: 0 if budget.check_time() else 1, 100)

    tables: list[dict[str, object]] = []
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name LIMIT ?",
            (MAX_SCHEMA_TABLES,),
        ).fetchall()
        for table_position, (table_name,) in enumerate(rows, start=1):
            if budget is not None and not budget.check_time():
                return {"status": "budget_exhausted", "tables": tables}
            raw_table = str(table_name)
            columns = conn.execute(
                f"PRAGMA table_info({_quote_identifier(raw_table)})"
            ).fetchall()
            safe_columns = [
                _safe_identifier(str(row[1]), _KNOWN_COLUMNS, "column", column_position)
                for column_position, row in enumerate(columns[:MAX_SCHEMA_COLUMNS], start=1)
            ]
            tables.append(
                {
                    "name": _safe_identifier(raw_table, _KNOWN_TABLES, "table", table_position),
                    "columns": safe_columns,
                }
            )
    except sqlite3.OperationalError:
        if budget is not None and budget.stopped:
            return {"status": "budget_exhausted", "tables": tables}
        return {"status": "locked", "tables": []}
    except sqlite3.DatabaseError:
        return {"status": "corrupt", "tables": []}
    finally:
        conn.close()
    return {"status": "ok", "tables": tables}


def _walk_tree(root: Path, budget: _ScanBudget) -> tuple[list[Path], list[Path]]:
    paths: list[Path] = []
    files: list[Path] = []
    pending = [root]
    while pending and not budget.stopped:
        current = pending.pop()
        if not budget.admit_directory():
            break
        paths.append(current)
        try:
            iterator = os.scandir(current)
        except OSError:
            continue
        with iterator:
            for entry in iterator:
                if not budget.check_time():
                    break
                candidate = Path(entry.path)
                try:
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(candidate)
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                if not budget.admit_file(candidate):
                    break
                paths.append(candidate)
                files.append(candidate)
    return paths, files


def _sum_markers(
    files: Sequence[Path],
    marker_counts: dict[Path, dict[str, int]],
    root: Path,
    *,
    budget: _ScanBudget | None = None,
) -> dict[str, int]:
    totals = {marker.decode("ascii"): 0 for marker in FIXED_MARKERS}
    for path in files:
        if budget is not None and not budget.check_time():
            break
        try:
            path.relative_to(root)
        except ValueError:
            continue
        for key, value in marker_counts.get(path, {}).items():
            totals[key] += value
    return totals


def _profile_label(name: str) -> str:
    if name.lower().startswith("multitab_"):
        return "multitab_<redacted>"
    if name == "web_shell":
        return name
    return "<redacted>"


def probe_webview_state(
    state_dir: Path,
    *,
    max_files: int = 5000,
    max_total_bytes: int = 512 * 1024 * 1024,
    max_directories: int = 20_000,
    max_scan_seconds: float = 3.0,
) -> dict[str, object]:
    if max_files < 1 or max_total_bytes < 1 or max_directories < 1 or max_scan_seconds <= 0:
        raise ValueError("invalid_scan_budget")
    state_dir = Path(state_dir)
    web_root = state_dir / ".xwechat" / "radium" / "web"
    zero_markers = {marker.decode("ascii"): 0 for marker in FIXED_MARKERS}
    if not web_root.is_dir():
        return {
            "web_root_present": False,
            "profiles": [],
            "marker_totals": zero_markers,
            "truncated": False,
            "truncation_reasons": [],
            "sensitive_values_returned": False,
        }

    budget = _ScanBudget(
        max_files=max_files,
        max_total_bytes=max_total_bytes,
        max_directories=max_directories,
        max_scan_seconds=max_scan_seconds,
        started_at=time.monotonic(),
    )
    profiles_root = web_root / "profiles"
    paths, files = _walk_tree(profiles_root, budget) if profiles_root.is_dir() else ([], [])
    file_markers: dict[Path, dict[str, int]] = {}
    for path in files:
        if not budget.check_time():
            break
        file_markers[path] = _file_marker_counts(path, budget=budget)

    file_set = set(files)
    profile_dirs: list[Path] = []
    for path in paths:
        if not budget.check_time():
            break
        if path.parent == profiles_root and path not in file_set:
            profile_dirs.append(path)
    profile_dirs.sort(key=lambda path: path.name)

    profile_by_name = {profile.name: profile for profile in profile_dirs}
    paths_by_profile = {profile: [] for profile in profile_dirs}
    files_by_profile = {profile: [] for profile in profile_dirs}
    for path in paths:
        if not budget.check_time():
            break
        try:
            relative = path.relative_to(profiles_root)
        except ValueError:
            continue
        if not relative.parts:
            continue
        profile = profile_by_name.get(relative.parts[0])
        if profile is None:
            continue
        paths_by_profile[profile].append(path)
        if path in file_set:
            files_by_profile[profile].append(path)

    profiles: list[dict[str, object]] = []
    marker_totals = dict(zero_markers)
    for profile in profile_dirs:
        if not budget.check_time():
            break
        profile_files = files_by_profile[profile]
        profile_markers = _sum_markers(
            profile_files,
            file_markers,
            profile,
            budget=budget,
        )
        for key, value in profile_markers.items():
            marker_totals[key] += value

        containers: list[dict[str, object]] = []
        candidates: list[Path] = []
        for path in paths_by_profile[profile]:
            if not budget.check_time():
                break
            if classify_webview_container(path, web_root):
                candidates.append(path)
        candidates.sort(key=lambda path: path.as_posix())

        contained_files: dict[Path, list[Path]] = {candidate: [] for candidate in candidates}
        candidate_set = set(candidates)
        for path in profile_files:
            if not budget.check_time():
                break
            current = path
            while True:
                if current in candidate_set:
                    contained_files[current].append(path)
                if current == profile or current.parent == current:
                    break
                current = current.parent

        for item in candidates:
            if not budget.check_time():
                break
            container_class = classify_webview_container(item, web_root)
            if container_class == "profile_root":
                continue
            item_files = contained_files[item]
            entry: dict[str, object] = {
                "class": container_class,
                "relative_path": _sanitize_relative(item, state_dir),
                "file_count": len(item_files),
                "marker_counts": _sum_markers(
                    item_files,
                    file_markers,
                    item,
                    budget=budget,
                ),
            }
            if container_class in {"cookie_sqlite", "history_sqlite"} and item in files:
                entry["sqlite_schema"] = inspect_sqlite_schema(item, budget=budget)
            containers.append(entry)

        profiles.append(
            {
                "profile": _profile_label(profile.name),
                "relative_root": _sanitize_relative(profile, state_dir),
                "containers": containers,
                "marker_counts": profile_markers,
            }
        )

    return {
        "web_root_present": True,
        "profiles": profiles,
        "marker_totals": marker_totals,
        "truncated": bool(budget.reasons),
        "truncation_reasons": sorted(budget.reasons),
        "sensitive_values_returned": False,
    }
