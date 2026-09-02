import json

from app.account_index import PublicAccountIndex


def test_account_index_persists_name_to_public_biz_across_instances_with_private_file_mode(tmp_path):
    index = PublicAccountIndex(tmp_path)
    index.remember("  示例公众号  ", "BIZ_PUBLIC")

    restored = PublicAccountIndex(tmp_path)
    assert restored.resolve("示例公众号") == "BIZ_PUBLIC"
    assert restored.resolve("  示例公众号  ") == "BIZ_PUBLIC"

    path = tmp_path / ".public-account-index.json"
    assert path.exists()
    assert path.stat().st_mode & 0o777 == 0o600
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert "BIZ_PUBLIC" in path.read_text(encoding="utf-8")
    for forbidden in ["key", "pass_ticket", "appmsg_token", "cookie", "token"]:
        assert forbidden not in json.dumps(payload).lower()


def test_account_index_normalizes_name_and_handles_corrupt_file_without_throwing(tmp_path):
    path = tmp_path / ".public-account-index.json"
    path.write_text("not-json", encoding="utf-8")
    index = PublicAccountIndex(tmp_path)
    assert index.resolve("Example Account") is None

    index.remember("Ｅｘａｍｐｌｅ　Ａｃｃｏｕｎｔ", "BIZ_ONE")
    assert index.resolve("example account") == "BIZ_ONE"


def test_account_index_rejects_invalid_values_without_writing_them(tmp_path):
    index = PublicAccountIndex(tmp_path)
    for name, biz in [("", "BIZ"), ("name", ""), ("name\n", "BIZ"), ("name", "BAD BIZ")]:
        try:
            index.remember(name, biz)
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError")
    assert index.resolve("name") is None
