#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

TARGET_FILE="config/v1-physical-acceptance-target.json"
RESULT_FILE="state/.v1-newest20-acceptance-latest.json"
[[ -f "$TARGET_FILE" ]] || exit 0
mkdir -p state

python - <<'PY'
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from app.config import ensure_control_token

target_path = Path("config/v1-physical-acceptance-target.json")
result_path = Path("state/.v1-newest20-acceptance-latest.json")
target = json.loads(target_path.read_text(encoding="utf-8"))
fingerprint = hashlib.sha256(json.dumps(target, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]

if result_path.is_file():
    try:
        previous = json.loads(result_path.read_text(encoding="utf-8"))
    except Exception:
        previous = {}
    if previous.get("target_fingerprint") == fingerprint and (previous.get("response") or {}).get("verdict") == "AUTOMATED_GATE_PASS_UI_PENDING":
        raise SystemExit(0)

state_dir = Path(os.getenv("WECHAT_STATE_DIR", "state"))
token = ensure_control_token(state_dir, os.getenv("WECHAT_CONTROL_TOKEN"))

# Wait for WeChat Web UI readiness before attempting authenticated discovery.
for _ in range(60):
    req = urllib.request.Request(
        "http://127.0.0.1:8787/v1/runtime/status",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as response:
            status_payload = json.loads(response.read().decode("utf-8"))
        if status_payload.get("wechat_web_ready"):
            break
    except Exception:
        pass
    time.sleep(2)

payload = json.dumps({
    "account_name": target["account_name"],
    "biz": target["biz"],
}, ensure_ascii=False).encode("utf-8")

last = None
for attempt in range(3):
    req = urllib.request.Request(
        "http://127.0.0.1:8787/v1/public-accounts/acceptance",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            last = {"http_status": response.status, "response": json.loads(response.read().decode("utf-8"))}
        break
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body)
        except Exception:
            detail = {"detail": "acceptance_http_error"}
        last = {"http_status": exc.code, "response": detail}
        if exc.code not in {409, 503}:
            break
    except Exception:
        last = {"http_status": 0, "response": {"detail": "acceptance_unreachable"}}
    time.sleep(10 * (attempt + 1))

record = {
    "target_fingerprint": fingerprint,
    "target": target,
    **(last or {"http_status": 0, "response": {"detail": "acceptance_not_attempted"}}),
    "sensitive_values_returned": False,
}
result_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
result_path.chmod(0o600)
PY
