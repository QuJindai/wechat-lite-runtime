from __future__ import annotations

import sqlite3
from pathlib import Path

from app.webview_probe import (
    classify_webview_container,
    inspect_sqlite_schema,
    probe_webview_state,
    scan_fixed_markers,
)


def build_web_root(tmp_path: Path) -> Path:
    web_root = tmp_path / ".xwechat" / "radium" / "web"
    profile = web_root / "profiles" / "multitab_0123456789abcdef0123456789abcdef"
    leveldb = profile / "Local Storage" / "leveldb"
    leveldb.mkdir(parents=True)
    (leveldb / "000003.log").write_bytes(
        b"prefix https://mp.weixin.qq.com/mp/profile_ext __biz=abc pass_ticket=SECRET "
        b"appmsg_token=TOKEN suffix https://mp.weixin.qq.com/s/abc"
    )
    (profile / "Cache" / "Cache_Data").mkdir(parents=True)
    (profile / "Cache" / "Cache_Data" / "data_0").write_bytes(
        b"https://mp.weixin.qq.com/s/xyz"
    )
    return web_root


def create_cookie_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE cookies (host_key TEXT, name TEXT, encrypted_value BLOB, expires_utc INTEGER)"
        )
        conn.execute(
            "INSERT INTO cookies(host_key, name, encrypted_value, expires_utc) VALUES (?, ?, ?, ?)",
            (".mp.weixin.qq.com", "pass_ticket", b"super-secret-cookie-value", 123),
        )
        conn.commit()
    finally:
        conn.close()


def test_classifies_known_webview_containers(tmp_path: Path):
    web_root = build_web_root(tmp_path)
    profile = web_root / "profiles" / "multitab_0123456789abcdef0123456789abcdef"
    cookies = profile / "Network" / "Cookies"
    create_cookie_db(cookies)

    assert classify_webview_container(profile, web_root) == "profile_root"
    assert classify_webview_container(profile / "Local Storage" / "leveldb", web_root) == "local_storage_leveldb"
    assert classify_webview_container(cookies, web_root) == "cookie_sqlite"
    assert classify_webview_container(profile / "History", web_root) == "history_sqlite"
    assert classify_webview_container(profile / "Cache", web_root) == "cache_store"


def test_fixed_marker_scan_returns_counts_only(tmp_path: Path):
    target = tmp_path / "sample.bin"
    target.write_bytes(
        b"https://mp.weixin.qq.com/a __biz=x pass_ticket=SECRET pass_ticket=SECOND appmsg_token=T"
    )

    result = scan_fixed_markers(
        target,
        (b"mp.weixin.qq.com", b"__biz", b"pass_ticket", b"appmsg_token"),
    )

    assert result == {
        "mp.weixin.qq.com": 1,
        "__biz": 1,
        "pass_ticket": 2,
        "appmsg_token": 1,
    }
    rendered = repr(result)
    assert "SECRET" not in rendered
    assert "SECOND" not in rendered


def test_sqlite_schema_never_reads_rows(tmp_path: Path):
    db = tmp_path / "Cookies"
    create_cookie_db(db)

    result = inspect_sqlite_schema(db)

    assert result["status"] == "ok"
    assert result["tables"] == [
        {
            "name": "cookies",
            "columns": ["host_key", "name", "encrypted_value", "expires_utc"],
        }
    ]
    rendered = repr(result)
    assert "super-secret-cookie-value" not in rendered
    assert "pass_ticket" not in rendered
    assert ".mp.weixin.qq.com" not in rendered


def test_probe_webview_state_sanitizes_profile_ids_and_exposes_no_values(tmp_path: Path):
    web_root = build_web_root(tmp_path)
    profile = web_root / "profiles" / "multitab_0123456789abcdef0123456789abcdef"
    cookies = profile / "Network" / "Cookies"
    create_cookie_db(cookies)

    result = probe_webview_state(tmp_path)

    assert result["web_root_present"] is True
    assert result["sensitive_values_returned"] is False
    assert result["profiles"]
    profile_result = result["profiles"][0]
    assert profile_result["profile"] == "multitab_<redacted>"
    assert "0123456789abcdef0123456789abcdef" not in repr(result)

    classes = {container["class"] for container in profile_result["containers"]}
    assert "local_storage_leveldb" in classes
    assert "cookie_sqlite" in classes
    assert "cache_store" in classes

    marker_totals = result["marker_totals"]
    assert marker_totals["mp.weixin.qq.com"] >= 2
    assert marker_totals["__biz"] >= 1
    assert marker_totals["pass_ticket"] >= 1
    assert marker_totals["appmsg_token"] >= 1

    rendered = repr(result)
    assert "super-secret-cookie-value" not in rendered
    assert "SECRET" not in rendered
    assert "TOKEN" not in rendered


def test_probe_missing_web_root_is_explicit(tmp_path: Path):
    result = probe_webview_state(tmp_path)

    assert result == {
        "web_root_present": False,
        "profiles": [],
        "marker_totals": {
            "mp.weixin.qq.com": 0,
            "__biz": 0,
            "pass_ticket": 0,
            "appmsg_token": 0,
        },
        "sensitive_values_returned": False,
    }
