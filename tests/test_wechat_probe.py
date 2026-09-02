from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.wechat_probe import classify_artifact, probe_state, sanitize_relative_root


def make_settings(state_dir: Path) -> Settings:
    return Settings(
        control_token="secret",
        codespace_name="probe-space",
        state_dir=state_dir,
        wechat_host="127.0.0.1",
        wechat_port=3001,
        probe_timeout=0.1,
    )


def test_classify_artifact_recognizes_only_structural_classes(tmp_path: Path):
    state = tmp_path / "state"
    cases = {
        state / "xwechat_files" / "wxid_abc123" / "msg.db": "xwechat_db",
        state / "webview" / "User Data" / "Default" / "Cache" / "data_1": "webview_cache",
        state / "webview" / "User Data" / "Default" / "Cookies": "cookie_store",
        state / "webview" / "Cache" / "mp.weixin.qq.com" / "index": "mp_weixin_trace",
        state / "misc" / "random.sqlite": "other_candidate",
        state / "misc" / "notes.txt": None,
    }

    for path, expected in cases.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("TOPSECRET", encoding="utf-8")
        assert classify_artifact(path, state) == expected


def test_sanitize_relative_root_redacts_account_like_segments(tmp_path: Path):
    state = tmp_path / "state"
    path = state / "xwechat_files" / "wxid_veryprivate123" / "Msg" / "msg.db"
    assert sanitize_relative_root(path, state) == "xwechat_files/<redacted>/Msg"


def test_sanitize_relative_root_redacts_all_unknown_segments(tmp_path: Path):
    state = tmp_path / "state"
    path = state / "PRIVATE_ACCOUNT_123" / "SECRET_FOLDER_456" / "random.sqlite"
    assert sanitize_relative_root(path, state) == "<redacted>/<redacted>"


def test_probe_state_returns_counts_and_never_file_contents(tmp_path: Path):
    state = tmp_path / "state"
    files = [
        state / "xwechat_files" / "wxid_private" / "msg.db",
        state / "webview" / "User Data" / "Default" / "Cookies",
        state / "webview" / "Cache" / "mp.weixin.qq.com" / "index",
    ]
    for path in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("TOPSECRET_COOKIE_VALUE", encoding="utf-8")

    result = probe_state(state)
    rendered = repr(result)

    assert result["state_initialized"] is True
    assert result["sensitive_values_returned"] is False
    assert {item["class"] for item in result["artifact_classes"]} == {
        "xwechat_db",
        "cookie_store",
        "mp_weixin_trace",
    }
    assert "TOPSECRET_COOKIE_VALUE" not in rendered
    assert "wxid_private" not in rendered


def test_probe_endpoint_is_bearer_protected_and_sanitized(tmp_path: Path):
    state = tmp_path / "state"
    cookie_file = state / "webview" / "User Data" / "Default" / "Cookies"
    cookie_file.parent.mkdir(parents=True)
    cookie_file.write_text("TOPSECRET_COOKIE_VALUE", encoding="utf-8")

    client = TestClient(create_app(make_settings(state), tcp_probe=lambda *_: True))
    assert client.get("/v1/wechat/probe").status_code == 401

    response = client.get(
        "/v1/wechat/probe",
        headers={"Authorization": "Bearer secret"},
    )
    assert response.status_code == 200
    assert response.json()["sensitive_values_returned"] is False
    assert "TOPSECRET_COOKIE_VALUE" not in response.text


def test_pending_acceptance_result_does_not_initialize_probe_state(tmp_path: Path):
    state = tmp_path / "state"
    state.mkdir()
    (state / ".v1-newest20-acceptance-latest.json").write_text("{}", encoding="utf-8")
    (state / ".v1-newest20-acceptance-latest.json.tmp.123").write_text("{}", encoding="utf-8")

    assert probe_state(state)["state_initialized"] is False
