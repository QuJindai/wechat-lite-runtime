from app.runtime import summarize_state_dir


def test_public_account_index_alone_does_not_initialize_wechat_profile(tmp_path):
    (tmp_path / ".public-account-index.json").write_text('{"version":1,"accounts":{}}', encoding="utf-8")
    assert summarize_state_dir(tmp_path) == {
        "initialized": False,
        "file_count": 0,
        "total_bytes": 0,
    }
