import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from app.account_bootstrap import BootstrapResult, LaunchEvidence
from app.credential_scanner import CaptureCandidate
from app.live_discovery import LiveDiscoveryService
from app.providers import ProviderError


def make_candidate(key: str, modified_at: float, biz: str = "BIZ_PUBLIC") -> CaptureCandidate:
    return CaptureCandidate(
        request_url=(
            "https://mp.weixin.qq.com/mp/profile_ext?action=getmsg"
            f"&__biz={biz}&uin=UIN_SECRET&key={key}&pass_ticket=PASS_SECRET&offset=0"
        ),
        fields={"biz": biz, "uin": "UIN_SECRET", "key": key, "pass_ticket": "PASS_SECRET"},
        modified_at=modified_at,
        source_root=".xwechat/radium/web",
    )


def bootstrap_result(candidates):
    return BootstrapResult(
        status="CREDENTIAL_OBSERVED" if candidates else "CREDENTIAL_NOT_OBSERVED",
        launch=LaunchEvidence(True, 255, True, "/usr/bin/wechat", "https://mp.weixin.qq.com/mp/profile_ext"),
        credential_observed=bool(candidates),
        candidate_count=len(candidates),
        poll_count=1,
        candidates=list(candidates),
        scanner_truncated=False,
    )


def page(start: int, count: int, can_continue: bool) -> bytes:
    rows = []
    for index in range(start, start + count):
        rows.append({
            "comm_msg_info": {"datetime": 1788307200 - index * 3600},
            "app_msg_ext_info": {
                "title": f"Article {index + 1}",
                "content_url": (
                    "https://mp.weixin.qq.com/s?__biz=BIZ_PUBLIC"
                    f"&mid={1000 + index}&idx=1&sn=SN{index + 1}&key=ARTICLE_SECRET"
                ),
                "multi_app_msg_item_list": [],
            },
        })
    return json.dumps({
        "ret": 0,
        "can_msg_continue": 1 if can_continue else 0,
        "general_msg_list": json.dumps({"list": rows}, separators=(",", ":")),
    }).encode()


class MemoryTransport:
    def __init__(self, pages):
        self.pages = pages
        self.urls = []

    def get(self, url: str) -> bytes:
        self.urls.append(url)
        return self.pages[int(parse_qs(urlsplit(url).query)["offset"][0])]


def test_live_service_bootstraps_selects_newest_matching_candidate_and_returns_20(tmp_path: Path):
    older = make_candidate("OLD_SECRET", 10)
    newer = make_candidate("NEW_SECRET", 20)
    bootstrap_calls = []
    transport_candidates = []
    memory = MemoryTransport({0: page(0, 10, True), 10: page(10, 10, False)})

    def bootstrapper(biz: str):
        bootstrap_calls.append(biz)
        return bootstrap_result([older, newer])

    def transport_factory(candidate):
        transport_candidates.append(candidate)
        return memory

    service = LiveDiscoveryService(
        state_dir=tmp_path,
        bootstrapper=bootstrapper,
        transport_factory=transport_factory,
    )
    result = service.recent_articles("Example Account", "BIZ_PUBLIC", 20)

    assert bootstrap_calls == ["BIZ_PUBLIC"]
    assert transport_candidates == [newer]
    assert result.article_count == 20
    assert result.count_satisfied is True
    assert result.timestamps_complete is True
    assert result.urls_unique is True
    assert result.account_verified is True
    assert result.freshness_verified is True
    assert [int(parse_qs(urlsplit(url).query)["offset"][0]) for url in memory.urls] == [0, 10]
    rendered = json.dumps(result.to_dict(), ensure_ascii=False) + repr(service)
    for secret in ["OLD_SECRET", "NEW_SECRET", "UIN_SECRET", "PASS_SECRET", "ARTICLE_SECRET"]:
        assert secret not in rendered


def test_live_service_requires_observed_matching_candidate(tmp_path: Path):
    service = LiveDiscoveryService(
        state_dir=tmp_path,
        bootstrapper=lambda biz: bootstrap_result([]),
        transport_factory=lambda candidate: MemoryTransport({}),
    )
    with pytest.raises(ProviderError) as exc:
        service.recent_articles("Example", "BIZ_PUBLIC", 20)
    assert exc.value.code == "HISTORY_SURFACE_UNAVAILABLE"


def test_live_service_rejects_mismatched_candidate_biz(tmp_path: Path):
    service = LiveDiscoveryService(
        state_dir=tmp_path,
        bootstrapper=lambda biz: bootstrap_result([make_candidate("SECRET", 1, biz="OTHER_BIZ")]),
        transport_factory=lambda candidate: MemoryTransport({}),
    )
    with pytest.raises(ProviderError) as exc:
        service.recent_articles("Example", "BIZ_PUBLIC", 20)
    assert exc.value.code == "HISTORY_SURFACE_UNAVAILABLE"


def test_live_service_rejects_response_articles_from_wrong_biz(tmp_path: Path):
    candidate = make_candidate("SECRET", 1)
    wrong_body = page(0, 20, False).replace(b"BIZ_PUBLIC", b"OTHER_BIZ")
    service = LiveDiscoveryService(
        state_dir=tmp_path,
        bootstrapper=lambda biz: bootstrap_result([candidate]),
        transport_factory=lambda candidate: MemoryTransport({0: wrong_body}),
    )
    with pytest.raises(ProviderError) as exc:
        service.recent_articles("Example", "BIZ_PUBLIC", 20)
    assert exc.value.code == "ACCOUNT_NOT_FOUND"
