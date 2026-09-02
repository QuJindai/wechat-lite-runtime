import json
from urllib.parse import parse_qs, urlsplit

import pytest

from app.history_pager import (
    ProfileExtAuthError,
    ProfileExtResponseError,
    build_page_url,
    parse_profile_ext_page,
)
from app.history_seed import HistorySeed
from app.providers import AuthenticatedHistoryProvider, ProviderError


def seed(scene: str = "999") -> HistorySeed:
    return HistorySeed(
        _raw_url=(
            "https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz=BIZ_PUBLIC"
            "&uin=UIN_SECRET&key=KEY_SECRET&pass_ticket=PASS_SECRET"
            f"&scene={scene}"
        ),
        title="history",
        last_visit_time=1,
    )


def test_page_url_forces_scene_124_for_history_getmsg():
    url = build_page_url(seed("999"), offset=10, count=10)
    query = parse_qs(urlsplit(url).query)
    assert query["action"] == ["getmsg"]
    assert query["scene"] == ["124"]
    assert query["offset"] == ["10"]
    assert query["count"] == ["10"]
    assert query["f"] == ["json"]
    assert query["is_ok"] == ["1"]
    assert query["key"] == ["KEY_SECRET"]


def test_parser_maps_ret_minus_3_to_auth_error_without_echoing_payload():
    payload = json.dumps({"ret": -3, "errmsg": "expired key=KEY_SECRET"}).encode()
    with pytest.raises(ProfileExtAuthError) as exc:
        parse_profile_ext_page(payload, "Example")
    assert "KEY_SECRET" not in str(exc.value)


def test_parser_maps_other_nonzero_ret_to_response_error_without_echoing_payload():
    payload = json.dumps({"ret": -1, "errmsg": "backend PASS_SECRET"}).encode()
    with pytest.raises(ProfileExtResponseError) as exc:
        parse_profile_ext_page(payload, "Example")
    assert "PASS_SECRET" not in str(exc.value)


class OnePageTransport:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def get(self, url: str) -> bytes:
        return self.payload


def test_provider_maps_profile_ext_auth_error_to_login_required():
    provider = AuthenticatedHistoryProvider(
        None,
        OnePageTransport(json.dumps({"ret": -3, "errmsg": "PRIVATE"}).encode()),
        seed=seed(),
    )
    with pytest.raises(ProviderError) as exc:
        provider.recent_articles("Example", 20)
    assert exc.value.code == "LOGIN_REQUIRED"
    assert "PRIVATE" not in str(exc.value)


def test_provider_maps_other_profile_ext_error_to_history_unavailable():
    provider = AuthenticatedHistoryProvider(
        None,
        OnePageTransport(json.dumps({"ret": -1, "errmsg": "PRIVATE"}).encode()),
        seed=seed(),
    )
    with pytest.raises(ProviderError) as exc:
        provider.recent_articles("Example", 20)
    assert exc.value.code == "HISTORY_SURFACE_UNAVAILABLE"
    assert "PRIVATE" not in str(exc.value)
