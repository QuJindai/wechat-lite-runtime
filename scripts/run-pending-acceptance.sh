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

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from app.config import ensure_control_token
from app.pending_acceptance import (
    AcceptanceCacheIdentity,
    build_safe_session_generation,
    build_target_fingerprint,
    can_reuse_pass,
    read_git_head,
)

target_path = Path("config/v1-physical-acceptance-target.json")
result_path = Path("state/.v1-newest20-acceptance-latest.json")
target = json.loads(target_path.read_text(encoding="utf-8"))
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

cache_identity = AcceptanceCacheIdentity(
    target_fingerprint=build_target_fingerprint(target),
    git_head=read_git_head(Path.cwd()),
    session_generation=build_safe_session_generation(state_dir),
)
if result_path.is_file():
    try:
        previous = json.loads(result_path.read_text(encoding="utf-8"))
    except Exception:
        previous = {}
    if isinstance(previous, dict) and can_reuse_pass(previous, cache_identity):
        raise SystemExit(0)

payload = json.dumps({
    "article_url": target["article_url"],
}, ensure_ascii=False).encode("utf-8")

last = None
for attempt in range(3):
    req = urllib.request.Request(
        "http://127.0.0.1:8787/v1/public-accounts/acceptance-from-url",
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

final_identity = AcceptanceCacheIdentity(
    target_fingerprint=cache_identity.target_fingerprint,
    git_head=cache_identity.git_head,
    session_generation=build_safe_session_generation(state_dir),
)
record = {
    **final_identity.to_dict(),
    "target": target,
    **(last or {"http_status": 0, "response": {"detail": "acceptance_not_attempted"}}),
    "sensitive_values_returned": False,
}
temporary_path = result_path.with_name(f"{result_path.name}.tmp.{os.getpid()}")
data = (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
fd = os.open(temporary_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
try:
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary_path, result_path)
    if os.name != "nt":
        result_path.chmod(0o600)
finally:
    try:
        temporary_path.unlink()
    except OSError:
        pass
PY
