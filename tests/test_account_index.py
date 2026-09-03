import json
import os
from concurrent.futures import ThreadPoolExecutor

from app.account_index import PublicAccountIndex
from app.public_accounts import VerifiedAccountIdentity


def identity(
    *,
    account_name: str = "示例公众号",
    biz: str = "BIZ_PUBLIC",
    seed_url: str = "https://mp.weixin.qq.com/s/public-seed",
) -> VerifiedAccountIdentity:
    return VerifiedAccountIdentity(
        account_name=account_name,
        biz=biz,
        provenance="public_seed_article",
        canonical_seed_url=seed_url,
    )


def test_account_index_persists_verified_seed_identity_across_instances(tmp_path):
    index = PublicAccountIndex(tmp_path)
    index.remember_verified(identity(account_name="  示例公众号  "))

    restored = PublicAccountIndex(tmp_path)
    assert restored.resolve_verified("示例公众号") == identity()
    assert restored.resolve_verified("  示例公众号  ") == identity()

    path = tmp_path / ".public-account-index.json"
    assert path.exists()
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == {
        "version": 2,
        "accounts": {
            "示例公众号": {
                "account_name": "示例公众号",
                "biz": "BIZ_PUBLIC",
                "provenance": "public_seed_article",
                "canonical_seed_url": "https://mp.weixin.qq.com/s/public-seed",
            }
        },
    }
    for forbidden in ["key", "pass_ticket", "appmsg_token", "cookie", "token"]:
        assert forbidden not in json.dumps(payload).lower()


def test_account_index_normalizes_name_and_handles_corrupt_file_without_throwing(tmp_path):
    path = tmp_path / ".public-account-index.json"
    path.write_text("not-json", encoding="utf-8")
    index = PublicAccountIndex(tmp_path)
    assert index.resolve_verified("Example Account") is None

    index.remember_verified(identity(account_name="Ｅｘａｍｐｌｅ　Ａｃｃｏｕｎｔ", biz="BIZ_ONE"))
    restored = index.resolve_verified("example account")
    assert restored is not None
    assert restored.account_name == "Example Account"
    assert restored.biz == "BIZ_ONE"


def test_legacy_v1_entries_are_unverified_and_read_only(tmp_path):
    path = tmp_path / ".public-account-index.json"
    legacy = '{"version":1,"accounts":{"示例公众号":"BIZ_LEGACY"}}\n'
    path.write_text(legacy, encoding="utf-8")

    assert PublicAccountIndex(tmp_path).resolve_verified("示例公众号") is None
    assert path.read_text(encoding="utf-8") == legacy


def test_malformed_v2_entries_are_ignored(tmp_path):
    path = tmp_path / ".public-account-index.json"
    path.write_text(
        json.dumps(
            {
                "version": 2,
                "accounts": {
                    "bad provenance": {
                        "account_name": "Bad Provenance",
                        "biz": "BIZ_ONE",
                        "provenance": "caller_input",
                        "canonical_seed_url": "https://mp.weixin.qq.com/s/one",
                    },
                    "bad url": {
                        "account_name": "Bad URL",
                        "biz": "BIZ_TWO",
                        "provenance": "public_seed_article",
                        "canonical_seed_url": "https://example.com/s/two",
                    },
                    "bad shape": "BIZ_THREE",
                },
            }
        ),
        encoding="utf-8",
    )

    index = PublicAccountIndex(tmp_path)
    assert index.resolve_verified("Bad Provenance") is None
    assert index.resolve_verified("Bad URL") is None
    assert index.resolve_verified("Bad Shape") is None


def test_unverified_name_biz_write_api_is_not_available(tmp_path):
    index = PublicAccountIndex(tmp_path)
    assert not hasattr(index, "remember")
    assert not hasattr(index, "resolve")


def test_concurrent_verified_writes_are_merged_without_temp_file_collisions(tmp_path):
    index = PublicAccountIndex(tmp_path)
    identities = [
        identity(
            account_name=f"并发公众号 {position}",
            biz=f"BIZ_{position}",
            seed_url=f"https://mp.weixin.qq.com/s/seed-{position}",
        )
        for position in range(50)
    ]

    with ThreadPoolExecutor(max_workers=16) as executor:
        list(executor.map(index.remember_verified, identities))

    restored = PublicAccountIndex(tmp_path)
    assert all(
        restored.resolve_verified(item.account_name) == item
        for item in identities
    )
    assert list(tmp_path.glob(".public-account-index.json.tmp.*")) == []
