from datetime import datetime, timedelta, timezone

from app.public_accounts import (
    ArticleRecord,
    build_discovery_result,
    canonicalize_mp_url,
    normalize_article,
    redact_sensitive_text,
)


def test_canonicalize_mp_url_strips_auth_bearing_query_values():
    url = (
        "https://mp.weixin.qq.com/s?__biz=MzA123&mid=2247483000&idx=1&sn=abc123"
        "&chksm=deadbeef&scene=21&key=SUPERSECRET&pass_ticket=PASSSECRET&uin=12345"
    )
    canonical = canonicalize_mp_url(url)

    assert canonical == (
        "https://mp.weixin.qq.com/s?__biz=MzA123&mid=2247483000&idx=1&sn=abc123&chksm=deadbeef"
    )
    assert "SUPERSECRET" not in canonical
    assert "PASSSECRET" not in canonical
    assert "scene=" not in canonical


def test_canonicalize_path_article_drops_tracking_query():
    url = "https://mp.weixin.qq.com/s/AbCdEf?scene=1&key=secret"
    assert canonicalize_mp_url(url) == "https://mp.weixin.qq.com/s/AbCdEf"


def test_normalize_article_parses_timestamp_and_public_fields():
    record = normalize_article(
        {
            "account_name": "示例公众号",
            "biz": "MzA123",
            "title": "文章 A",
            "url": "https://mp.weixin.qq.com/s/AbCdEf?scene=1&key=secret",
            "published_at": "2026-09-02T08:30:00+08:00",
            "observed_at": "2026-09-02T09:00:00+08:00",
            "verified_account": True,
        },
        position=1,
    )

    assert isinstance(record, ArticleRecord)
    assert record.canonical_url == "https://mp.weixin.qq.com/s/AbCdEf"
    assert record.published_at.isoformat() == "2026-09-02T08:30:00+08:00"
    assert record.position == 1
    assert record.verified_account is True


def test_normalize_article_accepts_unix_timestamp_in_china_timezone():
    china = timezone(timedelta(hours=8))
    expected = datetime(2026, 9, 2, 8, 0, tzinfo=china)
    record = normalize_article(
        {
            "account_name": "示例公众号",
            "biz": "MzA123",
            "title": "文章 B",
            "url": "https://mp.weixin.qq.com/s/slug-b",
            "published_at": int(expected.timestamp()),
            "observed_at": "2026-09-02T09:00:00+08:00",
            "verified_account": True,
        },
        position=2,
    )
    assert record.published_at == expected


def test_build_discovery_result_deduplicates_and_orders_newest_first():
    raw = [
        {
            "account_name": "示例公众号",
            "biz": "MzA123",
            "title": "Old",
            "url": "https://mp.weixin.qq.com/s/old",
            "published_at": "2026-09-01T08:00:00+08:00",
            "observed_at": "2026-09-02T09:00:00+08:00",
            "verified_account": True,
        },
        {
            "account_name": "示例公众号",
            "biz": "MzA123",
            "title": "New",
            "url": "https://mp.weixin.qq.com/s/new?scene=1",
            "published_at": "2026-09-02T08:00:00+08:00",
            "observed_at": "2026-09-02T09:00:00+08:00",
            "verified_account": True,
        },
        {
            "account_name": "示例公众号",
            "biz": "MzA123",
            "title": "New duplicate",
            "url": "https://mp.weixin.qq.com/s/new?key=secret",
            "published_at": "2026-09-02T08:00:00+08:00",
            "observed_at": "2026-09-02T09:00:00+08:00",
            "verified_account": True,
        },
    ]
    records = [normalize_article(item, position=i + 1) for i, item in enumerate(raw)]

    result = build_discovery_result(
        records,
        requested_count=2,
        account_verified=True,
        freshness_verified=True,
        is_exhaustive_for_window=False,
        pagination_cursor="opaque:2",
    )

    assert [article.title for article in result.articles] == ["New", "Old"]
    assert result.count_satisfied is True
    assert result.timestamps_complete is True
    assert result.urls_unique is True
    assert result.account_verified is True
    assert result.freshness_verified is True
    assert result.is_exhaustive_for_window is False


def test_completeness_flags_remain_independent():
    only = normalize_article(
        {
            "account_name": "示例公众号",
            "biz": "MzA123",
            "title": "Only",
            "url": "https://mp.weixin.qq.com/s/only",
            "published_at": "2026-09-02T08:00:00+08:00",
            "observed_at": "2026-09-02T09:00:00+08:00",
            "verified_account": True,
        },
        position=1,
    )
    result = build_discovery_result(
        [only],
        requested_count=20,
        account_verified=True,
        freshness_verified=False,
        is_exhaustive_for_window=True,
    )

    assert result.count_satisfied is False
    assert result.timestamps_complete is True
    assert result.urls_unique is True
    assert result.account_verified is True
    assert result.freshness_verified is False
    assert result.is_exhaustive_for_window is True


def test_redact_sensitive_text_removes_bearer_cookie_and_token_values():
    value = (
        "GET https://mp.weixin.qq.com/s?mid=1&key=URLSECRET&pass_ticket=PASSSECRET "
        "Authorization: Bearer BEARERSECRET Cookie: session=COOKIESECRET token=TOKENVALUE"
    )
    redacted = redact_sensitive_text(value)

    for secret in ["URLSECRET", "PASSSECRET", "BEARERSECRET", "COOKIESECRET", "TOKENVALUE"]:
        assert secret not in redacted
    assert "<redacted>" in redacted
