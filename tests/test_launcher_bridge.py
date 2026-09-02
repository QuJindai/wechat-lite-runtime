import json
from pathlib import Path
from urllib.error import URLError

import pytest

from app.launcher_bridge import HttpWechatURLLauncher


class FakeResponse:
    def __init__(self, payload: dict[str, object], status: int = 200) -> None:
        self.payload = json.dumps(payload).encode()
        self.status = status

    def read(self, amount: int = -1) -> bytes:
        return self.payload

    def close(self) -> None:
        pass


def test_http_launcher_calls_only_loopback_bridge_and_keeps_token_private():
    seen = []

    def opener(request, timeout):
        seen.append((request, timeout))
        return FakeResponse({
            "dispatch_attempted": True,
            "exit_code": 255,
            "secondary_instance_exit": True,
            "executable": "/usr/bin/wechat",
        })

    launcher = HttpWechatURLLauncher("CONTROL_SECRET", opener=opener, timeout_seconds=2.0)
    evidence = launcher.open_public_account("BIZ_PUBLIC")

    assert evidence.dispatch_attempted is True
    assert evidence.exit_code == 255
    assert evidence.secondary_instance_exit is True
    assert evidence.executable == "wechat-container:/usr/bin/wechat"
    assert len(seen) == 1
    request, timeout = seen[0]
    assert request.full_url == "http://127.0.0.1:8790/open"
    assert timeout == 2.0
    assert request.headers["Authorization"] == "Bearer CONTROL_SECRET"
    body = json.loads(request.data.decode())
    assert body["url"].startswith("https://mp.weixin.qq.com/mp/profile_ext?")
    assert "__biz=BIZ_PUBLIC" in body["url"]
    rendered = repr(launcher) + repr(evidence.safe_summary())
    assert "CONTROL_SECRET" not in rendered
    assert "BIZ_PUBLIC" not in rendered


def test_http_launcher_rejects_non_loopback_bridge_endpoint():
    with pytest.raises(ValueError):
        HttpWechatURLLauncher("secret", endpoint="http://wechat:8790/open")
    with pytest.raises(ValueError):
        HttpWechatURLLauncher("secret", endpoint="https://example.com/open")


def test_http_launcher_network_failure_is_safe_failed_dispatch():
    def opener(request, timeout):
        raise URLError("CONTROL_SECRET BIZ_PUBLIC")

    launcher = HttpWechatURLLauncher("CONTROL_SECRET", opener=opener)
    evidence = launcher.open_public_account("BIZ_PUBLIC")
    assert evidence.dispatch_attempted is False
    assert evidence.exit_code == 127
    rendered = repr(launcher) + repr(evidence.safe_summary())
    assert "CONTROL_SECRET" not in rendered
    assert "BIZ_PUBLIC" not in rendered


def test_control_token_is_required():
    with pytest.raises(ValueError):
        HttpWechatURLLauncher("")
