import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def load_yaml(path: str):
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


def test_wechat_service_contract():
    compose = load_yaml(".devcontainer/docker-compose.yml")
    wechat = compose["services"]["wechat"]
    assert wechat["image"] == "ghcr.io/nickrunning/wechat-selkies:0.0.16"
    assert "../state:/config" in wechat["volumes"]
    assert str(wechat["environment"]["ENABLE_WECHAT_AUTO_LOGIN"]).lower() == "true"
    assert str(wechat["environment"]["AUTO_START_WECHAT"]).lower() == "true"
    assert str(wechat["environment"]["AUTO_START_QQ"]).lower() == "false"
    assert wechat["shm_size"] == "1gb"


def test_devcontainer_forwards_ui_and_control_ports():
    devcontainer = load_json(".devcontainer/devcontainer.json")
    assert 8787 in devcontainer["forwardPorts"]
    assert "wechat:3001" in devcontainer["forwardPorts"]
    assert devcontainer["service"] == "workspace"
    assert "wechat" in devcontainer["runServices"]


def test_codespace_supports_gh_cli_remote_diagnostics():
    devcontainer = load_json(".devcontainer/devcontainer.json")
    assert devcontainer["features"]["ghcr.io/devcontainers/features/sshd:1"] == {
        "version": "latest"
    }


def test_workspace_image_removes_unused_broken_yarn_apt_source_before_features():
    compose = load_yaml(".devcontainer/docker-compose.yml")
    workspace = compose["services"]["workspace"]
    assert workspace["build"] == {
        "context": "..",
        "dockerfile": ".devcontainer/Dockerfile",
    }
    assert "image" not in workspace

    dockerfile = (ROOT / ".devcontainer/Dockerfile").read_text(encoding="utf-8")
    assert dockerfile.startswith(
        "FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm\n"
    )
    assert "rm -f /etc/apt/sources.list.d/yarn.list" in dockerfile


def test_ci_runs_python_module_pytest():
    workflow = (ROOT / ".github/workflows/test.yml").read_text(encoding="utf-8")
    assert "python -m pytest -q" in workflow
    assert "python-version: '3.12'" in workflow


def test_ci_checks_out_exact_pull_request_head():
    workflow = (ROOT / ".github/workflows/test.yml").read_text(encoding="utf-8")
    assert "ref: ${{ github.event.pull_request.head.sha || github.sha }}" in workflow


def test_readme_documents_persistence_and_physical_gate():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "state/ -> /config" in readme
    assert "scan -> stop -> start -> verify" in readme
    assert "ghcr.io/nickrunning/wechat-selkies:0.0.16" in readme


def test_development_doc_records_physical_login_gate_passed():
    development = (ROOT / "DEVELOPMENT.md").read_text(encoding="utf-8")
    assert "CODESPACE_STATE_PERSISTENCE = PASS" in development
    assert "PHYSICAL_LOGIN_PERSISTENCE = PASS" in development
    assert "V0 = PASS" in development


def test_wechat_ui_auto_opens_when_codespace_starts():
    devcontainer = load_json(".devcontainer/devcontainer.json")
    assert devcontainer["portsAttributes"]["wechat:3001"]["onAutoForward"] == "openBrowser"


def test_readme_documents_one_command_acceptance():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "python -m app.acceptance before" in readme
    assert "python -m app.acceptance after" in readme


def test_workspace_does_not_override_codespaces_injected_identity_or_secret():
    compose = load_yaml(".devcontainer/docker-compose.yml")
    workspace_env = compose["services"]["workspace"]["environment"]
    assert "WECHAT_CONTROL_TOKEN" not in workspace_env
    assert "CODESPACE_NAME" not in workspace_env


def test_devcontainer_does_not_require_manual_control_token_secret():
    devcontainer = load_json(".devcontainer/devcontainer.json")
    assert "secrets" not in devcontainer or "WECHAT_CONTROL_TOKEN" not in devcontainer["secrets"]


def test_readme_has_branch_specific_codespaces_quickstart_link():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "https://codespaces.new/QuJindai/wechat-lite-runtime/tree/feat/v0-codespace-runtime?quickstart=1" in readme


def test_codespaces_uses_service_forwarding_without_shared_container_namespaces():
    compose = load_yaml(".devcontainer/docker-compose.yml")
    workspace = compose["services"]["workspace"]
    wechat = compose["services"]["wechat"]
    assert "network_mode" not in workspace
    assert "network_mode" not in wechat
    assert workspace["environment"]["WECHAT_WEB_HOST"] == "wechat"
    assert workspace["environment"]["WECHAT_LAUNCHER_ENDPOINT"] == "http://wechat:8790/open"
    assert "WECHAT_LAUNCHER_HOST" not in wechat["environment"]
    assert "ports" not in workspace
    assert "ports" not in wechat
