from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Mapping, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

CHINA_TZ = timezone(timedelta(hours=8))
_PUBLIC_IDENTITY_PARAMS = ("__biz", "mid", "idx", "sn", "chksm")
_SENSITIVE_QUERY_KEYS = {
    "key",
    "pass_ticket",
    "uin",
    "token",
    "auth",
    "authorization",
    "cookie",
    "session",
    "sessionid",
    "scene",
}


@dataclass(frozen=True)
class ArticleRecord:
    account_name: str
    biz: str | None
    title: str
    canonical_url: str
    published_at: datetime | None
    position: int
    observed_at: datetime
    source: str = "authenticated_wechat"
    verified_account: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "account_name": self.account_name,
            "biz": self.biz,
            "title": self.title,
            "canonical_url": self.canonical_url,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "position": self.position,
            "observed_at": self.observed_at.isoformat(),
            "source": self.source,
            "verified_account": self.verified_account,
        }


@dataclass(frozen=True)
class DiscoveryResult:
    requested_count: int
    articles: tuple[ArticleRecord, ...]
    count_satisfied: bool
    timestamps_complete: bool
    urls_unique: bool
    account_verified: bool
    freshness_verified: bool
    is_exhaustive_for_window: bool
    pagination_cursor: str | None = None
    provider: str = "authenticated_wechat"
    verification: str = "unverified"

    @property
    def article_count(self) -> int:
        return len(self.articles)

    def to_dict(self) -> dict[str, object]:
        return {
            "requested_count": self.requested_count,
            "article_count": self.article_count,
            "articles": [article.to_dict() for article in self.articles],
            "count_satisfied": self.count_satisfied,
            "timestamps_complete": self.timestamps_complete,
            "urls_unique": self.urls_unique,
            "account_verified": self.account_verified,
            "freshness_verified": self.freshness_verified,
            "is_exhaustive_for_window": self.is_exhaustive_for_window,
            "pagination_cursor": self.pagination_cursor,
            "provider": self.provider,
            "verification": self.verification,
        }


def canonicalize_mp_url(url: str) -> str:
    split = urlsplit(url.strip())
    host = (split.hostname or "").lower()
    if host != "mp.weixin.qq.com":
        raise ValueError("unsupported_article_host")

    path = split.path or "/s"
    if path.startswith("/s/"):
        query = ""
    else:
        values = dict(parse_qsl(split.query, keep_blank_values=True))
        kept = [(key, values[key]) for key in _PUBLIC_IDENTITY_PARAMS if key in values]
        query = urlencode(kept)

    return urlunsplit(("https", "mp.weixin.qq.com", path, query, ""))


def _parse_datetime(value: object, *, allow_none: bool = False) -> datetime | None:
    if value is None:
        if allow_none:
            return None
        raise ValueError("timestamp_required")
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=CHINA_TZ)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            if allow_none:
                return None
            raise ValueError("timestamp_required")
        if stripped.isdigit():
            return datetime.fromtimestamp(float(stripped), tz=CHINA_TZ)
        parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
    else:
        raise ValueError("unsupported_timestamp")

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=CHINA_TZ)
    return parsed


def normalize_article(raw: Mapping[str, object], position: int) -> ArticleRecord:
    url_value = raw.get("canonical_url") or raw.get("url")
    if not isinstance(url_value, str) or not url_value.strip():
        raise ValueError("article_url_required")

    observed_at = _parse_datetime(raw.get("observed_at"), allow_none=False)
    assert observed_at is not None
    published_at = _parse_datetime(raw.get("published_at"), allow_none=True)

    return ArticleRecord(
        account_name=str(raw.get("account_name") or "").strip(),
        biz=str(raw.get("biz")).strip() if raw.get("biz") is not None else None,
        title=str(raw.get("title") or "").strip(),
        canonical_url=canonicalize_mp_url(url_value),
        published_at=published_at,
        position=position,
        observed_at=observed_at,
        source=str(raw.get("source") or "authenticated_wechat"),
        verified_account=bool(raw.get("verified_account", False)),
    )


def build_discovery_result(
    records: Sequence[ArticleRecord],
    *,
    requested_count: int,
    account_verified: bool,
    freshness_verified: bool,
    is_exhaustive_for_window: bool,
    pagination_cursor: str | None = None,
    provider: str = "authenticated_wechat",
    verification: str = "unverified",
) -> DiscoveryResult:
    if requested_count < 1:
        raise ValueError("requested_count_must_be_positive")

    ordered = sorted(
        records,
        key=lambda record: record.published_at.timestamp() if record.published_at else float("-inf"),
        reverse=True,
    )
    seen: set[str] = set()
    unique: list[ArticleRecord] = []
    for record in ordered:
        if record.canonical_url in seen:
            continue
        seen.add(record.canonical_url)
        unique.append(record)
        if len(unique) >= requested_count:
            break

    positioned = tuple(replace(record, position=index + 1) for index, record in enumerate(unique))
    urls = [record.canonical_url for record in positioned]

    return DiscoveryResult(
        requested_count=requested_count,
        articles=positioned,
        count_satisfied=len(positioned) >= requested_count,
        timestamps_complete=all(record.published_at is not None for record in positioned),
        urls_unique=len(urls) == len(set(urls)),
        account_verified=bool(account_verified and all(record.verified_account for record in positioned)),
        freshness_verified=bool(freshness_verified),
        is_exhaustive_for_window=bool(is_exhaustive_for_window),
        pagination_cursor=pagination_cursor,
        provider=provider,
        verification=verification,
    )


def redact_sensitive_text(value: str) -> str:
    redacted = value
    redacted = re.sub(
        r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+",
        r"\1<redacted>",
        redacted,
    )
    redacted = re.sub(r"(?i)(bearer\s+)[^\s]+", r"\1<redacted>", redacted)
    redacted = re.sub(r"(?i)(cookie\s*:\s*)[^\r\n]+", r"\1<redacted>", redacted)
    keys = "|".join(sorted(re.escape(key) for key in _SENSITIVE_QUERY_KEYS))
    redacted = re.sub(
        rf"(?i)((?:{keys})=)[^&\s]+",
        r"\1<redacted>",
        redacted,
    )
    return redacted
