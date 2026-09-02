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


def locate_history_seed(history_db: Path) -> HistorySeed | None:
    if not history_db.is_file():
        return None

    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(f"file:{history_db}?mode=ro", uri=True)
        rows = connection.execute(
            "SELECT url, title, last_visit_time FROM urls "
            "WHERE url LIKE 'https://mp.weixin.qq.com/%' "
            "ORDER BY last_visit_time DESC LIMIT 100"
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
        return HistorySeed(
            _raw_url=value,
            title=str(title or ""),
            last_visit_time=int(last_visit_time or 0),
        )
    return None
