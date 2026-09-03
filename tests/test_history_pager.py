import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from app.history_pager import build_page_url, parse_profile_ext_page
from app.history_seed import HistorySeed


FIXTURES = Path(__file__).parent / "fixtures" / "profile_ext"


def private_seed() -> HistorySeed:
    return HistorySeed(
        _raw_url=(
            "https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz=BIZSECRET"
            "&uin=UINSECRET&key=KEYSECRET&pass_ticket=PASSSECRET"
            "&appmsg_token=TOKENSECRET&scene=124"
        ),
        title="history",
        last_visit_time=1,
    )


def test_build_page_url_preserves_private_context_and_changes_only_paging_controls():
    url = build_page_url(private_seed(), offset=10, count=10)
    query = parse_qs(urlsplit(url).query)

    assert urlsplit(url).hostname == "mp.weixin.qq.com"
    assert urlsplit(url).path == "/mp/profile_ext"
    assert query["action"] == ["getmsg"]
    assert query["offset"] == ["10"]
    assert query["count"] == ["10"]
    assert query["f"] == ["json"]
    assert query["__biz"] == ["BIZSECRET"]
    assert query["uin"] == ["UINSECRET"]
    assert query["key"] == ["KEYSECRET"]
    assert query["pass_ticket"] == ["PASSSECRET"]
    assert query["appmsg_token"] == ["TOKENSECRET"]


def test_build_page_url_rejects_non_wechat_seed_without_echoing_secret():
    seed = HistorySeed(
        _raw_url="https://example.com/mp/profile_ext?key=DO_NOT_ECHO",
        title="bad",
        last_visit_time=1,
    )
    with pytest.raises(ValueError) as exc:
        build_page_url(seed, offset=0)
    assert "DO_NOT_ECHO" not in str(exc.value)


def test_parse_profile_ext_page_normalizes_main_and_multi_articles():
    payload = (FIXTURES / "page0.json").read_bytes()

    records, can_continue = parse_profile_ext_page(payload, "Example Account")

    assert can_continue is True
    assert [record.title for record in records] == ["Article 1", "Article 1B", "Article 2"]
    assert all(record.account_name == "Example Account" for record in records)
    assert all(record.biz == "BIZPUB" for record in records)
    assert all(record.verified_account is False for record in records)
    assert all(record.published_at is not None for record in records)
    rendered = json.dumps([record.to_dict() for record in records], ensure_ascii=False)
    for secret in ["SECRET1", "SECRET1B", "SECRET2", "PASS1"]:
        assert secret not in rendered
    assert records[0].canonical_url == "https://mp.weixin.qq.com/s?__biz=BIZPUB&mid=1000&idx=1&sn=SN1"
    assert records[1].position == 2


def test_parse_profile_ext_page_reads_terminal_continuation_flag():
    payload = (FIXTURES / "page10.json").read_bytes()
    records, can_continue = parse_profile_ext_page(payload, "Example Account")

    assert can_continue is False
    assert len(records) == 1
    assert records[0].title == "Article 3"


def test_parse_profile_ext_page_rejects_malformed_payload_without_raw_echo():
    with pytest.raises(ValueError) as exc:
        parse_profile_ext_page(b'{"general_msg_list":"SECRET_PAYLOAD_NOT_JSON"}', "Example")
    assert "SECRET_PAYLOAD_NOT_JSON" not in str(exc.value)
