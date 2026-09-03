from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.public_accounts import build_discovery_result, normalize_article


def settings(tmp_path: Path) -> Settings:
    return Settings(
        control_token="secret",
        codespace_name="api-space",
        state_dir=tmp_path,
        wechat_host="127.0.0.1",
        wechat_port=3001,
        probe_timeout=0.1,
    )


def auth():
    return {"Authorization": "Bearer secret"}


class Service:
    def __init__(self):
        self.calls = []

    def recent_articles(self, account_name, biz, limit):
        self.calls.append((account_name, biz, limit))
        records = []
        for i in range(limit):
            records.append(normalize_article({
                "account_name": account_name,
                "biz": "RESOLVED_BIZ",
                "title": f"Article {i+1}",
                "url": f"https://mp.weixin.qq.com/s/article-{i+1}",
                "published_at": 1788307200 - i * 3600,
                "observed_at": 1788307200,
                "verified_account": False,
            }, i + 1))
        return build_discovery_result(
            records,
            requested_count=limit,
            account_verified=False,
            freshness_verified=True,
            is_exhaustive_for_window=False,
            provider="authenticated_history",
            verification="resolved_by_ui_delta",
        )


def test_discover_api_accepts_account_name_without_biz(tmp_path):
    service = Service()
    client = TestClient(create_app(settings(tmp_path), tcp_probe=lambda *_: True, live_discovery_service=service))

    response = client.post(
        "/v1/public-accounts/discover",
        json={"account_name": "目标公众号", "limit": 20},
        headers=auth(),
    )

    assert response.status_code == 200
    assert service.calls == [("目标公众号", None, 20)]
    assert response.json()["article_count"] == 20
    assert {item["biz"] for item in response.json()["articles"]} == {"RESOLVED_BIZ"}


def test_discover_api_maps_identity_ambiguity_without_exposing_candidate_values(tmp_path):
    from app.providers import ProviderError

    class Ambiguous:
        def recent_articles(self, account_name, biz, limit):
            raise ProviderError("ACCOUNT_IDENTITY_AMBIGUOUS", "multiple candidates SECRET_BIZ_VALUE")

    client = TestClient(create_app(settings(tmp_path), tcp_probe=lambda *_: True, live_discovery_service=Ambiguous()))
    response = client.post(
        "/v1/public-accounts/discover",
        json={"account_name": "目标公众号"},
        headers=auth(),
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ACCOUNT_IDENTITY_AMBIGUOUS"
    assert "SECRET_BIZ_VALUE" not in response.text
