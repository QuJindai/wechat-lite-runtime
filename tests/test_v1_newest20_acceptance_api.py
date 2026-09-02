from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.public_accounts import build_discovery_result, normalize_article


def settings(tmp_path: Path) -> Settings:
    return Settings(
        control_token="secret",
        codespace_name="acceptance-space",
        state_dir=tmp_path,
        wechat_host="127.0.0.1",
        wechat_port=3001,
        probe_timeout=0.1,
    )


def auth():
    return {"Authorization": "Bearer secret"}


class Service:
    def __init__(self):
        self.calls = []

    def recent_articles(self, account_name, biz, limit):
        self.calls.append((account_name, biz, limit))
        base = datetime(2026, 9, 2, 20, 0, tzinfo=timezone(timedelta(hours=8)))
        records = [
            normalize_article({
                "account_name": account_name,
                "biz": "RESOLVED_BIZ",
                "title": f"Article {i+1}",
                "url": f"https://mp.weixin.qq.com/s/article-{i+1}?key=SECRET{i+1}",
                "published_at": base.timestamp() - i * 3600,
                "observed_at": base,
                "verified_account": True,
            }, i + 1)
            for i in range(20)
        ]
        return build_discovery_result(
            records,
            requested_count=20,
            account_verified=True,
            freshness_verified=True,
            is_exhaustive_for_window=False,
            provider="authenticated_history",
            verification="authenticated_history_seed",
        )


def test_acceptance_endpoint_is_bearer_protected_and_runs_name_only_newest20_gate(tmp_path):
    service = Service()
    client = TestClient(create_app(settings(tmp_path), tcp_probe=lambda *_: True, live_discovery_service=service))

    assert client.post("/v1/public-accounts/acceptance", json={"account_name": "目标公众号"}).status_code == 401

    response = client.post(
        "/v1/public-accounts/acceptance",
        json={"account_name": "目标公众号"},
        headers=auth(),
    )
    assert response.status_code == 200
    assert service.calls == [("目标公众号", None, 20)]
    body = response.json()
    assert body["verdict"] == "AUTOMATED_GATE_PASS_UI_PENDING"
    assert body["first"]["title"] == "Article 1"
    assert body["twentieth"]["title"] == "Article 20"
    assert "SECRET1" not in response.text


def test_acceptance_endpoint_accepts_optional_biz_and_forces_limit_twenty(tmp_path):
    service = Service()
    client = TestClient(create_app(settings(tmp_path), tcp_probe=lambda *_: True, live_discovery_service=service))
    response = client.post(
        "/v1/public-accounts/acceptance",
        json={"account_name": "目标公众号", "biz": "KNOWN_BIZ"},
        headers=auth(),
    )
    assert response.status_code == 200
    assert service.calls == [("目标公众号", "KNOWN_BIZ", 20)]
