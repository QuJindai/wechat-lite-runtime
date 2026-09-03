from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.providers import ProviderError, SyntheticHistoryProvider

FIXTURES = Path(__file__).parent / "fixtures" / "wechat_history"


def settings(tmp_path: Path) -> Settings:
    return Settings(
        control_token="secret",
        codespace_name="api-space",
        state_dir=tmp_path,
        wechat_host="127.0.0.1",
        wechat_port=3001,
        probe_timeout=0.1,
    )


def auth() -> dict[str, str]:
    return {"Authorization": "Bearer secret"}


def test_recent_endpoint_requires_bearer_token(tmp_path: Path):
    app = create_app(
        settings(tmp_path),
        tcp_probe=lambda *_: True,
        public_account_provider=SyntheticHistoryProvider(FIXTURES),
    )
    client = TestClient(app)
    assert client.get("/v1/public-accounts/示例公众号/recent?limit=20").status_code == 401


def test_recent_endpoint_returns_synthetic_content_without_verification_claims(tmp_path: Path):
    app = create_app(
        settings(tmp_path),
        tcp_probe=lambda *_: True,
        public_account_provider=SyntheticHistoryProvider(FIXTURES),
    )
    client = TestClient(app)
    response = client.get(
        "/v1/public-accounts/示例公众号/recent?limit=20",
        headers=auth(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["article_count"] == 20
    assert body["count_satisfied"] is True
    assert body["timestamps_complete"] is True
    assert body["urls_unique"] is True
    assert body["account_verified"] is False
    assert body["freshness_verified"] is False
    assert all(article["verified_account"] is False for article in body["articles"])
    assert len(body["articles"]) == 20
    assert all("key=" not in article["canonical_url"] for article in body["articles"])
    assert "cookie" not in response.text.lower()


def test_recent_endpoint_validates_limit(tmp_path: Path):
    app = create_app(
        settings(tmp_path),
        tcp_probe=lambda *_: True,
        public_account_provider=SyntheticHistoryProvider(FIXTURES),
    )
    client = TestClient(app)
    assert client.get("/v1/public-accounts/示例公众号/recent?limit=0", headers=auth()).status_code == 422
    assert client.get("/v1/public-accounts/示例公众号/recent?limit=101", headers=auth()).status_code == 422


def test_recent_endpoint_maps_provider_error_without_leaking_secret(tmp_path: Path):
    class FailingProvider:
        def recent_articles(self, account, limit, since=None):
            raise ProviderError(
                "LOGIN_REQUIRED",
                "expired key=URLSECRET Authorization: Bearer BEARERSECRET",
            )

    app = create_app(
        settings(tmp_path),
        tcp_probe=lambda *_: True,
        public_account_provider=FailingProvider(),
    )
    client = TestClient(app)
    response = client.get("/v1/public-accounts/示例公众号/recent?limit=20", headers=auth())

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "LOGIN_REQUIRED"
    assert "URLSECRET" not in response.text
    assert "BEARERSECRET" not in response.text


def test_recent_endpoint_without_provider_is_explicitly_unavailable(tmp_path: Path):
    client = TestClient(create_app(settings(tmp_path), tcp_probe=lambda *_: True))
    response = client.get("/v1/public-accounts/示例公众号/recent?limit=20", headers=auth())
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "HISTORY_SURFACE_UNAVAILABLE"
