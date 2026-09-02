#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python - <<'PY'
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from app.config import ensure_control_token

root = Path.cwd()
target_path = root / "config" / "v1-physical-acceptance-target.json"
state_dir = Path(os.getenv("WECHAT_STATE_DIR", "state"))
output_path = state_dir / ".v1-newest20-acceptance-latest.json"

if not target_path.is_file():
    raise SystemExit(0)

try:
    target = json.loads(target_path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    raise SystemExit(0)

account_name = str(target.get("account_name") or "").strip()
biz = str(target.get("biz") or "").strip()
if not account_name or not biz:
    raise SystemExit(0)

token = ensure_control_token(state_dir, os.getenv("WECHAT_CONTROL_TOKEN"))
request_body = json.dumps({"account_name": account_name, "biz": biz}).encode("utf-8")
url = "http://127.0.0.1:8787/v1/public-accounts/acceptance"
result: dict[str, object] | None = None

for attempt in range(1, 4):
    request = urllib.request.Request(
        url,
        data=request_body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            result = json.loads(response.read().decode("utf-8"))
        break
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8", errors="replace"))
        except Exception:
            body = {"detail": {"code": "HTTP_ERROR"}}
        result = {
            "verdict": "PHYSICAL_ACCEPTANCE_PENDING",
            "http_status": int(exc.code),
            "error": body.get("detail") if isinstance(body, dict) else {"code": "HTTP_ERROR"},
            "attempt": attempt,
            "sensitive_values_returned": False,
        }
        if exc.code not in {409, 502, 503}:
            break
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        result = {
            "verdict": "PHYSICAL_ACCEPTANCE_PENDING",
            "error": {"code": "CONTROL_API_UNAVAILABLE"},
            "attempt": attempt,
            "sensitive_values_returned": False,
        }
    if attempt < 3:
        time.sleep(5)

if result is None:
    result = {
        "verdict": "PHYSICAL_ACCEPTANCE_PENDING",
        "error": {"code": "NO_RESULT"},
        "sensitive_values_returned": False,
    }

result["target"] = {
    "article_url": str(target.get("article_url") or ""),
    "account_name": account_name,
    "biz": biz,
}
output_path.parent.mkdir(parents=True, exist_ok=True)
temp = output_path.with_suffix(output_path.suffix + ".tmp")
temp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
os.chmod(temp, 0o600)
temp.replace(output_path)
os.chmod(output_path, 0o600)
PY
