from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_cli_probe_starts_real_wechat_container_and_uploads_diagnostic():
    workflow = (ROOT / ".github/workflows/runtime-cli-probe.yml").read_text(encoding="utf-8")

    assert "name: Runtime CLI Probe" in workflow
    assert "feat/v1-public-account-discovery" in workflow
    assert "docker compose -f .devcontainer/docker-compose.yml up -d wechat" in workflow
    assert "ps -eo pid,args" in workflow
    assert "Radium|WMPF|WeChatAppEx|chrome|chromium|cef" in workflow
    assert "ss -ltnp" in workflow
    assert "/json/version" in workflow
    assert "/json/list" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "runtime-cli-probe" in workflow


def test_runtime_cli_probe_diagnostic_is_sanitized_and_does_not_mount_real_state():
    workflow = (ROOT / ".github/workflows/runtime-cli-probe.yml").read_text(encoding="utf-8")

    assert "WECHAT_IMAGE=ghcr.io/nickrunning/wechat-selkies:0.0.16" in workflow
    assert "state-runtime-cli-probe" in workflow
    assert "<redacted>" in workflow
    assert "cookie" not in workflow.lower()
    assert "pass_ticket" not in workflow
    assert "appmsg_token" not in workflow
