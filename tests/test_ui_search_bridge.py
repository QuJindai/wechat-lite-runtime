import io
import json
from pathlib import Path

from app.launcher_bridge import HttpWechatURLLauncher


class Response:
    status = 200

    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def read(self, amount=-1):
        return self.payload if amount < 0 else self.payload[:amount]

    def close(self):
        pass


def test_http_bridge_search_posts_name_internally_but_safe_evidence_never_echoes_it():
    seen = {}

    def opener(request, timeout):
        seen["url"] = request.full_url
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = json.loads(request.data.decode())
        return Response({"dispatch_attempted": True, "window_found": True, "search_submitted": True})

    bridge = HttpWechatURLLauncher("CONTROL_SECRET", opener=opener)
    evidence = bridge.search_public_account("示例公众号")

    assert seen["url"] == "http://127.0.0.1:8790/search"
    assert seen["auth"] == "Bearer CONTROL_SECRET"
    assert seen["body"] == {"account_name": "示例公众号"}
    assert evidence.dispatch_attempted is True
    assert evidence.window_found is True
    assert evidence.search_submitted is True
    rendered = repr(evidence) + repr(evidence.safe_summary())
    assert "示例公众号" not in rendered
    assert "CONTROL_SECRET" not in rendered


def test_launcher_service_search_sequence_is_keyboard_only_and_does_not_read_clipboard_or_click_chat():
    root = Path(__file__).resolve().parents[1]
    script = (root / "scripts" / "wechat-launcher-service.py").read_text(encoding="utf-8")
    assert '"/search"' in script
    assert "xdotool" in script
    assert "windowactivate" in script
    assert "ctrl+f" in script.lower()
    assert "xclip" in script
    assert "ctrl+v" in script.lower()
    assert "Return" in script
    assert "mousemove" not in script
    assert "click" not in script
    assert "xclip -o" not in script
