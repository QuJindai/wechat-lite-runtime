from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def settings(tmp_path: Path) -> Settings:
    return Settings(
        control_token="secret",
        codespace_name="test-space",
        state_dir=tmp_path,
        wechat_host="127.0.0.1",
        wechat_port=3001,
        probe_timeout=0.1,
    )


def auth() -> dict[str, str]:
    return {"Authorization": "Bearer secret"}


def test_webview_probe_requires_bearer(tmp_path: Path):
    client = TestClient(create_app(settings(tmp_path), tcp_probe=lambda *_: True))

    response = client.get("/v1/wechat/webview-probe")

    assert response.status_code == 401


def test_webview_probe_missing_root_is_explicit(tmp_path: Path):
    client = TestClient(create_app(settings(tmp_path), tcp_probe=lambda *_: True))

    response = client.get("/v1/wechat/webview-probe", headers=auth())

    assert response.status_code == 200
    assert response.json() == {
        "web_root_present": False,
        "profiles": [],
        "marker_totals": {
            "mp.weixin.qq.com": 0,
            "__biz": 0,
            "pass_ticket": 0,
            "appmsg_token": 0,
        },
        "truncated": False,
        "truncation_reasons": [],
        "sensitive_values_returned": False,
    }


def test_webview_probe_api_never_returns_cookie_rows(tmp_path: Path):
    profile = (
        tmp_path
        / ".xwechat"
        / "radium"
        / "web"
        / "profiles"
        / "multitab_abcdefabcdefabcdefabcdefabcdefab"
    )
    cookie_db = profile / "Network" / "Cookies"
    cookie_db.parent.mkdir(parents=True)
    conn = sqlite3.connect(cookie_db)
    try:
        conn.execute("CREATE TABLE cookies (host_key TEXT, name TEXT, encrypted_value BLOB)")
        conn.execute(
            "INSERT INTO cookies VALUES (?, ?, ?)",
            (".mp.weixin.qq.com", "pass_ticket", b"DO-NOT-RETURN-THIS"),
        )
        conn.commit()
    finally:
        conn.close()

    leveldb = profile / "Local Storage" / "leveldb"
    leveldb.mkdir(parents=True)
    (leveldb / "000001.log").write_bytes(
        b"mp.weixin.qq.com __biz pass_ticket appmsg_token=PRIVATE"
    )

    client = TestClient(create_app(settings(tmp_path), tcp_probe=lambda *_: True))
    response = client.get("/v1/wechat/webview-probe", headers=auth())

    assert response.status_code == 200
    body = response.json()
    assert body["web_root_present"] is True
    assert body["sensitive_values_returned"] is False
    rendered = response.text
    assert "DO-NOT-RETURN-THIS" not in rendered
    assert "PRIVATE" not in rendered
    assert ".mp.weixin.qq.com" not in rendered
    assert "abcdefabcdefabcdefabcdefabcdefab" not in rendered


def test_webview_probe_api_handles_corrupt_history_database_without_500(tmp_path: Path):
    history = (
        tmp_path
        / ".xwechat"
        / "radium"
        / "web"
        / "profiles"
        / "multitab_abcdefabcdefabcdefabcdefabcdefab"
        / "History"
    )
    history.parent.mkdir(parents=True)
    history.write_bytes(b"SQLite format 3\x00" + b"PRIVATE_CORRUPT_BYTES" * 8)

    client = TestClient(create_app(settings(tmp_path), tcp_probe=lambda *_: True))
    response = client.get("/v1/wechat/webview-probe", headers=auth())

    assert response.status_code == 200
    assert "PRIVATE_CORRUPT_BYTES" not in response.text
    schema = response.json()["profiles"][0]["containers"][0]["sqlite_schema"]
    assert schema == {"status": "corrupt", "tables": []}
