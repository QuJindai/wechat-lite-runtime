from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Sequence

FIXED_MARKERS: tuple[bytes, ...] = (
    b"mp.weixin.qq.com",
    b"__biz",
    b"pass_ticket",
    b"appmsg_token",
)

_PROFILE_ID_RE = re.compile(r"^(multitab_).+$", re.IGNORECASE)
_HEX_ID_RE = re.compile(r"^[0-9a-fA-F]{16,}$")
MAX_SCAN_BYTES_PER_FILE = 32 * 1024 * 1024
MAX_SCHEMA_TABLES = 32
MAX_SCHEMA_COLUMNS = 64


def _sanitize_segment(segment: str) -> str:
    match = _PROFILE_ID_RE.match(segment)
    if match:
        return f"{match.group(1)}<redacted>"
    if _HEX_ID_RE.match(segment):
        return "<redacted>"
    return segment


def _sanitize_relative(path: Path, state_dir: Path) -> str:
    try:
        relative = path.relative_to(state_dir)
    except ValueError:
        relative = Path(path.name)
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


def _count_in_file(path: Path, needle: bytes) -> int:
    try:
        size = path.stat().st_size
    except OSError:
        return 0
    if size <= 0:
        return 0

    count = 0
    remaining = min(size, MAX_SCAN_BYTES_PER_FILE)
    overlap = max(len(needle) - 1, 0)
    tail = b""
    try:
        with path.open("rb") as handle:
            while remaining > 0:
                chunk = handle.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                data = tail + chunk
                count += data.count(needle)
                tail = data[-overlap:] if overlap else b""
    except OSError:
        return 0
    return count


def scan_fixed_markers(path: Path, needles: Sequence[bytes] = FIXED_MARKERS) -> dict[str, int]:
    result = {needle.decode("ascii"): 0 for needle in needles}
    if path.is_file():
        files = [path]
    elif path.is_dir():
        files = [candidate for candidate in path.rglob("*") if candidate.is_file()]
    else:
        files = []

    for candidate in files:
        for needle in needles:
            result[needle.decode("ascii")] += _count_in_file(candidate, needle)
    return result


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def inspect_sqlite_schema(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"status": "not_sqlite", "tables": []}

    try:
        with path.open("rb") as handle:
            header = handle.read(16)
    except OSError:
        return {"status": "unreadable", "tables": []}
    if header != b"SQLite format 3\x00":
        return {"status": "not_sqlite", "tables": []}

    uri = f"file:{path.as_posix()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=0.2)
    except sqlite3.OperationalError:
        return {"status": "locked", "tables": []}

    tables: list[dict[str, object]] = []
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name LIMIT ?",
            (MAX_SCHEMA_TABLES,),
        ).fetchall()
        for (table_name,) in rows:
            columns = conn.execute(
                f"PRAGMA table_info({_quote_identifier(str(table_name))})"
            ).fetchall()
            tables.append(
                {
                    "name": str(table_name),
                    "columns": [str(row[1]) for row in columns[:MAX_SCHEMA_COLUMNS]],
                }
            )
    except sqlite3.OperationalError:
        return {"status": "locked", "tables": []}
    finally:
        conn.close()
    return {"status": "ok", "tables": tables}


def _container_file_count(path: Path) -> int:
    if path.is_file():
        return 1
    if not path.is_dir():
        return 0
    return sum(1 for item in path.rglob("*") if item.is_file())


def _profile_label(name: str) -> str:
    if name.lower().startswith("multitab_"):
        return "multitab_<redacted>"
    if name == "web_shell":
        return name
    return "<redacted>"


def probe_webview_state(state_dir: Path) -> dict[str, object]:
    state_dir = Path(state_dir)
    web_root = state_dir / ".xwechat" / "radium" / "web"
    zero_markers = {marker.decode("ascii"): 0 for marker in FIXED_MARKERS}
    if not web_root.is_dir():
        return {
            "web_root_present": False,
            "profiles": [],
            "marker_totals": zero_markers,
            "sensitive_values_returned": False,
        }

    profiles_root = web_root / "profiles"
    profile_dirs = []
    if profiles_root.is_dir():
        profile_dirs = sorted(
            [item for item in profiles_root.iterdir() if item.is_dir()],
            key=lambda item: item.name,
        )

    profiles: list[dict[str, object]] = []
    marker_totals = dict(zero_markers)
    for profile in profile_dirs:
        profile_markers = scan_fixed_markers(profile)
        for key, value in profile_markers.items():
            marker_totals[key] += value

        containers: list[dict[str, object]] = []
        candidates = [item for item in profile.rglob("*") if classify_webview_container(item, web_root)]
        for item in sorted(candidates, key=lambda candidate: candidate.as_posix()):
            container_class = classify_webview_container(item, web_root)
            if container_class == "profile_root":
                continue
            entry: dict[str, object] = {
                "class": container_class,
                "relative_path": _sanitize_relative(item, state_dir),
                "file_count": _container_file_count(item),
                "marker_counts": scan_fixed_markers(item),
            }
            if container_class in {"cookie_sqlite", "history_sqlite"}:
                entry["sqlite_schema"] = inspect_sqlite_schema(item)
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
        "sensitive_values_returned": False,
    }
