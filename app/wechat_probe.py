from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from app.runtime import is_runtime_metadata

_ACCOUNT_SEGMENT = re.compile(r"^(?:wxid_|gh_)[A-Za-z0-9_-]+$", re.IGNORECASE)
_DB_SUFFIXES = {".db", ".sqlite", ".sqlite3"}
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
    "webview",
    "cef",
    "chromium",
}


def _looks_sensitive_segment(segment: str) -> bool:
    if _ACCOUNT_SEGMENT.match(segment):
        return True
    compact = segment.replace("-", "").replace("_", "")
    return len(compact) >= 24 and compact.isalnum()


def _sanitize_segment(segment: str) -> str:
    if segment in _KNOWN_PATH_SEGMENTS and not _looks_sensitive_segment(segment):
        return segment
    return "<redacted>"


def sanitize_relative_root(path: Path, state_dir: Path) -> str:
    try:
        relative = path.relative_to(state_dir)
    except ValueError:
        return "<outside-state>"

    parent_parts = list(relative.parent.parts[:3])
    sanitized = [_sanitize_segment(part) for part in parent_parts]
    return "/".join(sanitized) if sanitized else "."


def classify_artifact(path: Path, state_dir: Path) -> str | None:
    try:
        relative = path.relative_to(state_dir)
    except ValueError:
        return None

    parts = [part.lower() for part in relative.parts]
    filename = path.name.lower()
    relative_text = "/".join(parts)

    if "mp.weixin.qq.com" in relative_text:
        return "mp_weixin_trace"

    if filename in {"cookies", "cookies-journal"} or filename.startswith("cookie"):
        return "cookie_store"

    if "xwechat_files" in parts and path.suffix.lower() in _DB_SUFFIXES:
        return "xwechat_db"

    if any(
        marker in parts
        for marker in {"webview", "cef", "chromium", "cache", "code cache", "gpucache", "user data"}
    ):
        return "webview_cache"

    if path.suffix.lower() in _DB_SUFFIXES:
        return "other_candidate"

    return None


def probe_state(state_dir: Path) -> dict[str, object]:
    grouped: dict[str, dict[str, object]] = defaultdict(lambda: {"count": 0, "roots": set()})
    state_initialized = False

    if state_dir.exists():
        for path in state_dir.rglob("*"):
            if not path.is_file():
                continue
            if not is_runtime_metadata(path):
                state_initialized = True
            artifact_class = classify_artifact(path, state_dir)
            if artifact_class is None:
                continue
            entry = grouped[artifact_class]
            entry["count"] = int(entry["count"]) + 1
            roots = entry["roots"]
            assert isinstance(roots, set)
            roots.add(sanitize_relative_root(path, state_dir))

    artifact_classes = []
    for artifact_class in sorted(grouped):
        entry = grouped[artifact_class]
        roots = entry["roots"]
        assert isinstance(roots, set)
        artifact_classes.append(
            {
                "class": artifact_class,
                "count": int(entry["count"]),
                "relative_roots": sorted(roots),
                "candidate": True,
            }
        )

    return {
        "state_initialized": state_initialized,
        "artifact_classes": artifact_classes,
        "sensitive_values_returned": False,
    }
