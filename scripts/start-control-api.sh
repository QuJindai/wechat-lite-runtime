#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="/tmp/wechat-lite-runtime-api.pid"
LOG_FILE="/tmp/wechat-lite-runtime-api.log"

if [[ -f "$PID_FILE" ]]; then
  existing_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
    exit 0
  fi
  rm -f "$PID_FILE"
fi

cd "$ROOT_DIR"
nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8787 >"$LOG_FILE" 2>&1 &
echo $! >"$PID_FILE"
