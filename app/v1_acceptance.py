from __future__ import annotations

from app.public_accounts import ArticleRecord, DiscoveryResult


def _article_summary(article: ArticleRecord | None) -> dict[str, object] | None:
    if article is None:
        return None
    return {
        "account_name": article.account_name,
        "biz": article.biz,
        "title": article.title,
        "canonical_url": article.canonical_url,
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "position": article.position,
    }


def evaluate_newest20_gate(result: DiscoveryResult) -> dict[str, object]:
    checks = {
        "article_count_20": result.article_count == 20,
        "count_satisfied": bool(result.count_satisfied),
        "timestamps_complete": bool(result.timestamps_complete),
        "urls_unique": bool(result.urls_unique),
        "account_verified": bool(result.account_verified),
        "freshness_verified": bool(result.freshness_verified),
    }
    automated_pass = all(checks.values())
    first = result.articles[0] if result.articles else None
    twentieth = result.articles[19] if len(result.articles) >= 20 else None
    return {
        "verdict": "AUTOMATED_GATE_PASS_UI_PENDING" if automated_pass else "AUTOMATED_GATE_FAIL",
        "checks": checks,
        "provider": result.provider,
        "verification": result.verification,
        "first": _article_summary(first),
        "twentieth": _article_summary(twentieth),
        "manual_ui_crosscheck_required": automated_pass,
        "sensitive_values_returned": False,
    }
