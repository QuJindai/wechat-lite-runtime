from pathlib import Path

from fastapi.testclient import TestClient

from app.account_bootstrap import BootstrapResult, LaunchEvidence
from app.config import Settings
from app.credential_scanner import CaptureCandidate
from app.main import create_app


def settings(tmp_path: Path) -> Settings:
    return Settings(
        control_token="secret",
        codespace_name="musical-guide",
        state_dir=tmp_path,
        wechat_host="127.0.0.1",
        wechat_port=3001,
        probe_timeout=0.1,
    )


def auth() -> dict[str, str]:
    return {"Authorization": "Bearer secret"}


def safe_result() -> BootstrapResult:
    candidate = CaptureCandidate(
        request_url="https://mp.weixin.qq.com/mp/profile_ext?action=getmsg&__biz=BIZ_SECRET&uin=UIN_SECRET&key=KEY_SECRET&pass_ticket=PASS_SECRET",
        fields={"biz": "BIZ_SECRET", "uin": "UIN_SECRET", "key": "KEY_SECRET", "pass_ticket": "PASS_SECRET"},
        modified_at=100.0,
        source_root=".xwechat/radium/web",
    )
    return BootstrapResult(
        status="CREDENTIAL_OBSERVED",
        launch=LaunchEvidence(
            dispatch_attempted=True,
            exit_code=255,
            secondary_instance_exit=True,
            executable="/usr/bin/wechat",
            _target_url="https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz=BIZ_SECRET",
        ),
        credential_observed=True,
        candidate_count=1,
        poll_count=2,
        candidates=[candidate],
        scanner_truncated=False,
    )


def test_bootstrap_api_requires_bearer(tmp_path: Path):
    client = TestClient(
        create_app(settings(tmp_path), tcp_probe=lambda *_: True, account_bootstrapper=lambda biz: safe_result())
    )
    assert client.post("/v1/public-accounts/bootstrap", json={"biz": "BIZ_PUBLIC"}).status_code == 401


def test_bootstrap_api_returns_safe_result_and_never_raw_credentials(tmp_path: Path):
    seen = []

    def bootstrapper(biz: str) -> BootstrapResult:
        seen.append(biz)
        return safe_result()

    client = TestClient(
        create_app(settings(tmp_path), tcp_probe=lambda *_: True, account_bootstrapper=bootstrapper)
    )
    response = client.post(
        "/v1/public-accounts/bootstrap",
        json={"biz": "BIZ_PUBLIC"},
        headers=auth(),
    )

    assert response.status_code == 200
    assert seen == ["BIZ_PUBLIC"]
    payload = response.json()
    assert payload["status"] == "CREDENTIAL_OBSERVED"
    assert payload["credential_observed"] is True
    assert payload["candidate_count"] == 1
    assert payload["candidates"][0]["field_names"] == ["biz", "key", "pass_ticket", "uin"]
    assert payload["sensitive_values_returned"] is False
    rendered = response.text
    for secret in ["BIZ_SECRET", "UIN_SECRET", "KEY_SECRET", "PASS_SECRET"]:
        assert secret not in rendered


def test_bootstrap_api_validates_request_shape(tmp_path: Path):
    client = TestClient(
        create_app(settings(tmp_path), tcp_probe=lambda *_: True, account_bootstrapper=lambda biz: safe_result())
    )
    assert client.post("/v1/public-accounts/bootstrap", json={}, headers=auth()).status_code == 422


def test_bootstrap_api_maps_invalid_biz_without_echoing_value(tmp_path: Path):
    def bootstrapper(biz: str) -> BootstrapResult:
        raise ValueError("invalid_target_biz")

    client = TestClient(
        create_app(settings(tmp_path), tcp_probe=lambda *_: True, account_bootstrapper=bootstrapper)
    )
    response = client.post(
        "/v1/public-accounts/bootstrap",
        json={"biz": " BAD BIZ "},
        headers=auth(),
    )
    assert response.status_code == 400
    assert response.json()["detail"] == {"code": "INVALID_BIZ"}
    assert "BAD BIZ" not in response.text
