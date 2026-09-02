import json
from datetime import datetime
from pathlib import Path

import pytest

from app.providers import ProviderError, SyntheticHistoryProvider

FIXTURES = Path(__file__).parent / "fixtures" / "wechat_history"


def test_synthetic_provider_paginates_deduplicates_and_returns_newest_20():
    provider = SyntheticHistoryProvider(FIXTURES)
    result = provider.recent_articles("示例公众号", 20)

    assert result.article_count == 20
    assert result.count_satisfied is True
    assert result.timestamps_complete is True
    assert result.urls_unique is True
    assert result.account_verified is True
    assert result.freshness_verified is True
    assert result.articles[0].title == "文章 01"
    assert result.articles[-1].title == "文章 20"
    assert result.pagination_cursor == "fixture:2"
    assert "?" not in result.pagination_cursor
    assert all("key=" not in article.canonical_url for article in result.articles)


def test_synthetic_provider_respects_since_filter():
    provider = SyntheticHistoryProvider(FIXTURES)
    result = provider.recent_articles(
        "示例公众号",
        20,
        since=datetime.fromisoformat("2026-09-02T15:00:00+08:00"),
    )
    assert [article.title for article in result.articles] == [
        "文章 01",
        "文章 02",
        "文章 03",
        "文章 04",
        "文章 05",
    ]
    assert result.count_satisfied is False


def test_provider_reports_account_not_found(tmp_path: Path):
    (tmp_path / "page1.json").write_text(
        json.dumps({"account": "另一个公众号", "articles": [], "next": None}, ensure_ascii=False),
        encoding="utf-8",
    )
    provider = SyntheticHistoryProvider(tmp_path)
    with pytest.raises(ProviderError) as exc:
        provider.recent_articles("目标公众号", 20)
    assert exc.value.code == "ACCOUNT_NOT_FOUND"


def test_provider_reports_login_required(tmp_path: Path):
    (tmp_path / "page1.json").write_text(
        json.dumps({"status": "login_required"}),
        encoding="utf-8",
    )
    provider = SyntheticHistoryProvider(tmp_path)
    with pytest.raises(ProviderError) as exc:
        provider.recent_articles("目标公众号", 20)
    assert exc.value.code == "LOGIN_REQUIRED"


def test_provider_reports_incomplete_pagination(tmp_path: Path):
    (tmp_path / "page1.json").write_text(
        json.dumps(
            {
                "account": "目标公众号",
                "freshness_verified": True,
                "next": "missing.json",
                "articles": [
                    {
                        "account_name": "目标公众号",
                        "title": "one",
                        "url": "https://mp.weixin.qq.com/s/one",
                        "published_at": "2026-09-02T08:00:00+08:00",
                        "observed_at": "2026-09-02T09:00:00+08:00",
                        "verified_account": True,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    provider = SyntheticHistoryProvider(tmp_path)
    with pytest.raises(ProviderError) as exc:
        provider.recent_articles("目标公众号", 20)
    assert exc.value.code == "PAGINATION_INCOMPLETE"
