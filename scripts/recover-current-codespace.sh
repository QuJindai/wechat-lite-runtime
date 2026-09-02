#!/usr/bin/env bash
set -euo pipefail

REPO="QuJindai/wechat-lite-runtime"
BRANCH="feat/v0-codespace-runtime"
WORKSPACE="${CODESPACE_VSCODE_FOLDER:-/workspaces/wechat-lite-runtime}"
RECOVERY_DIR="$WORKSPACE/state/recovery"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

if [[ "${CODESPACES:-}" != "true" ]]; then
  echo "ERROR: this script must run inside GitHub Codespaces." >&2
  exit 2
fi

cd "$WORKSPACE"
mkdir -p "$RECOVERY_DIR"

# Preserve tracked local edits before resetting. state/ is git-ignored and remains untouched.
git diff > "$RECOVERY_DIR/pre-sync-$STAMP.patch" || true
git diff --cached > "$RECOVERY_DIR/pre-sync-staged-$STAMP.patch" || true
git status --porcelain=v1 > "$RECOVERY_DIR/pre-sync-status-$STAMP.txt" || true

printf 'RECOVERY_STEP=fetch_latest\n'
git fetch origin "$BRANCH"

printf 'RECOVERY_STEP=reset_to_remote\n'
git reset --hard "origin/$BRANCH"

HEAD_SHORT="$(git rev-parse --short HEAD)"
printf 'RECOVERY_HEAD=%s\n' "$HEAD_SHORT"

# Codespaces CLI is normally available in a Codespace. Use the session token without printing it.
if ! command -v gh >/dev/null 2>&1; then
  echo "RECOVERY_SYNC=PASS"
  echo "RECOVERY_REBUILD=NEEDS_UI"
  echo "Run: Codespaces: Rebuild Container"
  exit 0
fi

if [[ -n "${GITHUB_TOKEN:-}" && -z "${GH_TOKEN:-}" ]]; then
  export GH_TOKEN="$GITHUB_TOKEN"
fi

if [[ -z "${CODESPACE_NAME:-}" ]]; then
  echo "RECOVERY_SYNC=PASS"
  echo "RECOVERY_REBUILD=NEEDS_UI"
  echo "Run: Codespaces: Rebuild Container"
  exit 0
fi

printf 'RECOVERY_STEP=rebuild_codespace name=%s\n' "$CODESPACE_NAME"
# Rebuilding the current Codespace may terminate this shell immediately on success.
if gh codespace rebuild -c "$CODESPACE_NAME" -R "$REPO"; then
  echo "RECOVERY_REBUILD=REQUESTED"
else
  echo "RECOVERY_SYNC=PASS"
  echo "RECOVERY_REBUILD=NEEDS_UI"
  echo "Run: Codespaces: Rebuild Container"
  exit 0
fi
