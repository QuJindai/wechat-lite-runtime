from __future__ import annotations

import json
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
from app.public_accounts import DiscoveryResult, build_discovery_result, normalize_article


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


class HistoryTransport(Protocol):
    def get(self, url: str) -> bytes: ...


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
    ) -> DiscoveryResult:
        if limit < 1:
            raise ValueError("limit_must_be_positive")

        seed = self._seed
        if seed is None and self.history_db is not None:
            seed = locate_history_seed(self.history_db)
        if seed is None:
            raise ProviderError("HISTORY_SURFACE_UNAVAILABLE")

        offset = 0
        page_size = min(10, max(1, limit))
        records = []
        max_pages = 100

        for _ in range(max_pages):
            private_url = build_page_url(seed, offset=offset, count=page_size)
            try:
                payload = self.transport.get(private_url)
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
            filtered = records
            if since is not None:
                filtered = [
                    article
                    for article in records
                    if article.published_at is not None and article.published_at >= since
                ]

            result = build_discovery_result(
                filtered,
                requested_count=limit,
                account_verified=True,
                freshness_verified=True,
                is_exhaustive_for_window=False,
                pagination_cursor=(
                    f"history:{seed.safe_summary()['seed_fingerprint']}:{offset + page_size}"
                    if can_continue
                    else None
                ),
                provider="authenticated_history",
                verification="authenticated_history_seed",
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
        freshness_verified = True
        account_verified = True

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
            if page_account and page_account != account:
                account_verified = False

            freshness_verified = freshness_verified and bool(page.get("freshness_verified", False))
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

        normalized = [normalize_article(item, position=index + 1) for index, item in enumerate(raw_articles)]
        if since is not None:
            normalized = [
                article
                for article in normalized
                if article.published_at is not None and article.published_at >= since
            ]

        return build_discovery_result(
            normalized,
            requested_count=limit,
            account_verified=account_verified,
            freshness_verified=freshness_verified,
            is_exhaustive_for_window=False,
            pagination_cursor=f"fixture:{page_count}",
            provider="synthetic_history",
            verification="synthetic_fixture",
        )
