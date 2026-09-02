from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_cli_probe_workflow_is_thin_and_uploads_diagnostic():
    workflow = (ROOT / ".github/workflows/runtime-cli-probe.yml").read_text(encoding="utf-8")

    assert "name: Runtime CLI Probe" in workflow
    assert "feat/v1-public-account-discovery" in workflow
    assert "bash scripts/runtime-cli-probe.sh" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "runtime-cli-probe" in workflow


def test_runtime_cli_probe_script_starts_real_wechat_and_checks_radium_cdp():
    script = (ROOT / "scripts/runtime-cli-probe.sh").read_text(encoding="utf-8")

    assert "WECHAT_IMAGE=ghcr.io/nickrunning/wechat-selkies:0.0.16" in script
    assert "state-runtime-cli-probe" in script
    assert "docker compose -f .devcontainer/docker-compose.yml up -d wechat" in script
    assert "ps -eo pid,args" in script
    assert "Radium|WMPF|WeChatAppEx|chrome|chromium|cef" in script
    assert "ss -ltnp" in script
    assert "/json/version" in script
    assert "/json/list" in script
    assert "<redacted>" in script
    assert "cookie" not in script.lower()
    assert "pass_ticket" not in script
    assert "appmsg_token" not in script
