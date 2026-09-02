import json
from urllib.parse import parse_qs, urlsplit

from app.credential_scanner import CaptureCandidate, ScanReport
from app.launcher_bridge import SearchEvidence
from app.live_discovery import LiveDiscoveryService


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
        scanned_files=1,
        scanned_bytes=100,
        roots=[".xwechat/radium/web"],
        candidates=list(items),
        duration_seconds=0.01,
        truncated=False,
        truncation_reasons=[],
    )


class Navigator:
    def search_public_account(self, account_name):
        return SearchEvidence(True, True, True, account_name)


class GoodTransport:
    def __init__(self, biz):
        self.biz = biz

    def get(self, url):
        offset = int(parse_qs(urlsplit(url).query)["offset"][0])
        rows = []
        for i in range(offset, offset + 10):
            rows.append({
                "comm_msg_info": {"datetime": 1788307200 - i * 3600},
                "app_msg_ext_info": {
                    "title": f"Article {i+1}",
                    "content_url": f"https://mp.weixin.qq.com/s?__biz={self.biz}&mid={1000+i}&idx=1&sn=SN{i+1}",
                    "multi_app_msg_item_list": [],
                },
            })
        return json.dumps({
            "ret": 0,
            "can_msg_continue": 1 if offset == 0 else 0,
            "general_msg_list": json.dumps({"list": rows}),
        }).encode()


def test_name_resolution_ignores_baseline_fingerprint_even_when_file_mtime_is_newer_after_search(tmp_path):
    old_before = candidate("OLD_BIZ", "OLD", 100.0)
    # Same credential fingerprint, but its containing cache file was rewritten after UI search.
    old_after = candidate("OLD_BIZ", "OLD", 300.0)
    target = candidate("BIZ_TARGET", "TARGET", 250.0)
    scans = [report([old_before]), report([old_after, target])]

    service = LiveDiscoveryService(
        tmp_path,
        transport_factory=lambda item: GoodTransport(item.fields["biz"]),
        ui_navigator=Navigator(),
        scan_fn=lambda target_biz, **kwargs: scans.pop(0),
        ui_timeout_seconds=1.0,
        ui_poll_seconds=0.0,
    )

    result = service.recent_articles("目标公众号", None, 20)
    assert result.article_count == 20
    assert {article.biz for article in result.articles} == {"BIZ_TARGET"}
