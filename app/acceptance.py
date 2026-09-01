from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping

from app.config import ensure_control_token

SNAPSHOT_FILE = ".v0-acceptance-before.json"
DEFAULT_STATUS_URL = "http://127.0.0.1:8787/v1/runtime/status"


def safe_snapshot(status: Mapping[str, Any]) -> dict[str, Any]:
    storage = status.get("session_storage") or {}
    return {
        "codespace_name": status.get("codespace_name"),
        "wechat_web_ready": bool(status.get("wechat_web_ready")),
        "ui_url": status.get("ui_url"),
        "session_initialized": bool(storage.get("initialized")),
        "file_count": int(storage.get("file_count", 0)),
        "total_bytes": int(storage.get("total_bytes", 0)),
    }


def evaluate_restart(
    before: Mapping[str, Any],
    current: Mapping[str, Any],
    *,
    marker_exists: bool,
) -> dict[str, Any]:
    if (
        not marker_exists
        or not bool(before.get("session_initialized"))
        or not bool(current.get("session_initialized"))
    ):
        verdict = "STATE_LOST"
    elif not bool(current.get("wechat_web_ready")):
        verdict = "RUNTIME_NOT_READY"
    else:
        verdict = "STORAGE_PASS_AUTH_PENDING"

    return {
        "verdict": verdict,
        "marker_survived": marker_exists,
        "session_initialized_before": bool(before.get("session_initialized")),
        "session_initialized_after": bool(current.get("session_initialized")),
        "wechat_web_ready_after": bool(current.get("wechat_web_ready")),
        "manual_login_check_required": verdict == "STORAGE_PASS_AUTH_PENDING",
        "ui_url": current.get("ui_url"),
    }


def record_before(state_dir: Path, status: Mapping[str, Any]) -> dict[str, Any]:
    state_dir.mkdir(parents=True, exist_ok=True)
    snapshot = safe_snapshot(status)
    marker = state_dir / SNAPSHOT_FILE
    marker.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "verdict": "BASELINE_RECORDED",
        "snapshot": snapshot,
        "marker": str(marker),
        "next_action": "Stop this Codespace, start the same Codespace, then run: python -m app.acceptance after",
    }


def verify_after(state_dir: Path, status: Mapping[str, Any]) -> dict[str, Any]:
    marker = state_dir / SNAPSHOT_FILE
    marker_exists = marker.exists()
    if marker_exists:
        try:
            before = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            before = {"session_initialized": False}
            marker_exists = False
    else:
        before = {"session_initialized": False}

    current = safe_snapshot(status)
    result = evaluate_restart(before, current, marker_exists=marker_exists)
    result["before"] = before
    result["after"] = current
    return result


def fetch_runtime_status(token: str, url: str = DEFAULT_STATUS_URL) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"control_api_http_{exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"control_api_unreachable: {exc.reason}") from exc


def _print_result(result: Mapping[str, Any]) -> None:
    print(json.dumps(dict(result), ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="WeChat V0 Codespaces persistence acceptance helper")
    parser.add_argument("mode", choices=("before", "after"))
    parser.add_argument(
        "--state-dir",
        default=os.getenv("WECHAT_STATE_DIR", "state"),
        help="Persistent WeChat state directory",
    )
    parser.add_argument(
        "--status-url",
        default=DEFAULT_STATUS_URL,
        help="Control API runtime-status URL",
    )
    args = parser.parse_args(argv)

    state_dir = Path(args.state_dir)
    token = ensure_control_token(state_dir, os.getenv("WECHAT_CONTROL_TOKEN"))

    try:
        status = fetch_runtime_status(token, args.status_url)
    except RuntimeError as exc:
        _print_result({"verdict": "CONTROL_API_ERROR", "error": str(exc)})
        return 2

    if args.mode == "before":
        result = record_before(state_dir, status)
        if not result["snapshot"]["session_initialized"]:
            result["verdict"] = "LOGIN_NOT_INITIALIZED"
            _print_result(result)
            return 2
        _print_result(result)
        return 0

    result = verify_after(state_dir, status)
    _print_result(result)
    return 0 if result["verdict"] == "STORAGE_PASS_AUTH_PENDING" else 2


if __name__ == "__main__":
    sys.exit(main())
