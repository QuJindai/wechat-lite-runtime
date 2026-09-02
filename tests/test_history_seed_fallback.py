import json
import sqlite3
from urllib.parse import parse_qs, urlsplit

from app.account_bootstrap import BootstrapResult, LaunchEvidence
from app.credential_scanner import CaptureCandidate
from app.history_seed import locate_state_history_seeds
from app.live_discovery import LiveDiscoveryService
from app.providers import ProviderError


def write_history(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE urls (id INTEGER PRIMARY KEY, url TEXT, title TEXT, visit_count INTEGER, typed_count INTEGER, last_visit_time INTEGER, hidden INTEGER)"
        )
        for row_id, url, ts in rows:
            conn.execute(
                "INSERT INTO urls VALUES (?, ?, ?, 1, 0, ?, 0)",
                (row_id, url, "history", ts),
            )
        conn.commit()
    finally:
        conn.close()


def seed_url(biz, suffix):
    return (
        "https://mp.weixin.qq.com/mp/profile_ext?action=home"
        f"&__biz={biz}&uin=UIN_{suffix}&key=KEY_{suffix}&pass_ticket=PASS_{suffix}&appmsg_token=TOKEN_{suffix}"
    )


def page(offset):
    rows = []
    for i in range(offset, offset + 10):
        rows.append({
            "comm_msg_info": {"datetime": 1788307200 - i * 3600},
            "app_msg_ext_info": {
                "title": f"Article {i+1}",
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
        "general_msg_list": json.dumps({"list": rows}),
    }).encode()


class GoodTransport:
    def get(self, url):
        return page(int(parse_qs(urlsplit(url).query)["offset"][0]))


class StaleTransport:
    def get(self, url):
        raise ProviderError("LOGIN_REQUIRED", "stale history seed")


def bootstrap_candidate():
    item = CaptureCandidate(
        request_url=(
            "https://mp.weixin.qq.com/mp/profile_ext?action=getmsg&__biz=BIZ_TARGET"
            "&uin=UIN_BOOT&key=KEY_BOOT&pass_ticket=PASS_BOOT"
        ),
        fields={"biz": "BIZ_TARGET", "uin": "UIN_BOOT", "key": "KEY_BOOT", "pass_ticket": "PASS_BOOT"},
        modified_at=999.0,
        source_root=".xwechat/radium/web",
    )
    return BootstrapResult(
        status="CREDENTIAL_OBSERVED",
        launch=LaunchEvidence(True, 255, True, "/usr/bin/wechat", "https://mp.weixin.qq.com/mp/profile_ext"),
        credential_observed=True,
        candidate_count=1,
        poll_count=1,
        candidates=[item],
        scanner_truncated=False,
    )


def test_state_history_seed_locator_filters_target_biz_and_orders_newest(tmp_path):
    profiles = tmp_path / ".xwechat" / "radium" / "web" / "profiles"
    write_history(
        profiles / "multitab_a" / "History",
        [
            (1, seed_url("OTHER_BIZ", "OTHER"), 900),
            (2, seed_url("BIZ_TARGET", "OLD"), 500),
        ],
    )
    write_history(
        profiles / "multitab_b" / "History",
        [(1, seed_url("BIZ_TARGET", "NEW"), 800)],
    )

    seeds = locate_state_history_seeds(tmp_path, "BIZ_TARGET")
    assert len(seeds) == 2
    assert seeds[0].last_visit_time == 800
    assert seeds[1].last_visit_time == 500
    rendered = repr(seeds)
    for secret in ["KEY_NEW", "KEY_OLD", "PASS_NEW", "PASS_OLD"]:
        assert secret not in rendered


def test_live_discovery_uses_working_private_history_before_bootstrap(tmp_path):
    profiles = tmp_path / ".xwechat" / "radium" / "web" / "profiles"
    write_history(profiles / "multitab_a" / "History", [(1, seed_url("BIZ_TARGET", "HISTORY"), 800)])
    bootstrap_calls = []

    def bootstrapper(biz):
        bootstrap_calls.append(biz)
        raise AssertionError("bootstrap should not run when private History seed works")

    service = LiveDiscoveryService(
        tmp_path,
        bootstrapper=bootstrapper,
        transport_factory=lambda candidate: GoodTransport(),
    )
    result = service.recent_articles("Example", "BIZ_TARGET", 20)
    assert result.article_count == 20
    assert bootstrap_calls == []


def test_live_discovery_refreshes_after_stale_private_history_seed(tmp_path):
    profiles = tmp_path / ".xwechat" / "radium" / "web" / "profiles"
    write_history(profiles / "multitab_a" / "History", [(1, seed_url("BIZ_TARGET", "HISTORY"), 800)])
    seen = []

    def factory(candidate):
        key = candidate.fields.get("key")
        seen.append(key)
        return StaleTransport() if key == "KEY_HISTORY" else GoodTransport()

    service = LiveDiscoveryService(
        tmp_path,
        bootstrapper=lambda biz: bootstrap_candidate(),
        transport_factory=factory,
    )
    result = service.recent_articles("Example", "BIZ_TARGET", 20)

    assert result.article_count == 20
    assert seen == ["KEY_HISTORY", "KEY_BOOT"]
