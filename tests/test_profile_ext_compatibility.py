import json
from urllib.parse import parse_qs, urlsplit

import pytest

from app.history_pager import ProfileExtAuthError, build_page_url, parse_profile_ext_page
from app.history_seed import HistorySeed


def seed_without_compat_flags():
    return HistorySeed(
        _raw_url=(
            "https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz=BIZ"
            "&uin=UIN&key=KEY&pass_ticket=PASS&appmsg_token=TOKEN"
        ),
        title="history",
        last_visit_time=1,
    )


def test_page_builder_forces_wechat_compatibility_flags():
    query = parse_qs(urlsplit(build_page_url(seed_without_compat_flags(), 0, 10)).query, keep_blank_values=True)
    assert query["scene"] == ["124"]
    assert query["x5"] == ["1"]
    assert query["wxtoken"] == [""]
    assert query["f"] == ["json"]
    assert query["count"] == ["10"]


def test_no_session_errmsg_is_classified_as_auth_failure_without_echoing_payload():
    payload = json.dumps({
        "ret": -2,
        "errmsg": "no session KEY_SHOULD_NOT_LEAK",
        "general_msg_list": "{}",
    }).encode()
    with pytest.raises(ProfileExtAuthError) as exc:
        parse_profile_ext_page(payload, "Example")
    assert "KEY_SHOULD_NOT_LEAK" not in str(exc.value)
