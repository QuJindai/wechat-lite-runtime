from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

_SAFE_QUERY_KEYS = ("__biz", "pass_ticket", "appmsg_token", "key", "uin")


@dataclass(frozen=True, repr=False)
class HistorySeed:
    _raw_url: str
    title: str
    last_visit_time: int

    def safe_summary(self) -> dict[str, object]:
        parsed = urlsplit(self._raw_url)
        query = parse_qs(parsed.query, keep_blank_values=True)
        return {
            "present": True,
            "host": parsed.hostname or "",
            "path": parsed.path,
            "query_keys_present": {key: key in query for key in _SAFE_QUERY_KEYS},
            "seed_fingerprint": hashlib.sha256(self._raw_url.encode("utf-8")).hexdigest()[:16],
        }

    def __repr__(self) -> str:
        return f"HistorySeed({self.safe_summary()!r})"


def _is_profile_ext_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname == "mp.weixin.qq.com"
        and parsed.path == "/mp/profile_ext"
    )


def _matches_target_biz(value: str, target_biz: str | None) -> bool:
    if target_biz is None:
        return True
    try:
        query = parse_qs(urlsplit(value).query, keep_blank_values=True)
    except ValueError:
        return False
    return (query.get("__biz") or [""])[0] == target_biz


def locate_history_seed(history_db: Path, target_biz: str | None = None) -> HistorySeed | None:
    if not history_db.is_file():
        return None

    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(f"file:{history_db}?mode=ro", uri=True)
        rows = connection.execute(
            "SELECT url, title, last_visit_time FROM urls "
            "WHERE url LIKE 'https://mp.weixin.qq.com/%' "
            "ORDER BY last_visit_time DESC LIMIT 500"
        ).fetchall()
    except (sqlite3.Error, OSError):
        return None
    finally:
        if connection is not None:
            connection.close()

    for raw_url, title, last_visit_time in rows:
        value = str(raw_url or "")
        if not _is_profile_ext_url(value):
            continue
        if not _matches_target_biz(value, target_biz):
            continue
        return HistorySeed(
            _raw_url=value,
            title=str(title or ""),
            last_visit_time=int(last_visit_time or 0),
        )
    return None


def locate_state_history_seeds(
    state_dir: Path,
    target_biz: str,
    *,
    max_candidates: int = 10,
) -> list[HistorySeed]:
    target = target_biz.strip()
    if not target or len(target) > 256 or any(char.isspace() for char in target):
        raise ValueError("invalid_target_biz")
    if max_candidates < 1:
        raise ValueError("max_candidates_out_of_range")

    profiles_root = Path(state_dir) / ".xwechat" / "radium" / "web" / "profiles"
    seeds: list[HistorySeed] = []
    if profiles_root.is_dir():
        for profile_dir in sorted(profiles_root.iterdir(), key=lambda path: path.name):
            if not profile_dir.is_dir():
                continue
            seed = locate_history_seed(profile_dir / "History", target)
            if seed is not None:
                seeds.append(seed)

    seeds.sort(key=lambda item: item.last_visit_time, reverse=True)
    return seeds[:max_candidates]


def _sanitize_profile_name(name: str) -> str:
    if name == "web_shell":
        return name
    if name == "multitab":
        return name
    if name.startswith("multitab_"):
        return "multitab_<redacted>"
    return "<redacted>"


def probe_history_seed_status(state_dir: Path) -> dict[str, object]:
    profiles_root = Path(state_dir) / ".xwechat" / "radium" / "web" / "profiles"
    candidates: list[tuple[HistorySeed, str, Path]] = []

    if profiles_root.is_dir():
        for profile_dir in sorted(profiles_root.iterdir(), key=lambda path: path.name):
            if not profile_dir.is_dir():
                continue
            history = profile_dir / "History"
            seed = locate_history_seed(history)
            if seed is None:
                continue
            candidates.append((seed, profile_dir.name, history))

    if not candidates:
        return {
            "present": False,
            "candidate_count": 0,
            "selected_profile": None,
            "selected_history": None,
            "seed": None,
            "sensitive_values_returned": False,
        }

    def ranking(item: tuple[HistorySeed, str, Path]) -> tuple[int, int]:
        seed, profile_name, _ = item
        multitab_priority = 1 if profile_name.startswith("multitab") else 0
        return seed.last_visit_time, multitab_priority

    seed, profile_name, _ = max(candidates, key=ranking)
    safe_profile = _sanitize_profile_name(profile_name)
    return {
        "present": True,
        "candidate_count": len(candidates),
        "selected_profile": safe_profile,
        "selected_history": f".xwechat/radium/web/profiles/{safe_profile}/History",
        "seed": seed.safe_summary(),
        "sensitive_values_returned": False,
    }
