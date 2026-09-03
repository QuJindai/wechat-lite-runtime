import json
from urllib.parse import parse_qs, urlsplit

import pytest

from app.account_bootstrap import BootstrapResult, LaunchEvidence
from app.credential_scanner import CaptureCandidate
from app.live_discovery import LiveDiscoveryService
from app.providers import ProviderError


def candidate(name: str, modified_at: float) -> CaptureCandidate:
    return CaptureCandidate(
        request_url=(
            "https://mp.weixin.qq.com/mp/profile_ext?action=getmsg&__biz=BIZ_TARGET"
            f"&uin=UIN_{name}&key=KEY_{name}&pass_ticket=PASS_{name}"
        ),
        fields={
            "biz": "BIZ_TARGET",
            "uin": f"UIN_{name}",
            "key": f"KEY_{name}",
            "pass_ticket": f"PASS_{name}",
        },
        modified_at=modified_at,
        source_root=".xwechat/radium/web",
    )


def bootstrap_result(candidates):
    return BootstrapResult(
        status="CREDENTIAL_OBSERVED",
        launch=LaunchEvidence(True, 255, True, "/usr/bin/wechat", "https://mp.weixin.qq.com/mp/profile_ext"),
        credential_observed=True,
        candidate_count=len(candidates),
        poll_count=1,
        candidates=list(candidates),
        scanner_truncated=False,
    )


def page(offset: int) -> bytes:
    entries = []
    for i in range(offset, offset + 10):
        entries.append({
            "comm_msg_info": {"datetime": 1788307200 - i * 3600},
            "app_msg_ext_info": {
                "title": f"Article {i + 1}",
                "content_url": (
                    "https://mp.weixin.qq.com/s?__biz=BIZ_TARGET"
                    f"&mid={1000+i}&idx=1&sn=SN{i+1}&key=ARTICLE_SECRET"
                ),
                "multi_app_msg_item_list": [],
            },
        })
    return json.dumps({
        "ret": 0,
        "can_msg_continue": 1 if offset == 0 else 0,
        "general_msg_list": json.dumps({"list": entries}),
    }).encode()


class AuthFailTransport:
    def get(self, url: str) -> bytes:
        raise ProviderError("LOGIN_REQUIRED", "stale credential")


class GoodTransport:
    def get(self, url: str) -> bytes:
        offset = int(parse_qs(urlsplit(url).query)["offset"][0])
        return page(offset)


def test_live_discovery_rotates_from_newest_stale_candidate_to_older_working_candidate(tmp_path):
    newest = candidate("NEW", 200.0)
    older = candidate("OLD", 100.0)
    seen = []

    def factory(item):
        seen.append(item.fields["key"])
        return AuthFailTransport() if item is newest else GoodTransport()

    service = LiveDiscoveryService(
        tmp_path,
        bootstrapper=lambda biz: bootstrap_result([older, newest]),
        transport_factory=factory,
    )
    result = service.recent_articles("Example Account", "BIZ_TARGET", 20)

    assert result.article_count == 20
    assert result.count_satisfied is True
    assert seen == ["KEY_NEW", "KEY_OLD"]


def test_live_discovery_returns_login_required_when_all_valid_candidates_are_stale(tmp_path):
    newest = candidate("NEW", 200.0)
    older = candidate("OLD", 100.0)
    service = LiveDiscoveryService(
        tmp_path,
        bootstrapper=lambda biz: bootstrap_result([older, newest]),
        transport_factory=lambda item: AuthFailTransport(),
    )

    with pytest.raises(ProviderError) as exc:
        service.recent_articles("Example Account", "BIZ_TARGET", 20)
    assert exc.value.code == "LOGIN_REQUIRED"
    assert "KEY_NEW" not in str(exc.value)
    assert "KEY_OLD" not in str(exc.value)
