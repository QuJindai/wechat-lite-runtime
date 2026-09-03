#!/usr/bin/env python3
from __future__ import annotations

import hmac
import json
import os
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

_LISTEN = (os.getenv("WECHAT_LAUNCHER_HOST", "127.0.0.1"), 8790)
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


def _valid_account_name(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized or len(normalized) > 256 or any(ord(char) < 32 for char in normalized):
        return None
    return normalized


def _desktop_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("DISPLAY", ":1")
    env["HOME"] = "/config"
    env.setdefault("XDG_CONFIG_HOME", "/config/.config")
    env.setdefault("XDG_CACHE_HOME", "/config/.cache")
    env.setdefault("XDG_DATA_HOME", "/config/.local/share")
    xauthority = Path("/config/.Xauthority")
    if xauthority.exists():
        env.setdefault("XAUTHORITY", str(xauthority))
    return env


def _as_desktop_user(argv: list[str]) -> list[str]:
    setuid = shutil.which("s6-setuidgid")
    if os.geteuid() == 0 and setuid:
        return [setuid, "abc", *argv]
    runuser = shutil.which("runuser")
    if os.geteuid() == 0 and runuser:
        return [runuser, "-u", "abc", "--", *argv]
    return argv


def _wechat_command(target_url: str) -> tuple[list[str], dict[str, str]]:
    return _as_desktop_user(["/usr/bin/wechat", target_url]), _desktop_env()


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


def _run_desktop(argv: list[str], *, input_bytes: bytes | None = None, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        _as_desktop_user(argv),
        env=_desktop_env(),
        input=input_bytes,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=3.0,
        check=False,
    )


def _search_public_account(account_name: str) -> dict[str, object]:
    xdotool = shutil.which("xdotool")
    xclip = shutil.which("xclip")
    if not xdotool or not xclip:
        return {"dispatch_attempted": False, "window_found": False, "search_submitted": False}

    with _LAUNCH_LOCK:
        try:
            found = _run_desktop([xdotool, "search", "--onlyvisible", "--class", "wechat"], capture=True)
            window_ids = [line.strip() for line in found.stdout.decode("ascii", errors="ignore").splitlines() if line.strip().isdigit()]
            if found.returncode != 0 or not window_ids:
                return {"dispatch_attempted": False, "window_found": False, "search_submitted": False}
            window_id = window_ids[0]
            activate = _run_desktop([xdotool, "windowactivate", "--sync", window_id])
            focus_search = _run_desktop([xdotool, "key", "--clearmodifiers", "ctrl+f"])
            write_clipboard = _run_desktop([xclip, "-selection", "clipboard"], input_bytes=account_name.encode("utf-8"))
            paste = _run_desktop([xdotool, "key", "--clearmodifiers", "ctrl+v"])
            time.sleep(0.4)
            submit = _run_desktop([xdotool, "key", "--clearmodifiers", "Return"])
            try:
                _run_desktop([xclip, "-selection", "clipboard"], input_bytes=b"")
            except Exception:
                pass
            dispatched = all(
                step.returncode == 0
                for step in (activate, focus_search, write_clipboard, paste)
            )
            return {
                "dispatch_attempted": dispatched,
                "window_found": True,
                "search_submitted": dispatched and submit.returncode == 0,
            }
        except (OSError, subprocess.SubprocessError):
            return {"dispatch_attempted": False, "window_found": False, "search_submitted": False}


class Handler(BaseHTTPRequestHandler):
    server_version = "wechat-launcher/2"

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
        if self.path not in {"/open", "/search"}:
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
        if not isinstance(payload, dict):
            self._json(400, {"error": "invalid_json"})
            return

        if self.path == "/open":
            target = _valid_target(payload.get("url"))
            if target is None:
                self._json(400, {"error": "invalid_target"})
                return
            self._json(200, _launch(target))
            return

        account_name = _valid_account_name(payload.get("account_name"))
        if account_name is None:
            self._json(400, {"error": "invalid_account_name"})
            return
        self._json(200, _search_public_account(account_name))

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer(_LISTEN, Handler).serve_forever()
