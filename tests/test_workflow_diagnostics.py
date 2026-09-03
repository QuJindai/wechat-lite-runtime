from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTIC_WORKFLOWS = (
    "runtime-cli-probe.yml",
    "runtime-launcher-probe.yml",
    "runtime-smoke.yml",
)


def test_diagnostic_workflows_cannot_create_untested_bot_commits():
    for filename in DIAGNOSTIC_WORKFLOWS:
        workflow = (ROOT / ".github" / "workflows" / filename).read_text(encoding="utf-8")
        assert "contents: read" in workflow, filename
        assert "contents: write" not in workflow, filename
        assert "git commit" not in workflow, filename
        assert "git push" not in workflow, filename
        assert "actions/upload-artifact@v4" in workflow, filename
        assert "$GITHUB_STEP_SUMMARY" in workflow, filename
        assert "> docs/" not in workflow, filename


def test_live_discovery_index_smoke_uses_verified_identity_api():
    workflow = (ROOT / ".github" / "workflows" / "live-discovery-runtime-smoke.yml").read_text(
        encoding="utf-8"
    )
    assert "index.remember_verified(identity)" in workflow
    assert "resolve_verified(" in workflow
    assert "index.remember(" not in workflow
    assert ").resolve(" not in workflow


def test_development_status_describes_runtime_smoke_as_failure_path_only():
    development = (ROOT / "DEVELOPMENT.md").read_text(encoding="utf-8")
    assert "V1_LIVE_RUNTIME_FAILURE_PATH_SMOKE = PASS" in development
    assert "unauthenticated failure-path integration smoke" in development
    assert "does not prove logged-in newest-20 pagination" in development
