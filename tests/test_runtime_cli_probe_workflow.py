from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_cli_probe_starts_real_wechat_container_and_uploads_sanitized_artifact():
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


def test_runtime_cli_probe_persists_only_sanitized_summary_to_repository():
    workflow = (ROOT / ".github/workflows/runtime-cli-probe.yml").read_text(encoding="utf-8")

    assert "contents: write" in workflow
    assert "docs/runtime-cli-probe-latest.md" in workflow
    assert "git commit -m 'ci: record runtime CLI probe'" in workflow
    assert "git push" in workflow
    assert "<redacted>" in workflow
    assert "cookie" not in workflow.lower()
    assert "pass_ticket" not in workflow
    assert "appmsg_token" not in workflow


def test_runtime_cli_probe_identifies_port_8082_and_checks_for_devtools_configuration():
    workflow = (ROOT / ".github/workflows/runtime-cli-probe.yml").read_text(encoding="utf-8")

    assert "8082" in workflow
    assert "fuser -n tcp 8082" in workflow or "lsof -nP -iTCP:8082" in workflow
    assert "http://127.0.0.1:8082" in workflow
    assert "/json/version" in workflow
    assert "/json/list" in workflow
    assert "remote-debugging" in workflow
    assert "/opt/wechat" in workflow
    assert "runtime-cli-probe/port-8082.txt" in workflow
    assert "runtime-cli-probe/runtime-config-hints.txt" in workflow
