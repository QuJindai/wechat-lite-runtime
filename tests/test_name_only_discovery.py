import json
from urllib.parse import parse_qs, urlsplit

import pytest

from app.credential_scanner import CaptureCandidate, ScanReport, scan_credentials
from app.launcher_bridge import SearchEvidence
from app.live_discovery import LiveDiscoveryService
from app.providers import ProviderError


def candidate(biz: str, suffix: str, modified_at: float) -> CaptureCandidate:
    return CaptureCandidate(
        request_url=(
            "https://mp.weixin.qq.com/mp/profile_ext?action=getmsg"
            f"&__biz={biz}&uin=UIN_{suffix}&key=KEY_{suffix}&pass_ticket=PASS_{suffix}"
        ),
        fields={
            "biz": biz,
            "uin": f"UIN_{suffix}",
            "key": f"KEY_{suffix}",
            "pass_ticket": f"PASS_{suffix}",
        },
        modified_at=modified_at,
        source_root=".xwechat/radium/web",
    )


def report(items):
    return ScanReport(
        scanned_files=2,
        scanned_bytes=200,
        roots=[".xwechat/radium/web"],
        candidates=list(items),
        duration_seconds=0.01,
        truncated=False,
        truncation_reasons=[],
    )


def page(biz: str, offset: int) -> bytes:
    rows = []
    for i in range(offset, offset + 10):
        rows.append({
            "comm_msg_info": {"datetime": 1788307200 - i * 3600},
            "app_msg_ext_info": {
                "title": f"Article {i+1}",
                "content_url": (
                    "https://mp.weixin.qq.com/s?"
                    f"__biz={biz}&mid={1000+i}&idx=1&sn=SN{i+1}"
                ),
                "multi_app_msg_item_list": [],
            },
        })
    return json.dumps({
        "ret": 0,
        "can_msg_continue": 1 if offset == 0 else 0,
        "general_msg_list": json.dumps({"list": rows}),
    }).encode()


class GoodTransport:
    def __init__(self, biz):
        self.biz = biz

    def get(self, url):
        offset = int(parse_qs(urlsplit(url).query)["offset"][0])
        return page(self.biz, offset)


class Navigator:
    def __init__(self):
        self.calls = []

    def search_public_account(self, account_name):
        self.calls.append(account_name)
        return SearchEvidence(True, True, True, account_name)


def test_scanner_can_collect_valid_candidates_without_preknown_biz(tmp_path):
    web_root = tmp_path / ".xwechat" / "radium" / "web"
    web_root.mkdir(parents=True)
    payload = (
        b"https://mp.weixin.qq.com/mp/profile_ext?action=getmsg&__biz=BIZ_A&uin=UA&key=KA&pass_ticket=PA\x00"
        b"https://mp.weixin.qq.com/mp/profile_ext?action=getmsg&__biz=BIZ_B&uin=UB&key=KB&pass_ticket=PB"
    )
    (web_root / "capture.bin").write_bytes(payload)

    result = scan_credentials(
        None,
        roots=[web_root],
        since_minutes=60,
        max_files=10,
        max_total_bytes=1024 * 1024,
        max_directories=10,
        max_scan_seconds=2,
    )

    assert {item.fields["biz"] for item in result.candidates} == {"BIZ_A", "BIZ_B"}
    assert result.safe_summary()["sensitive_values_returned"] is False


def test_name_only_discovery_resolves_unique_new_biz_by_before_after_fingerprint_delta(tmp_path):
    navigator = Navigator()
    old = candidate("OLD_BIZ", "OLD", 100.0)
    target = candidate("BIZ_TARGET", "TARGET", 200.0)
    scans = [report([old]), report([old, target])]

    def scan_fn(target_biz, **kwargs):
        assert target_biz is None
        return scans.pop(0)

    service = LiveDiscoveryService(
        tmp_path,
        bootstrapper=lambda biz: (_ for _ in ()).throw(AssertionError("URL bootstrap must not run before biz is known")),
        transport_factory=lambda item: GoodTransport(item.fields["biz"]),
        ui_navigator=navigator,
        scan_fn=scan_fn,
        ui_timeout_seconds=1.0,
        ui_poll_seconds=0.0,
    )

    result = service.recent_articles("目标公众号", None, 20)

    assert result.article_count == 20
    assert {article.biz for article in result.articles} == {"BIZ_TARGET"}
    assert result.account_verified is False
    assert not (tmp_path / ".public-account-index.json").exists()
    assert navigator.calls == ["目标公众号"]


def test_name_only_discovery_rejects_ambiguous_multiple_new_biz_candidates(tmp_path):
    navigator = Navigator()
    scans = [
        report([]),
        report([
            candidate("BIZ_A", "A", 200.0),
            candidate("BIZ_B", "B", 201.0),
        ]),
    ]

    service = LiveDiscoveryService(
        tmp_path,
        transport_factory=lambda item: GoodTransport(item.fields["biz"]),
        ui_navigator=navigator,
        scan_fn=lambda target_biz, **kwargs: scans.pop(0),
        ui_timeout_seconds=1.0,
        ui_poll_seconds=0.0,
    )

    with pytest.raises(ProviderError) as exc:
        service.recent_articles("目标公众号", None, 20)
    assert exc.value.code == "ACCOUNT_IDENTITY_AMBIGUOUS"
    rendered = str(exc.value)
    assert "BIZ_A" not in rendered
    assert "BIZ_B" not in rendered
