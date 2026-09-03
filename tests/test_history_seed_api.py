import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.history_seed import probe_history_seed_status
from app.main import create_app


def write_history(path: Path, url: str, last_visit_time: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE urls (id INTEGER PRIMARY KEY, url TEXT, title TEXT, visit_count INTEGER, typed_count INTEGER, last_visit_time INTEGER, hidden INTEGER)"
        )
        connection.execute(
            "INSERT INTO urls VALUES (?, ?, ?, ?, ?, ?, ?)",
            (1, url, "history", 1, 0, last_visit_time, 0),
        )
        connection.commit()
    finally:
        connection.close()


def make_settings(state_dir: Path) -> Settings:
    return Settings(
        control_token="secret",
        codespace_name="musical-guide",
        state_dir=state_dir,
        wechat_host="127.0.0.1",
        wechat_port=3001,
        probe_timeout=0.1,
    )


def auth() -> dict[str, str]:
    return {"Authorization": "Bearer secret"}


def test_probe_history_seed_status_selects_multitab_candidate_and_redacts_profile_suffix(tmp_path: Path):
    web = tmp_path / ".xwechat" / "radium" / "web" / "profiles"
    write_history(
        web / "web_shell" / "History",
        "https://mp.weixin.qq.com/s/not-a-history",
        900,
    )
    write_history(
        web / "multitab_1234567890abcdef" / "History",
        "https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz=BIZSECRET&key=KEYSECRET&pass_ticket=PASSSECRET",
        800,
    )

    result = probe_history_seed_status(tmp_path)
    rendered = json.dumps(result)

    assert result["present"] is True
    assert result["candidate_count"] == 1
    assert result["selected_profile"] == "multitab_<redacted>"
    assert result["selected_history"] == ".xwechat/radium/web/profiles/multitab_<redacted>/History"
    assert result["seed"]["host"] == "mp.weixin.qq.com"
    assert result["seed"]["path"] == "/mp/profile_ext"
    assert result["seed"]["query_keys_present"]["key"] is True
    for secret in ["1234567890abcdef", "BIZSECRET", "KEYSECRET", "PASSSECRET"]:
        assert secret not in rendered


def test_probe_history_seed_status_returns_absent_without_matching_seed(tmp_path: Path):
    result = probe_history_seed_status(tmp_path)
    assert result == {
        "present": False,
        "candidate_count": 0,
        "selected_profile": None,
        "selected_history": None,
        "seed": None,
        "sensitive_values_returned": False,
    }


def test_history_seed_status_api_requires_bearer_and_returns_only_safe_summary(tmp_path: Path):
    web = tmp_path / ".xwechat" / "radium" / "web" / "profiles"
    write_history(
        web / "multitab_deadbeef" / "History",
        "https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz=BIZSECRET&uin=UINSECRET&key=KEYSECRET&pass_ticket=PASSSECRET&appmsg_token=TOKENSECRET",
        999,
    )
    client = TestClient(create_app(make_settings(tmp_path), tcp_probe=lambda *_: True))

    assert client.get("/v1/wechat/history-seed-status").status_code == 401
    response = client.get("/v1/wechat/history-seed-status", headers=auth())
    assert response.status_code == 200
    rendered = response.text
    assert response.json()["present"] is True
    assert response.json()["sensitive_values_returned"] is False
    for secret in ["deadbeef", "BIZSECRET", "UINSECRET", "KEYSECRET", "PASSSECRET", "TOKENSECRET"]:
        assert secret not in rendered


def test_history_seed_handoff_script_uses_local_token_without_printing_it():
    root = Path(__file__).resolve().parents[1]
    script = (root / "scripts/probe-history-seed.sh").read_text(encoding="utf-8")
    assert "WECHAT_CONTROL_FORCE_RESTART=1 bash scripts/start-control-api.sh" in script
    assert "/v1/wechat/history-seed-status" in script
    assert "ensure_control_token" in script
    assert "cat state/.control-token" not in script
    assert "echo $token" not in script
    assert "print(token)" not in script
