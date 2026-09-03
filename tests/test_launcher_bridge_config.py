from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_wechat_service_installs_internal_launcher_as_custom_s6_service():
    compose = yaml.safe_load((ROOT / ".devcontainer/docker-compose.yml").read_text(encoding="utf-8"))
    wechat = compose["services"]["wechat"]
    volumes = wechat["volumes"]
    assert any("wechat-launcher-service.py" in str(item) and "/opt/wechat-lite/wechat-launcher-service.py" in str(item) for item in volumes)
    entrypoint = " ".join(str(item) for item in wechat["entrypoint"])
    assert "/custom-services.d/wechat-launcher" in entrypoint
    assert "exec /init" in entrypoint


def test_launcher_rpc_is_private_to_compose_network_and_not_forwarded():
    service = (ROOT / "scripts/wechat-launcher-service.py").read_text(encoding="utf-8")
    assert '_LISTEN = ("0.0.0.0", 8790)' in service
    assert "ThreadingHTTPServer" in service
    assert "/config/.control-token" in service
    assert "mp.weixin.qq.com" in service
    assert "Authorization" in service

    import json
    devcontainer = json.loads((ROOT / ".devcontainer/devcontainer.json").read_text(encoding="utf-8"))
    assert 8790 not in devcontainer["forwardPorts"]

    compose = yaml.safe_load((ROOT / ".devcontainer/docker-compose.yml").read_text(encoding="utf-8"))
    wechat = compose["services"]["wechat"]
    assert "ports" not in wechat


def test_real_compose_launcher_bridge_smoke_workflow_exists():
    workflow = (ROOT / ".github/workflows/launcher-bridge-smoke.yml").read_text(encoding="utf-8")
    assert "ghcr.io/nickrunning/wechat-selkies:0.0.16" in workflow
    assert "wechat:8790/healthz" in workflow
    assert "wechat:8790/open" in workflow
    assert "test-control-token" in workflow
    assert "dispatch_attempted" in workflow
