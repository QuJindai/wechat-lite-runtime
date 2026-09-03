from urllib.parse import parse_qs, quote, urlsplit

import pytest

from app.credential_scanner import CaptureCandidate, scan_credentials
from app.history_pager import build_page_url
from app.live_transport import history_seed_from_candidate
from app.providers import ProviderError


def modern_candidate() -> CaptureCandidate:
    url = (
        "https://mp.weixin.qq.com/mp/relatedsearchword?__biz=BIZ_MODERN&uin=UIN_SECRET"
        "&key=KEY_SECRET&pass_ticket=PASS_SECRET&appmsg_token=TOKEN_SECRET"
        "&mid=123&idx=1&sessionid=SESSION_SECRET"
    )
    return CaptureCandidate(
        request_url=url,
        fields={
            "biz": "BIZ_MODERN",
            "uin": "UIN_SECRET",
            "key": "KEY_SECRET",
            "pass_ticket": "PASS_SECRET",
            "appmsg_token": "TOKEN_SECRET",
            "mid": "123",
            "idx": "1",
            "sessionid": "SESSION_SECRET",
        },
        modified_at=100.0,
        source_root=".xwechat/radium/web",
    )


def test_relatedsearchword_candidate_can_seed_private_profile_ext_history_without_serializing_values():
    seed = history_seed_from_candidate(modern_candidate())
    parsed = urlsplit(seed._raw_url)
    query = parse_qs(parsed.query, keep_blank_values=True)

    assert parsed.hostname == "mp.weixin.qq.com"
    assert parsed.path == "/mp/profile_ext"
    assert query["__biz"] == ["BIZ_MODERN"]
    assert query["sessionid"] == ["SESSION_SECRET"]
    page = build_page_url(seed, 0, 10)
    page_query = parse_qs(urlsplit(page).query, keep_blank_values=True)
    assert page_query["appmsg_token"] == ["TOKEN_SECRET"]
    assert page_query["sessionid"] == ["SESSION_SECRET"]

    rendered = repr(seed)
    for secret in ["BIZ_MODERN", "UIN_SECRET", "KEY_SECRET", "PASS_SECRET", "TOKEN_SECRET", "SESSION_SECRET"]:
        assert secret not in rendered


def test_scanner_accepts_complete_percent_encoded_relatedsearchword_session(tmp_path):
    web_root = tmp_path / ".xwechat" / "radium" / "web"
    cache = web_root / "profiles" / "multitab_demo"
    cache.mkdir(parents=True)
    encoded = quote(modern_candidate().request_url, safe="").encode()
    (cache / "capture.bin").write_bytes(encoded)

    report = scan_credentials(
        "BIZ_MODERN",
        roots=[web_root],
        since_minutes=60,
        max_files=10,
        max_total_bytes=1024 * 1024,
        max_directories=20,
        max_scan_seconds=2,
    )

    assert len(report.candidates) == 1
    assert report.candidates[0].safe_summary()["field_names"] == [
        "appmsg_token", "biz", "idx", "key", "mid", "pass_ticket", "sessionid", "uin"
    ]
    assert report.safe_summary()["sensitive_values_returned"] is False


def test_incomplete_relatedsearchword_candidate_is_rejected():
    item = modern_candidate()
    item.fields.pop("sessionid")
    with pytest.raises(ProviderError) as exc:
        history_seed_from_candidate(item)
    assert exc.value.code == "HISTORY_SURFACE_UNAVAILABLE"
