import json
import sqlite3
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from app.providers import AuthenticatedHistoryProvider, HistoryPageResponse, ProviderError
from app.public_accounts import VerifiedAccountIdentity


def make_history(path: Path, *, include_seed: bool = True) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE urls (id INTEGER PRIMARY KEY, url TEXT, title TEXT, visit_count INTEGER, typed_count INTEGER, last_visit_time INTEGER, hidden INTEGER)"
        )
        if include_seed:
            connection.execute(
                "INSERT INTO urls VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    1,
                    "https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz=BIZSECRET&uin=UINSECRET&key=KEYSECRET&pass_ticket=PASSSECRET&appmsg_token=TOKENSECRET",
                    "history",
                    1,
                    0,
                    999,
                    0,
                ),
            )
        connection.commit()
    finally:
        connection.close()


def make_page(start: int, count: int, can_continue: bool) -> bytes:
    entries = []
    base_timestamp = 1788307200
    for index in range(start, start + count):
        entries.append(
            {
                "comm_msg_info": {"datetime": base_timestamp - index * 3600},
                "app_msg_ext_info": {
                    "title": f"Article {index + 1}",
                    "content_url": (
                        "https://mp.weixin.qq.com/s?__biz=BIZPUB"
                        f"&mid={1000 + index}&idx=1&sn=SN{index + 1}"
                        f"&key=ARTICLE_SECRET_{index + 1}&pass_ticket=ARTICLE_PASS_{index + 1}"
                    ),
                    "multi_app_msg_item_list": [],
                },
            }
        )
    outer = {
        "ret": 0,
        "can_msg_continue": 1 if can_continue else 0,
        "general_msg_list": json.dumps({"list": entries}, separators=(",", ":")),
    }
    return json.dumps(outer).encode("utf-8")


class MemoryTransport:
    def __init__(self, pages: dict[int, bytes]) -> None:
        self.pages = pages
        self.urls: list[str] = []

    def get(self, url: str) -> bytes:
        self.urls.append(url)
        offset = int(parse_qs(urlsplit(url).query)["offset"][0])
        return self.pages[offset]


class LiveMemoryTransport(MemoryTransport):
    def __init__(self, pages: dict[int, bytes], *, live_offsets: set[int]) -> None:
        super().__init__(pages)
        self.live_offsets = live_offsets

    def get(self, url: str) -> HistoryPageResponse:
        payload = super().get(url)
        offset = int(parse_qs(urlsplit(url).query)["offset"][0])
        return HistoryPageResponse(payload=payload, live_observation=offset in self.live_offsets)


def verified_identity(*, account_name: str = "Example Account", biz: str = "BIZPUB") -> VerifiedAccountIdentity:
    return VerifiedAccountIdentity(
        account_name=account_name,
        biz=biz,
        provenance="public_seed_article",
        canonical_seed_url="https://mp.weixin.qq.com/s/public-seed",
    )


def test_authenticated_history_provider_returns_twenty_unverified_for_byte_only_transport(tmp_path: Path):
    history = tmp_path / "History"
    make_history(history)
    transport = MemoryTransport({0: make_page(0, 10, True), 10: make_page(10, 10, False)})
    provider = AuthenticatedHistoryProvider(history, transport)

    result = provider.recent_articles("Example Account", 20)

    assert result.article_count == 20
    assert result.count_satisfied is True
    assert result.timestamps_complete is True
    assert result.urls_unique is True
    assert result.account_verified is False
    assert result.freshness_verified is False
    assert all(article.verified_account is False for article in result.articles)
    assert [article.title for article in result.articles[:2]] == ["Article 1", "Article 2"]
    assert [int(parse_qs(urlsplit(url).query)["offset"][0]) for url in transport.urls] == [0, 10]
    assert "KEYSECRET" in transport.urls[0]
    rendered = json.dumps(result.to_dict(), ensure_ascii=False)
    for secret in ["KEYSECRET", "PASSSECRET", "TOKENSECRET", "ARTICLE_SECRET_1", "ARTICLE_PASS_1"]:
        assert secret not in rendered


def test_authenticated_history_provider_applies_matching_identity_and_live_offset_zero_evidence(tmp_path: Path):
    history = tmp_path / "History"
    make_history(history)
    transport = LiveMemoryTransport(
        {0: make_page(0, 10, True), 10: make_page(10, 10, False)},
        live_offsets={0, 10},
    )
    provider = AuthenticatedHistoryProvider(history, transport)

    result = provider.recent_articles(
        "Example Account",
        20,
        verified_identity=verified_identity(),
    )

    assert result.account_verified is True
    assert result.freshness_verified is True
    assert all(article.verified_account is True for article in result.articles)
    assert {article.account_name for article in result.articles} == {"Example Account"}
    assert result.verification == "public_seed_article+live_offset_zero"


def test_authenticated_history_provider_rejects_identity_name_or_article_biz_mismatch(tmp_path: Path):
    history = tmp_path / "History"
    make_history(history)
    provider = AuthenticatedHistoryProvider(
        history,
        LiveMemoryTransport({0: make_page(0, 10, False)}, live_offsets={0}),
    )

    with pytest.raises(ProviderError) as wrong_name:
        provider.recent_articles(
            "Wrong Display Name",
            10,
            verified_identity=verified_identity(),
        )
    assert wrong_name.value.code == "ACCOUNT_NOT_FOUND"

    with pytest.raises(ProviderError) as wrong_biz:
        provider.recent_articles(
            "Example Account",
            10,
            verified_identity=verified_identity(biz="UNRELATED_BIZ"),
        )
    assert wrong_biz.value.code == "ACCOUNT_NOT_FOUND"

    missing_biz_provider = AuthenticatedHistoryProvider(
        history,
        LiveMemoryTransport(
            {0: make_page(0, 10, False).replace(b"__biz=BIZPUB&", b"")},
            live_offsets={0},
        ),
    )
    with pytest.raises(ProviderError) as missing_biz:
        missing_biz_provider.recent_articles(
            "Example Account",
            10,
            verified_identity=verified_identity(),
        )
    assert missing_biz.value.code == "ACCOUNT_NOT_FOUND"


def test_live_nonzero_page_does_not_establish_freshness_without_live_offset_zero(tmp_path: Path):
    history = tmp_path / "History"
    make_history(history)
    provider = AuthenticatedHistoryProvider(
        history,
        LiveMemoryTransport(
            {0: make_page(0, 10, True), 10: make_page(10, 10, False)},
            live_offsets={10},
        ),
    )

    result = provider.recent_articles(
        "Example Account",
        20,
        verified_identity=verified_identity(),
    )

    assert result.account_verified is True
    assert result.freshness_verified is False
    assert result.verification == "public_seed_article"


def test_authenticated_history_provider_errors_when_history_seed_is_missing(tmp_path: Path):
    history = tmp_path / "History"
    make_history(history, include_seed=False)
    provider = AuthenticatedHistoryProvider(history, MemoryTransport({}))

    with pytest.raises(ProviderError) as exc:
        provider.recent_articles("Example", 20)
    assert exc.value.code == "HISTORY_SURFACE_UNAVAILABLE"


def test_authenticated_history_provider_reports_incomplete_pagination(tmp_path: Path):
    history = tmp_path / "History"
    make_history(history)
    provider = AuthenticatedHistoryProvider(
        history,
        MemoryTransport({0: make_page(0, 7, False)}),
    )

    with pytest.raises(ProviderError) as exc:
        provider.recent_articles("Example", 20)
    assert exc.value.code == "PAGINATION_INCOMPLETE"


def test_authenticated_history_provider_validates_limit_before_touching_transport(tmp_path: Path):
    history = tmp_path / "History"
    make_history(history)
    transport = MemoryTransport({})
    provider = AuthenticatedHistoryProvider(history, transport)

    with pytest.raises(ValueError):
        provider.recent_articles("Example", 0)
    assert transport.urls == []
