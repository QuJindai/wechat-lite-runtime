from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_safe_probe_script_self_heals_and_calls_local_probe_api():
    script = (ROOT / "scripts/probe-wechat-state.sh").read_text(encoding="utf-8")
    assert "scripts/start-control-api.sh" in script
    assert "/v1/wechat/probe" in script
    assert "ensure_control_token" in script
    assert "echo $TOKEN" not in script
    assert "cat state/.control-token" not in script


def test_readme_documents_v1_safe_probe_command_and_privacy_boundary():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "bash scripts/probe-wechat-state.sh" in readme
    assert "feat/v1-public-account-discovery" in readme
    assert "does not print cookies" in readme.lower()


def test_development_doc_records_v1_phase_a_physical_probe_passed():
    development = (ROOT / "DEVELOPMENT.md").read_text(encoding="utf-8")
    assert "V1_PHASE_A_SOFTWARE = PASS" in development
    assert "V1_SAFE_RUNTIME_PROBE = PASS" in development
    assert "mp_weixin_trace" in development
    assert "newest 20" in development.lower()
