import os
import sqlite3
from pathlib import Path

from app.history_seed import locate_history_seed


def make_history_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE urls (id INTEGER PRIMARY KEY, url TEXT, title TEXT, visit_count INTEGER, typed_count INTEGER, last_visit_time INTEGER, hidden INTEGER)"
        )
        rows = [
            (1, "https://example.com/mp/profile_ext?action=home&key=evil", "wrong host", 1, 0, 100, 0),
            (2, "https://mp.weixin.qq.com/s/abc", "article", 1, 0, 200, 0),
            (3, "https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz=BIZ_OLD&uin=UIN_OLD&key=KEY_OLD&pass_ticket=PASS_OLD", "old history", 1, 0, 300, 0),
            (4, "https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz=BIZ_NEW&uin=UIN_NEW&key=KEY_NEW&pass_ticket=PASS_NEW&appmsg_token=TOKEN_NEW", "new history", 1, 0, 500, 0),
        ]
        connection.executemany("INSERT INTO urls VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
        connection.commit()
    finally:
        connection.close()


def test_locate_history_seed_selects_newest_wechat_profile_ext_url(tmp_path: Path):
    history = tmp_path / "History"
    make_history_db(history)

    seed = locate_history_seed(history)

    assert seed is not None
    assert seed.last_visit_time == 500
    assert "BIZ_NEW" in seed._raw_url
    assert "BIZ_OLD" not in seed._raw_url


def test_history_seed_safe_summary_never_exposes_auth_values_or_raw_query(tmp_path: Path):
    history = tmp_path / "History"
    make_history_db(history)

    seed = locate_history_seed(history)
    assert seed is not None
    summary = seed.safe_summary()
    rendered = repr(summary) + repr(seed)

    assert summary["present"] is True
    assert summary["host"] == "mp.weixin.qq.com"
    assert summary["path"] == "/mp/profile_ext"
    assert summary["query_keys_present"] == {
        "__biz": True,
        "pass_ticket": True,
        "appmsg_token": True,
        "key": True,
        "uin": True,
    }
    assert len(summary["seed_fingerprint"]) == 16
    for secret in ["BIZ_NEW", "UIN_NEW", "KEY_NEW", "PASS_NEW", "TOKEN_NEW"]:
        assert secret not in rendered
    assert "?" not in str(summary["path"])


def test_locate_history_seed_returns_none_for_missing_or_irrelevant_history(tmp_path: Path):
    assert locate_history_seed(tmp_path / "missing") is None

    history = tmp_path / "History"
    connection = sqlite3.connect(history)
    try:
        connection.execute(
            "CREATE TABLE urls (id INTEGER PRIMARY KEY, url TEXT, title TEXT, visit_count INTEGER, typed_count INTEGER, last_visit_time INTEGER, hidden INTEGER)"
        )
        connection.execute(
            "INSERT INTO urls VALUES (1, 'https://mp.weixin.qq.com/s/only-article', 'article', 1, 0, 100, 0)"
        )
        connection.commit()
    finally:
        connection.close()

    assert locate_history_seed(history) is None


def test_history_seed_locator_opens_history_read_only(tmp_path: Path):
    history = tmp_path / "History"
    make_history_db(history)
    before = history.read_bytes()
    os.chmod(history, 0o444)

    seed = locate_history_seed(history)

    assert seed is not None
    assert history.read_bytes() == before
