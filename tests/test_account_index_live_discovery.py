import json
from urllib.parse import parse_qs, urlsplit

from app.account_bootstrap import BootstrapResult, LaunchEvidence
from app.account_index import PublicAccountIndex
from app.credential_scanner import CaptureCandidate
from app.live_discovery import LiveDiscoveryService


def candidate():
    item = CaptureCandidate(
        request_url=(
            "https://mp.weixin.qq.com/mp/profile_ext?action=getmsg&__biz=BIZ_TARGET"
            "&uin=UIN_SECRET&key=KEY_SECRET&pass_ticket=PASS_SECRET"
        ),
        fields={"biz": "BIZ_TARGET", "uin": "UIN_SECRET", "key": "KEY_SECRET", "pass_ticket": "PASS_SECRET"},
        modified_at=100.0,
        source_root=".xwechat/radium/web",
    )
    return item


def bootstrap_result():
    return BootstrapResult(
        status="CREDENTIAL_OBSERVED",
        launch=LaunchEvidence(True, 255, True, "/usr/bin/wechat", "https://mp.weixin.qq.com/mp/profile_ext"),
        credential_observed=True,
        candidate_count=1,
        poll_count=1,
        candidates=[candidate()],
        scanner_truncated=False,
    )


class GoodTransport:
    def get(self, url):
        offset = int(parse_qs(urlsplit(url).query)["offset"][0])
        rows = []
        for i in range(offset, offset + 10):
            rows.append({
                "comm_msg_info": {"datetime": 1788307200 - i * 3600},
                "app_msg_ext_info": {
                    "title": f"Article {i+1}",
                    "content_url": f"https://mp.weixin.qq.com/s?__biz=BIZ_TARGET&mid={1000+i}&idx=1&sn=SN{i+1}",
                    "multi_app_msg_item_list": [],
                },
            })
        return json.dumps({
            "ret": 0,
            "can_msg_continue": 1 if offset == 0 else 0,
            "general_msg_list": json.dumps({"list": rows}),
        }).encode()


class ForbiddenNavigator:
    def search_public_account(self, account_name):
        raise AssertionError("persisted account index should avoid UI resolution")


def test_successful_explicit_biz_discovery_remembers_mapping_for_later_name_only_request(tmp_path):
    index = PublicAccountIndex(tmp_path)
    first = LiveDiscoveryService(
        tmp_path,
        bootstrapper=lambda biz: bootstrap_result(),
        transport_factory=lambda item: GoodTransport(),
        account_index=index,
    )
    result = first.recent_articles("目标公众号", "BIZ_TARGET", 20)
    assert result.article_count == 20
    assert index.resolve("目标公众号") == "BIZ_TARGET"

    second = LiveDiscoveryService(
        tmp_path,
        bootstrapper=lambda biz: bootstrap_result(),
        transport_factory=lambda item: GoodTransport(),
        ui_navigator=ForbiddenNavigator(),
        account_index=PublicAccountIndex(tmp_path),
    )
    result2 = second.recent_articles("目标公众号", None, 20)
    assert result2.article_count == 20
    assert {article.biz for article in result2.articles} == {"BIZ_TARGET"}
