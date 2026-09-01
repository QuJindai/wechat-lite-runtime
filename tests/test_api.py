from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def make_settings(tmp_path: Path, token: str = "secret", codespace_name: str | None = "silver-potato") -> Settings:
    return Settings(
        control_token=token,
        codespace_name=codespace_name,
        state_dir=tmp_path,
        wechat_host="wechat",
        wechat_port=3001,
        probe_timeout=0.1,
    )


def auth(token: str = "secret") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_health_is_public(tmp_path: Path):
    client = TestClient(create_app(make_settings(tmp_path), tcp_probe=lambda *_: True))
    assert client.get("/healthz").json() == {"status": "ok"}


def test_status_requires_bearer_token(tmp_path: Path):
    client = TestClient(create_app(make_settings(tmp_path), tcp_probe=lambda *_: True))
    response = client.get("/v1/runtime/status")
    assert response.status_code == 401
    assert response.json()["detail"] == "unauthorized"


def test_status_rejects_wrong_bearer_token(tmp_path: Path):
    client = TestClient(create_app(make_settings(tmp_path), tcp_probe=lambda *_: True))
    response = client.get("/v1/runtime/status", headers=auth("wrong"))
    assert response.status_code == 401
    assert response.json()["detail"] == "unauthorized"


def test_status_reports_runtime(tmp_path: Path):
    (tmp_path / "profile.db").write_bytes(b"1234")
    client = TestClient(create_app(make_settings(tmp_path), tcp_probe=lambda *_: True))
    response = client.get("/v1/runtime/status", headers=auth())
    assert response.status_code == 200
    assert response.json() == {
        "codespace_name": "silver-potato",
        "wechat_web_ready": True,
        "ui_url": "https://silver-potato-3001.app.github.dev",
        "session_storage": {
            "initialized": True,
            "file_count": 1,
            "total_bytes": 4,
        },
    }


def test_ui_endpoint_returns_forwarded_url(tmp_path: Path):
    client = TestClient(create_app(make_settings(tmp_path), tcp_probe=lambda *_: False))
    response = client.get("/v1/runtime/ui", headers=auth())
    assert response.status_code == 200
    assert response.json() == {"ui_url": "https://silver-potato-3001.app.github.dev"}


def test_ui_endpoint_allows_non_codespace_runtime(tmp_path: Path):
    client = TestClient(
        create_app(make_settings(tmp_path, codespace_name=None), tcp_probe=lambda *_: False)
    )
    response = client.get("/v1/runtime/ui", headers=auth())
    assert response.status_code == 200
    assert response.json() == {"ui_url": None}


def test_missing_configured_token_is_service_error(tmp_path: Path):
    client = TestClient(create_app(make_settings(tmp_path, token=""), tcp_probe=lambda *_: True))
    response = client.get("/v1/runtime/status", headers=auth("anything"))
    assert response.status_code == 503
    assert response.json()["detail"] == "control_token_not_configured"
