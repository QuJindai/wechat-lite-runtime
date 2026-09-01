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
    assert "wechat-selkies:minimal" in wechat["image"]
    assert "../state:/config" in wechat["volumes"]
    assert str(wechat["environment"]["ENABLE_WECHAT_AUTO_LOGIN"]).lower() == "true"
    assert str(wechat["environment"]["AUTO_START_WECHAT"]).lower() == "true"
    assert str(wechat["environment"]["AUTO_START_QQ"]).lower() == "false"
    assert wechat["shm_size"] == "1gb"


def test_devcontainer_forwards_ui_and_control_ports():
    devcontainer = load_json(".devcontainer/devcontainer.json")
    assert {3001, 8787}.issubset(set(devcontainer["forwardPorts"]))
    assert devcontainer["service"] == "workspace"
    assert "wechat" in devcontainer["runServices"]


def test_ci_runs_python_module_pytest():
    workflow = (ROOT / ".github/workflows/test.yml").read_text(encoding="utf-8")
    assert "python -m pytest -q" in workflow
    assert "python-version: '3.12'" in workflow


def test_readme_documents_persistence_and_physical_gate():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "state/ -> /config" in readme
    assert "scan -> stop -> start -> verify" in readme
    assert "ghcr.io/nickrunning/wechat-selkies:minimal" in readme


def test_development_doc_keeps_main_merge_blocked_until_phone_gate():
    development = (ROOT / "DEVELOPMENT.md").read_text(encoding="utf-8")
    assert "PHYSICAL_LOGIN_PERSISTENCE" in development
    assert "Do not merge" in development


def test_wechat_ui_auto_opens_when_codespace_starts():
    devcontainer = load_json(".devcontainer/devcontainer.json")
    assert devcontainer["portsAttributes"]["3001"]["onAutoForward"] == "openBrowser"


def test_readme_documents_one_command_acceptance():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "python -m app.acceptance before" in readme
    assert "python -m app.acceptance after" in readme


def test_workspace_does_not_override_codespaces_injected_identity_or_secret():
    compose = load_yaml(".devcontainer/docker-compose.yml")
    workspace_env = compose["services"]["workspace"]["environment"]
    assert "WECHAT_CONTROL_TOKEN" not in workspace_env
    assert "CODESPACE_NAME" not in workspace_env


def test_devcontainer_recommends_control_token_secret():
    devcontainer = load_json(".devcontainer/devcontainer.json")
    assert "WECHAT_CONTROL_TOKEN" in devcontainer["secrets"]
