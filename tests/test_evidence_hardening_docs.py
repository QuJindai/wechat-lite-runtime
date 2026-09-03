from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_readme_documents_strict_identity_freshness_and_seed_gate():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "acceptance-from-url" in readme
    assert "caller-supplied name or biz is not identity evidence" in readme
    assert "live offset-zero" in readme
    assert "only seed-verified identities" in readme
    assert "unknown path and SQLite identifiers are redacted" in readme


def test_development_status_does_not_claim_unverified_discovery_is_persisted():
    development = (ROOT / "DEVELOPMENT.md").read_text(encoding="utf-8")
    assert "UI delta is navigation evidence only" in development
    assert "version 2" in development
    assert "only seed-verified identities are persisted" in development
    assert "acceptance-from-url" in development
