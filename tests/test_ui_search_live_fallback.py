import json
from urllib.parse import parse_qs, urlsplit

from app.account_bootstrap import BootstrapResult, LaunchEvidence
from app.credential_scanner import CaptureCandidate, ScanReport
from app.launcher_bridge import SearchEvidence
from app.live_discovery import LiveDiscoveryService


def empty_bootstrap():
    return BootstrapResult(
        status="CREDENTIAL_NOT_OBSERVED",
        launch=LaunchEvidence(True, 255, True, "/usr/bin/wechat", "https://mp.weixin.qq.com/mp/profile_ext"),
        credential_observed=False,
        candidate_count=0,
        poll_count=1,
        candidates=[],
        scanner_truncated=False,
    )


def candidate():
    return CaptureCandidate(
        request_url=(
            "https://mp.weixin.qq.com/mp/profile_ext?action=getmsg&__biz=BIZ_TARGET"
            "&uin=UIN_UI&key=KEY_UI&pass_ticket=PASS_UI"
        ),
        fields={"biz": "BIZ_TARGET", "uin": "UIN_UI", "key": "KEY_UI", "pass_ticket": "PASS_UI"},
        modified_at=1000.0,
        source_root=".xwechat/radium/web",
    )


def report(items):
    return ScanReport(
        scanned_files=1,
        scanned_bytes=100,
        roots=[".xwechat/radium/web"],
        candidates=list(items),
        duration_seconds=0.01,
        truncated=False,
        truncation_reasons=[],
    )


def page(offset):
    entries = []
    for i in range(offset, offset + 10):
        entries.append({
            "comm_msg_info": {"datetime": 1788307200 - i * 3600},
            "app_msg_ext_info": {
                "title": f"Article {i+1}",
                "content_url": (
                    "https://mp.weixin.qq.com/s?__biz=BIZ_TARGET"
                    f"&mid={1000+i}&idx=1&sn=SN{i+1}"
                ),
                "multi_app_msg_item_list": [],
            },
        })
    return json.dumps({
        "ret": 0,
        "can_msg_continue": 1 if offset == 0 else 0,
        "general_msg_list": json.dumps({"list": entries}),
    }).encode()


class GoodTransport:
    def get(self, url):
        offset = int(parse_qs(urlsplit(url).query)["offset"][0])
        return page(offset)


class Navigator:
    def __init__(self):
        self.calls = []

    def search_public_account(self, account_name):
        self.calls.append(account_name)
        return SearchEvidence(True, True, True, account_name)


def test_live_discovery_uses_ui_search_only_after_history_and_url_bootstrap_fail(tmp_path):
    navigator = Navigator()
    scans = [report([]), report([candidate()])]
    scan_calls = []

    def scan_fn(biz, **kwargs):
        scan_calls.append(biz)
        return scans.pop(0)

    service = LiveDiscoveryService(
        tmp_path,
        bootstrapper=lambda biz: empty_bootstrap(),
        transport_factory=lambda item: GoodTransport(),
        ui_navigator=navigator,
        scan_fn=scan_fn,
        ui_timeout_seconds=1.0,
        ui_poll_seconds=0.0,
    )
    result = service.recent_articles("示例公众号", "BIZ_TARGET", 20)

    assert result.article_count == 20
    assert navigator.calls == ["示例公众号"]
    assert scan_calls == ["BIZ_TARGET", "BIZ_TARGET"]
