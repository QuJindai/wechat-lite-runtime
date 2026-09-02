from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.public_accounts import build_discovery_result, normalize_article
from app.seed_article import SeedIdentity


def settings(tmp_path: Path) -> Settings:
    return Settings(control_token="secret", codespace_name="space", state_dir=tmp_path, wechat_host="127.0.0.1", wechat_port=3001, probe_timeout=0.1)


def auth():
    return {"Authorization": "Bearer secret"}


class FakeResolver:
    def resolve(self, url: str) -> SeedIdentity:
        return SeedIdentity(account_name="dSPACE德斯拜思", biz="Mzg2Mzg3NzgxNw==", canonical_url=url)


class FakeLiveDiscovery:
    def recent_articles(self, account_name, biz, limit):
        assert account_name == "dSPACE德斯拜思"
        assert biz == "Mzg2Mzg3NzgxNw=="
        assert limit == 20
        rows = []
        for i in range(20):
            rows.append(normalize_article({
                "account_name": account_name,
                "biz": biz,
                "title": f"Article {i+1}",
                "url": f"https://mp.weixin.qq.com/s/item-{i+1}",
                "published_at": 1788307200 - i * 3600,
                "observed_at": 1788310800,
                "verified_account": True,
            }, i + 1))
        return build_discovery_result(rows, requested_count=20, account_verified=True, freshness_verified=True, is_exhaustive_for_window=False, provider="authenticated_history", verification="seed_url")


def test_acceptance_from_url_requires_bearer(tmp_path: Path):
    client = TestClient(create_app(settings(tmp_path), tcp_probe=lambda *_: True, live_discovery_service=FakeLiveDiscovery(), seed_article_resolver=FakeResolver()))
    assert client.post("/v1/public-accounts/acceptance-from-url", json={"article_url":"https://mp.weixin.qq.com/s/abc"}).status_code == 401


def test_acceptance_from_url_resolves_identity_and_reuses_newest20_gate(tmp_path: Path):
    client = TestClient(create_app(settings(tmp_path), tcp_probe=lambda *_: True, live_discovery_service=FakeLiveDiscovery(), seed_article_resolver=FakeResolver()))
    response = client.post("/v1/public-accounts/acceptance-from-url", json={"article_url":"https://mp.weixin.qq.com/s/STxoDJyTsG6rrlZBDcBK9g"}, headers=auth())
    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "AUTOMATED_GATE_PASS_UI_PENDING"
    assert body["seed"]["account_name"] == "dSPACE德斯拜思"
    assert body["seed"]["biz"] == "Mzg2Mzg3NzgxNw=="
    assert body["seed"]["canonical_url"] == "https://mp.weixin.qq.com/s/STxoDJyTsG6rrlZBDcBK9g"
    assert body["sensitive_values_returned"] is False
