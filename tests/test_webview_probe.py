from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import app.webview_probe as webview_probe_module
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


def test_sqlite_schema_redacts_unknown_table_and_column_identifiers(tmp_path: Path):
    db = tmp_path / "History"
    conn = sqlite3.connect(db)
    try:
        conn.execute('CREATE TABLE "SECRET_TABLE_456" ("TOKEN_COLUMN_789" TEXT)')
        conn.commit()
    finally:
        conn.close()

    result = inspect_sqlite_schema(db)

    assert result["status"] == "ok"
    assert "SECRET_TABLE_456" not in repr(result)
    assert "TOKEN_COLUMN_789" not in repr(result)
    assert result["tables"] == [
        {"name": "<redacted-table-1>", "columns": ["<redacted-column-1>"]}
    ]


def test_sqlite_schema_reports_corrupt_database_without_raising_or_echoing_bytes(tmp_path: Path):
    db = tmp_path / "History"
    db.write_bytes(b"SQLite format 3\x00" + b"PRIVATE_CORRUPT_BYTES" * 8)

    result = inspect_sqlite_schema(db)

    assert result == {"status": "corrupt", "tables": []}
    assert "PRIVATE_CORRUPT_BYTES" not in repr(result)


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


def test_probe_webview_state_redacts_unknown_path_segments(tmp_path: Path):
    web_root = build_web_root(tmp_path)
    profile = web_root / "profiles" / "multitab_0123456789abcdef0123456789abcdef"
    private_cache = profile / "PRIVATE_ACCOUNT_123" / "Cache"
    private_cache.mkdir(parents=True)
    (private_cache / "data_0").write_bytes(b"mp.weixin.qq.com")

    result = probe_webview_state(tmp_path)

    assert "PRIVATE_ACCOUNT_123" not in repr(result)
    relative_paths = [
        container["relative_path"]
        for item in result["profiles"]
        for container in item["containers"]
    ]
    assert any("<redacted>/Cache" in path for path in relative_paths)


@pytest.mark.parametrize(
    ("limits", "reason"),
    [
        ({"max_files": 1}, "file_count_budget"),
        ({"max_total_bytes": 1}, "total_byte_budget"),
        ({"max_directories": 1}, "directory_budget"),
        ({"max_scan_seconds": 0.000000001}, "scan_time_budget"),
    ],
)
def test_probe_webview_state_reports_global_budget_truncation(tmp_path: Path, limits, reason, monkeypatch):
    build_web_root(tmp_path)
    if reason == "scan_time_budget":
        ticks = iter([0.0, 1.0])
        monkeypatch.setattr("app.webview_probe.time.monotonic", lambda: next(ticks, 1.0))
        limits = {"max_scan_seconds": 0.5}

    result = probe_webview_state(tmp_path, **limits)

    assert result["truncated"] is True
    assert reason in result["truncation_reasons"]
    assert result["sensitive_values_returned"] is False


def test_probe_webview_state_enforces_elapsed_budget_during_result_assembly(
    tmp_path: Path,
    monkeypatch,
):
    profiles_root = tmp_path / ".xwechat" / "radium" / "web" / "profiles"
    (profiles_root / "multitab_00000000000000000000000000000000").mkdir(parents=True)

    class AssemblyDeadlineClock:
        def __init__(self):
            self.calls = 0

        def monotonic(self):
            self.calls += 1
            return 0.0 if self.calls <= 8 else 2.0

    clock = AssemblyDeadlineClock()
    monkeypatch.setattr(webview_probe_module, "time", clock)

    result = probe_webview_state(tmp_path, max_scan_seconds=1.0)

    assert clock.calls >= 9
    assert result["truncated"] is True
    assert "scan_time_budget" in result["truncation_reasons"]


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
        "truncated": False,
        "truncation_reasons": [],
        "sensitive_values_returned": False,
    }
