#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

WECHAT_CONTROL_FORCE_RESTART=1 bash scripts/start-control-api.sh

python - <<'PY'
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from app.config import ensure_control_token

state_dir = Path(os.getenv("WECHAT_STATE_DIR", "state"))
token = ensure_control_token(state_dir, os.getenv("WECHAT_CONTROL_TOKEN"))
request = urllib.request.Request(
    "http://127.0.0.1:8787/v1/wechat/history-seed-status",
    headers={"Authorization": f"Bearer {token}"},
    method="GET",
)
try:
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
except urllib.error.HTTPError as exc:
    raise SystemExit(f"HISTORY_SEED_HTTP_ERROR={exc.code}") from exc
except urllib.error.URLError as exc:
    raise SystemExit(f"HISTORY_SEED_UNREACHABLE={exc.reason}") from exc

if payload.get("sensitive_values_returned") is not False:
    raise SystemExit("HISTORY_SEED_REJECTED=unexpected_sensitive_output_flag")

print(json.dumps(payload, ensure_ascii=False, indent=2))
PY
