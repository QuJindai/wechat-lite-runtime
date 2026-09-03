from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Protocol

from app.history_pager import (
    ProfileExtAuthError,
    ProfileExtResponseError,
    build_page_url,
    parse_profile_ext_page,
)
from app.history_seed import HistorySeed, locate_history_seed
from app.public_accounts import (
    ArticleRecord,
    DiscoveryResult,
    VerifiedAccountIdentity,
    build_discovery_result,
    normalize_account_display_name,
    normalize_article,
)


class ProviderError(RuntimeError):
    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


class PublicAccountProvider(Protocol):
    def recent_articles(
        self,
        account: str,
        limit: int,
        since: datetime | None = None,
    ) -> DiscoveryResult: ...


@dataclass(frozen=True)
class HistoryPageResponse:
    payload: bytes
    live_observation: bool = False


class HistoryTransport(Protocol):
    def get(self, url: str) -> bytes | HistoryPageResponse: ...


def _unwrap_history_response(response: bytes | HistoryPageResponse) -> tuple[bytes, bool]:
    if isinstance(response, HistoryPageResponse):
        return response.payload, bool(response.live_observation)
    if isinstance(response, bytes):
        return response, False
    raise ProviderError("HISTORY_SURFACE_UNAVAILABLE", "history_transport_invalid_response")


def _verified_records(
    records: list[ArticleRecord],
    identity: VerifiedAccountIdentity | None,
) -> list[ArticleRecord]:
    if identity is None:
        return [replace(record, verified_account=False) for record in records]
    if any(record.biz != identity.biz for record in records):
        raise ProviderError("ACCOUNT_NOT_FOUND", "discovered_article_account_mismatch")
    return [
        replace(
            record,
            account_name=identity.account_name,
            verified_account=True,
        )
        for record in records
    ]


def _verification_label(*, account_verified: bool, freshness_verified: bool) -> str:
    if account_verified and freshness_verified:
        return "public_seed_article+live_offset_zero"
    if account_verified:
        return "public_seed_article"
    if freshness_verified:
        return "live_offset_zero"
    return "unverified"


class AuthenticatedHistoryProvider:
    def __init__(
        self,
        history_db: Path | None,
        transport: HistoryTransport,
        *,
        seed: HistorySeed | None = None,
    ) -> None:
        self.history_db = Path(history_db) if history_db is not None else None
        self.transport = transport
        self._seed = seed

    def recent_articles(
        self,
        account: str,
        limit: int,
        since: datetime | None = None,
        *,
        verified_identity: VerifiedAccountIdentity | None = None,
    ) -> DiscoveryResult:
        if limit < 1:
            raise ValueError("limit_must_be_positive")
        if verified_identity is not None:
            try:
                requested_name = normalize_account_display_name(account)
            except ValueError as exc:
                raise ProviderError("ACCOUNT_NOT_FOUND", "verified_account_name_mismatch") from exc
            if requested_name.casefold() != verified_identity.account_name.casefold():
                raise ProviderError("ACCOUNT_NOT_FOUND", "verified_account_name_mismatch")

        seed = self._seed
        if seed is None and self.history_db is not None:
            seed = locate_history_seed(self.history_db)
        if seed is None:
            raise ProviderError("HISTORY_SURFACE_UNAVAILABLE")

        offset = 0
        page_size = min(10, max(1, limit))
        records = []
        max_pages = 100
        live_offset_zero_observed = False

        for _ in range(max_pages):
            private_url = build_page_url(seed, offset=offset, count=page_size)
            try:
                response = self.transport.get(private_url)
                payload, live_observation = _unwrap_history_response(response)
            except ProviderError:
                raise
            except Exception as exc:
                raise ProviderError("HISTORY_SURFACE_UNAVAILABLE", "history_transport_failed") from exc

            try:
                page_records, can_continue = parse_profile_ext_page(payload, account)
            except ProfileExtAuthError as exc:
                raise ProviderError("LOGIN_REQUIRED", "profile_ext_login_required") from exc
            except ProfileExtResponseError as exc:
                raise ProviderError("HISTORY_SURFACE_UNAVAILABLE", "profile_ext_request_rejected") from exc
            except ValueError as exc:
                raise ProviderError("HISTORY_SURFACE_UNAVAILABLE", "history_page_invalid") from exc

            records.extend(page_records)
            if offset == 0 and live_observation:
                live_offset_zero_observed = True
            evidenced_records = _verified_records(records, verified_identity)
            filtered = evidenced_records
            if since is not None:
                filtered = [
                    article
                    for article in evidenced_records
                    if article.published_at is not None and article.published_at >= since
                ]

            account_verified = verified_identity is not None
            result = build_discovery_result(
                filtered,
                requested_count=limit,
                account_verified=account_verified,
                freshness_verified=live_offset_zero_observed,
                is_exhaustive_for_window=False,
                pagination_cursor=(
                    f"history:{seed.safe_summary()['seed_fingerprint']}:{offset + page_size}"
                    if can_continue
                    else None
                ),
                provider="authenticated_history",
                verification=_verification_label(
                    account_verified=account_verified,
                    freshness_verified=live_offset_zero_observed,
                ),
            )
            if result.count_satisfied:
                return result
            if not can_continue:
                raise ProviderError("PAGINATION_INCOMPLETE")
            offset += page_size

        raise ProviderError("PAGINATION_INCOMPLETE", "history_pagination_guard")


class SyntheticHistoryProvider:
    def __init__(self, fixture_dir: Path) -> None:
        self.fixture_dir = Path(fixture_dir)

    def _load_page(self, filename: str) -> dict[str, object]:
        path = self.fixture_dir / filename
        if not path.is_file():
            raise ProviderError("PAGINATION_INCOMPLETE", "synthetic_page_missing")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProviderError("HISTORY_SURFACE_UNAVAILABLE", "synthetic_page_invalid") from exc
        if not isinstance(data, dict):
            raise ProviderError("HISTORY_SURFACE_UNAVAILABLE", "synthetic_page_invalid")
        return data

    def recent_articles(
        self,
        account: str,
        limit: int,
        since: datetime | None = None,
    ) -> DiscoveryResult:
        if limit < 1:
            raise ValueError("limit_must_be_positive")

        first = self.fixture_dir / "page1.json"
        if not first.is_file():
            raise ProviderError("HISTORY_SURFACE_UNAVAILABLE")

        current = "page1.json"
        visited: set[str] = set()
        raw_articles: list[dict[str, object]] = []
        page_count = 0
        while current is not None:
            if current in visited:
                raise ProviderError("PAGINATION_INCOMPLETE", "synthetic_pagination_cycle")
            visited.add(current)
            page = self._load_page(current)
            page_count += 1

            if page.get("status") == "login_required":
                raise ProviderError("LOGIN_REQUIRED")

            page_account = str(page.get("account") or "")
            if page_count == 1 and page_account != account:
                raise ProviderError("ACCOUNT_NOT_FOUND")
            articles = page.get("articles") or []
            if not isinstance(articles, list):
                raise ProviderError("HISTORY_SURFACE_UNAVAILABLE", "synthetic_articles_invalid")
            for item in articles:
                if isinstance(item, dict):
                    raw_articles.append(item)

            normalized = [normalize_article(item, position=index + 1) for index, item in enumerate(raw_articles)]
            if since is not None:
                normalized = [
                    article
                    for article in normalized
                    if article.published_at is not None and article.published_at >= since
                ]

            unique_urls = {article.canonical_url for article in normalized}
            next_value = page.get("next")
            next_page = str(next_value) if next_value else None

            if len(unique_urls) >= limit or next_page is None:
                break
            if not (self.fixture_dir / next_page).is_file():
                raise ProviderError("PAGINATION_INCOMPLETE")
            current = next_page

        normalized = [
            replace(normalize_article(item, position=index + 1), verified_account=False)
            for index, item in enumerate(raw_articles)
        ]
        if since is not None:
            normalized = [
                article
                for article in normalized
                if article.published_at is not None and article.published_at >= since
            ]

        return build_discovery_result(
            normalized,
            requested_count=limit,
            account_verified=False,
            freshness_verified=False,
            is_exhaustive_for_window=False,
            pagination_cursor=f"fixture:{page_count}",
            provider="synthetic_history",
            verification="synthetic_fixture",
        )
