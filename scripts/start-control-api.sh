#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="/tmp/wechat-lite-runtime-api.pid"
LOG_FILE="/tmp/wechat-lite-runtime-api.log"
HEALTH_URL="http://127.0.0.1:8787/healthz"
FORCE_RESTART="${WECHAT_CONTROL_FORCE_RESTART:-0}"

cd "$ROOT_DIR"

healthcheck() {
  python - "$HEALTH_URL" <<'PY'
import sys
import urllib.request

url = sys.argv[1]
try:
    with urllib.request.urlopen(url, timeout=1) as response:
        raise SystemExit(0 if response.status == 200 else 1)
except Exception:
    raise SystemExit(1)
PY
}

stop_pid_file_process() {
  if [[ -f "$PID_FILE" ]]; then
    existing_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
      kill "$existing_pid" 2>/dev/null || true
      for _ in $(seq 1 20); do
        if ! kill -0 "$existing_pid" 2>/dev/null; then
          break
        fi
        sleep 0.1
      done
    fi
    rm -f "$PID_FILE"
  fi
}

if [[ "$FORCE_RESTART" == "1" ]]; then
  stop_pid_file_process
  if healthcheck; then
    pkill -f 'python -m uvicorn app.main:app.*--port 8787' 2>/dev/null || true
    sleep 0.2
  fi
else
  if healthcheck; then
    echo "CONTROL_API_READY=1"
    exit 0
  fi
  stop_pid_file_process
fi

if ! python - <<'PY'
import fastapi
import uvicorn
PY
then
  echo "CONTROL_API_DEPENDENCIES=INSTALLING"
  python -m pip install -r requirements.txt
fi

: >"$LOG_FILE"
nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8787 >"$LOG_FILE" 2>&1 &
pid=$!
echo "$pid" >"$PID_FILE"

for _ in $(seq 1 40); do
  if healthcheck; then
    echo "CONTROL_API_READY=1"
    echo "CONTROL_API_PID=$pid"
    exit 0
  fi
  if ! kill -0 "$pid" 2>/dev/null; then
    break
  fi
  sleep 0.25
done

echo "CONTROL_API_READY=0" >&2
echo "CONTROL_API_LOG_BEGIN" >&2
tail -n 120 "$LOG_FILE" >&2 || true
echo "CONTROL_API_LOG_END" >&2
exit 1
