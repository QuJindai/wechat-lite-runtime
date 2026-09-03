from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.providers import ProviderError
from app.public_accounts import build_discovery_result, normalize_article


def settings(tmp_path: Path) -> Settings:
    return Settings(
        control_token="secret",
        codespace_name="api-space",
        state_dir=tmp_path,
        wechat_host="127.0.0.1",
        wechat_port=3001,
        probe_timeout=0.1,
    )


def auth():
    return {"Authorization": "Bearer secret"}


def result20():
    records = []
    for i in range(20):
        records.append(normalize_article({
            "account_name": "Example Account",
            "biz": "BIZ_PUBLIC",
            "title": f"Article {i + 1}",
            "url": f"https://mp.weixin.qq.com/s?__biz=BIZ_PUBLIC&mid={1000+i}&idx=1&sn=SN{i+1}&key=SECRET",
            "published_at": 1788307200 - i * 3600,
            "observed_at": "2026-09-02T22:00:00+08:00",
            "verified_account": False,
        }, i + 1))
    return build_discovery_result(
        records,
        requested_count=20,
        account_verified=False,
        freshness_verified=True,
        is_exhaustive_for_window=False,
        provider="live_authenticated_history",
        verification="bootstrap_credential_http",
    )


class FakeLiveService:
    def __init__(self):
        self.calls = []

    def recent_articles(self, account_name, biz, limit):
        self.calls.append((account_name, biz, limit))
        return result20()


def test_live_discover_endpoint_requires_bearer(tmp_path: Path):
    service = FakeLiveService()
    client = TestClient(create_app(settings(tmp_path), tcp_probe=lambda *_: True, live_discovery_service=service))
    response = client.post("/v1/public-accounts/discover", json={"account_name":"Example Account","biz":"BIZ_PUBLIC","limit":20})
    assert response.status_code == 401


def test_live_discover_endpoint_runs_one_call_and_returns_sanitized_20(tmp_path: Path):
    service = FakeLiveService()
    client = TestClient(create_app(settings(tmp_path), tcp_probe=lambda *_: True, live_discovery_service=service))
    response = client.post(
        "/v1/public-accounts/discover",
        json={"account_name":"Example Account","biz":"BIZ_PUBLIC","limit":20},
        headers=auth(),
    )
    assert response.status_code == 200
    assert service.calls == [("Example Account", "BIZ_PUBLIC", 20)]
    body = response.json()
    assert body["article_count"] == 20
    assert body["count_satisfied"] is True
    assert body["timestamps_complete"] is True
    assert body["urls_unique"] is True
    assert body["account_verified"] is False
    assert body["freshness_verified"] is True
    assert "key=SECRET" not in response.text


def test_live_discover_endpoint_validates_limit(tmp_path: Path):
    service = FakeLiveService()
    client = TestClient(create_app(settings(tmp_path), tcp_probe=lambda *_: True, live_discovery_service=service))
    response = client.post(
        "/v1/public-accounts/discover",
        json={"account_name":"Example","biz":"BIZ_PUBLIC","limit":101},
        headers=auth(),
    )
    assert response.status_code == 422
    assert service.calls == []


def test_live_discover_endpoint_maps_provider_error_without_secret(tmp_path: Path):
    class Failing:
        def recent_articles(self, account_name, biz, limit):
            raise ProviderError("LOGIN_REQUIRED", "expired key=PRIVATE_SECRET")
    client = TestClient(create_app(settings(tmp_path), tcp_probe=lambda *_: True, live_discovery_service=Failing()))
    response = client.post(
        "/v1/public-accounts/discover",
        json={"account_name":"Example","biz":"BIZ_PUBLIC","limit":20},
        headers=auth(),
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "LOGIN_REQUIRED"
    assert "PRIVATE_SECRET" not in response.text
