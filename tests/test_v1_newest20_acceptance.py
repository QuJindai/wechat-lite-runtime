from datetime import datetime, timedelta, timezone

from app.public_accounts import build_discovery_result, normalize_article
from app.v1_acceptance import evaluate_newest20_gate


def result(*, count=20, timestamp_missing=False, account_verified=True, freshness_verified=True):
    records = []
    base = datetime(2026, 9, 2, 20, 0, tzinfo=timezone(timedelta(hours=8)))
    for i in range(count):
        records.append(normalize_article({
            "account_name": "目标公众号",
            "biz": "BIZ_PUBLIC",
            "title": f"Article {i+1}",
            "url": (
                "https://mp.weixin.qq.com/s?__biz=BIZ_PUBLIC"
                f"&mid={1000+i}&idx=1&sn=SN{i+1}&key=SECRET{i+1}&pass_ticket=PASS{i+1}"
            ),
            "published_at": None if (timestamp_missing and i == 5) else base.timestamp() - i * 3600,
            "observed_at": base,
            "verified_account": account_verified,
        }, i + 1))
    return build_discovery_result(
        records,
        requested_count=20,
        account_verified=account_verified,
        freshness_verified=freshness_verified,
        is_exhaustive_for_window=False,
        provider="authenticated_history",
        verification="authenticated_history_seed",
    )


def test_newest20_acceptance_passes_automated_gate_but_requires_ui_head_tail_crosscheck():
    gate = evaluate_newest20_gate(result())

    assert gate["verdict"] == "AUTOMATED_GATE_PASS_UI_PENDING"
    assert gate["checks"] == {
        "article_count_20": True,
        "count_satisfied": True,
        "timestamps_complete": True,
        "urls_unique": True,
        "account_verified": True,
        "freshness_verified": True,
    }
    assert gate["manual_ui_crosscheck_required"] is True
    assert gate["first"]["position"] == 1
    assert gate["twentieth"]["position"] == 20
    assert gate["first"]["title"] == "Article 1"
    assert gate["twentieth"]["title"] == "Article 20"
    assert gate["sensitive_values_returned"] is False
    rendered = repr(gate)
    for secret in ["SECRET1", "PASS1", "SECRET20", "PASS20"]:
        assert secret not in rendered


def test_newest20_acceptance_fails_when_any_required_dimension_is_false():
    gate = evaluate_newest20_gate(result(timestamp_missing=True, freshness_verified=False))

    assert gate["verdict"] == "AUTOMATED_GATE_FAIL"
    assert gate["checks"]["timestamps_complete"] is False
    assert gate["checks"]["freshness_verified"] is False
    assert gate["manual_ui_crosscheck_required"] is False


def test_newest20_acceptance_does_not_treat_less_than_twenty_as_pass():
    gate = evaluate_newest20_gate(result(count=19))
    assert gate["verdict"] == "AUTOMATED_GATE_FAIL"
    assert gate["checks"]["article_count_20"] is False
    assert gate["first"] is not None
    assert gate["twentieth"] is None
