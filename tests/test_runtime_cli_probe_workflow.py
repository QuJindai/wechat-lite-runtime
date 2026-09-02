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
