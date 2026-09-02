from __future__ import annotations

import io

import pytest

from app.seed_article import SeedArticleResolver, SeedResolutionError


class FakeResponse:
    def __init__(self, body: bytes, *, status: int = 200, url: str = "https://mp.weixin.qq.com/s/AbCd") -> None:
        self._body = body
        self.status = status
        self._url = url

    def read(self, amount: int = -1) -> bytes:
        return self._body if amount < 0 else self._body[:amount]

    def geturl(self) -> str:
        return self._url

    def close(self) -> None:
        pass


def test_seed_resolver_extracts_account_and_biz_without_returning_private_material():
    html = b'''<html><head><meta property="og:article:author" content="dSPACE&#x5FB7;&#x65AF;&#x62DC;&#x601D;"></head><body><script>var biz = "Mzg2Mzg3NzgxNw=="; var key = "DO_NOT_RETURN";</script></body></html>'''
    resolver = SeedArticleResolver(opener=lambda req, timeout: FakeResponse(html))

    identity = resolver.resolve("https://mp.weixin.qq.com/s/STxoDJyTsG6rrlZBDcBK9g")

    assert identity.account_name == "dSPACE德斯拜思"
    assert identity.biz == "Mzg2Mzg3NzgxNw=="
    assert identity.canonical_url == "https://mp.weixin.qq.com/s/STxoDJyTsG6rrlZBDcBK9g"
    rendered = repr(identity.safe_summary()) + repr(identity)
    assert "DO_NOT_RETURN" not in rendered


def test_seed_resolver_rejects_non_wechat_hosts_before_network_call():
    calls = []
    resolver = SeedArticleResolver(opener=lambda req, timeout: calls.append(req) or FakeResponse(b""))
    with pytest.raises(SeedResolutionError) as exc:
        resolver.resolve("https://example.com/s/abc")
    assert exc.value.code == "SEED_URL_NOT_ALLOWED"
    assert calls == []


def test_seed_resolver_rejects_cross_host_redirect():
    resolver = SeedArticleResolver(
        opener=lambda req, timeout: FakeResponse(
            b'<meta property="og:article:author" content="Name"><script>var biz="BIZ";</script>',
            url="https://evil.example/result",
        )
    )
    with pytest.raises(SeedResolutionError) as exc:
        resolver.resolve("https://mp.weixin.qq.com/s/abc")
    assert exc.value.code == "SEED_REDIRECT_NOT_ALLOWED"


def test_seed_resolver_reports_missing_public_identity_without_echoing_page():
    resolver = SeedArticleResolver(opener=lambda req, timeout: FakeResponse(b"SECRET PAGE WITHOUT IDENTITY"))
    with pytest.raises(SeedResolutionError) as exc:
        resolver.resolve("https://mp.weixin.qq.com/s/abc")
    assert exc.value.code == "SEED_IDENTITY_NOT_FOUND"
    assert "SECRET PAGE" not in str(exc.value)
