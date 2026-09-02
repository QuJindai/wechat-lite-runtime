from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_phase_b_handoff_script_calls_sanitized_webview_probe():
    script = (ROOT / "scripts/probe-wechat-webview.sh").read_text(encoding="utf-8")
    assert "WECHAT_CONTROL_FORCE_RESTART=1 bash scripts/start-control-api.sh" in script
    assert "/v1/wechat/webview-probe" in script
    assert "ensure_control_token" in script
    assert "sensitive_values_returned" in script
    assert "cat state/.control-token" not in script
    assert "echo $token" not in script
    assert "print(token)" not in script


def test_readme_documents_phase_b_probe_command_and_security_boundary():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "bash scripts/probe-wechat-webview.sh" in readme
    assert "schema names" in readme
    assert "marker counts" in readme
    assert "does not return cookie or token values" in readme


def test_development_doc_records_phase_b_physical_probe_passed():
    development = (ROOT / "DEVELOPMENT.md").read_text(encoding="utf-8")
    assert "V1_PHASE_B_SOFTWARE = PASS" in development
    assert "V1_WEBVIEW_CONTAINER_PROBE = PASS" in development
    assert "multitab_<redacted>" in development
    assert "Local Storage/leveldb" in development
