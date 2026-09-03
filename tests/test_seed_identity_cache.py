import json
from pathlib import Path

from app.seed_article import SeedArticleResolver


def test_public_seed_cache_short_circuits_network(tmp_path: Path):
    cache = tmp_path / "public-seed-identities.json"
    cache.write_text(json.dumps({
        "https://mp.weixin.qq.com/s/STxoDJyTsG6rrlZBDcBK9g": {
            "account_name": "dSPACE德斯拜思",
            "biz": "Mzg2Mzg3NzgxNw=="
        }
    }, ensure_ascii=False), encoding="utf-8")
    calls = []
    resolver = SeedArticleResolver(cache_path=cache, opener=lambda req, timeout: calls.append(req))

    identity = resolver.resolve("https://mp.weixin.qq.com/s/STxoDJyTsG6rrlZBDcBK9g")

    assert identity.account_name == "dSPACE德斯拜思"
    assert identity.biz == "Mzg2Mzg3NzgxNw=="
    assert calls == []


def test_repository_public_seed_cache_contains_only_public_identity_fields():
    root = Path(__file__).resolve().parents[1]
    payload = json.loads((root / "config/public-seed-identities.json").read_text(encoding="utf-8"))
    entry = payload["https://mp.weixin.qq.com/s/STxoDJyTsG6rrlZBDcBK9g"]
    assert entry == {"account_name": "dSPACE德斯拜思", "biz": "Mzg2Mzg3NzgxNw=="}
    rendered = json.dumps(payload, ensure_ascii=False).lower()
    for forbidden in ["pass_ticket", "appmsg_token", "poc_token", "cookie", "authorization", "uin", "key\""]:
        assert forbidden not in rendered
