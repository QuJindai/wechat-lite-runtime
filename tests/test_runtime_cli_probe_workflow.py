from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_cli_probe_starts_real_wechat_container_and_uploads_sanitized_artifact():
    workflow = (ROOT / ".github/workflows/runtime-cli-probe.yml").read_text(encoding="utf-8")
    assert "name: Runtime CLI Probe" in workflow
    assert "feat/v1-public-account-discovery" in workflow
    assert "docker compose -f .devcontainer/docker-compose.yml up -d wechat" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "runtime-cli-probe" in workflow


def test_runtime_cli_probe_publishes_only_sanitized_summary_artifacts():
    workflow = (ROOT / ".github/workflows/runtime-cli-probe.yml").read_text(encoding="utf-8")
    assert "contents: read" in workflow
    assert "/tmp/runtime-cli-probe/summary.md" in workflow
    assert "$GITHUB_STEP_SUMMARY" in workflow
    assert "git commit" not in workflow
    assert "git push" not in workflow
    assert "<redacted>" in workflow
    assert "cookie" not in workflow.lower()
    assert "pass_ticket" not in workflow
    assert "appmsg_token" not in workflow


def test_runtime_cli_probe_inspects_linux_wechat_url_handler_and_dynamic_desktop_fields():
    workflow = (ROOT / ".github/workflows/runtime-cli-probe.yml").read_text(encoding="utf-8")
    assert 'find /usr/share/applications -maxdepth 1 -type f -iname "*wechat*.desktop"' in workflow
    assert "DESKTOP_DISCOVERED=" in workflow
    assert "while IFS= read -r desktop" in workflow
    assert 'grep -E "^Exec=" "$desktop"' in workflow
    assert 'grep -E "^MimeType=" "$desktop"' in workflow
    assert "xdg-mime query default x-scheme-handler/weixin" in workflow
    assert "weixin://" in workflow
    assert "runtime-cli-probe/url-handler.txt" in workflow
    assert "## URL handler capability" in workflow


def test_runtime_cli_probe_invokes_https_profile_url_and_records_only_sanitized_marker_counts():
    workflow = (ROOT / ".github/workflows/runtime-cli-probe.yml").read_text(encoding="utf-8")
    assert "AUTOTEST_BIZ" in workflow
    assert "/usr/bin/wechat" in workflow
    assert "mp/profile_ext?action=home" in workflow
    assert "DISPLAY=:1" in workflow
    assert "URL_INVOKE_EXIT=" in workflow
    assert "HISTORY_MARKER_ROWS=" in workflow
    assert "RAW_MARKER_FILES=" in workflow
    assert "runtime-cli-probe/url-invocation.txt" in workflow
    assert "## URL invocation capability" in workflow
