#!/usr/bin/env python3
from __future__ import annotations

import hmac
import json
import os
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

_LISTEN = ("127.0.0.1", 8790)
_TOKEN_FILE = Path("/config/.control-token")
_MAX_BODY = 16 * 1024
_LAUNCH_LOCK = threading.Lock()


def _read_token() -> str:
    explicit = os.getenv("WECHAT_CONTROL_TOKEN", "").strip()
    if explicit:
        return explicit
    try:
        return _TOKEN_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _valid_target(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 8192:
        return None
    try:
        parsed = urlsplit(value)
        query = parse_qs(parsed.query, keep_blank_values=True)
    except ValueError:
        return None
    if parsed.scheme != "https" or parsed.hostname != "mp.weixin.qq.com" or parsed.path != "/mp/profile_ext":
        return None
    action = (query.get("action") or [""])[0]
    biz = (query.get("__biz") or [""])[0]
    if action not in {"home", "getmsg"} or not biz or any(char.isspace() for char in biz):
        return None
    return value


def _wechat_command(target_url: str) -> tuple[list[str], dict[str, str]]:
    env = os.environ.copy()
    env.setdefault("DISPLAY", ":1")
    env["HOME"] = "/config"
    env.setdefault("XDG_CONFIG_HOME", "/config/.config")
    env.setdefault("XDG_CACHE_HOME", "/config/.cache")
    env.setdefault("XDG_DATA_HOME", "/config/.local/share")
    binary = "/usr/bin/wechat"
    setuid = shutil.which("s6-setuidgid")
    if os.geteuid() == 0 and setuid:
        return [setuid, "abc", binary, target_url], env
    runuser = shutil.which("runuser")
    if os.geteuid() == 0 and runuser:
        return [runuser, "-u", "abc", "--", binary, target_url], env
    return [binary, target_url], env


def _launch(target_url: str) -> dict[str, object]:
    argv, env = _wechat_command(target_url)
    with _LAUNCH_LOCK:
        try:
            completed = subprocess.run(
                argv,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=4.0,
                check=False,
            )
            exit_code = int(completed.returncode)
        except subprocess.TimeoutExpired:
            exit_code = 124
        except OSError:
            exit_code = 127
    return {
        "dispatch_attempted": exit_code in {0, 255},
        "exit_code": exit_code,
        "secondary_instance_exit": exit_code == 255,
        "executable": "/usr/bin/wechat",
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "wechat-launcher/1"

    def _json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._json(200, {"status": "ok"})
        else:
            self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        if self.path != "/open":
            self._json(404, {"error": "not_found"})
            return
        token = _read_token()
        if not token:
            self._json(503, {"error": "control_token_not_ready"})
            return
        auth = self.headers.get("Authorization", "")
        expected = f"Bearer {token}"
        if not hmac.compare_digest(auth, expected):
            self._json(401, {"error": "unauthorized"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length < 1 or length > _MAX_BODY:
            self._json(400, {"error": "invalid_body"})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(400, {"error": "invalid_json"})
            return
        target = _valid_target(payload.get("url") if isinstance(payload, dict) else None)
        if target is None:
            self._json(400, {"error": "invalid_target"})
            return
        self._json(200, _launch(target))

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer(_LISTEN, Handler).serve_forever()
