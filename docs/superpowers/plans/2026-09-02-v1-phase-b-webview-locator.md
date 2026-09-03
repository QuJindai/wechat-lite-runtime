# V1 Phase B WebView Locator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Identify the concrete authenticated WeChat WebView storage containers that carry public-account session/history context without returning any secret values.

**Architecture:** Restrict inspection to `state/.xwechat/radium/web`. Classify Chromium profile roots, Local Storage LevelDB directories, standard SQLite stores, and binary/text containers containing `mp.weixin.qq.com` markers. Return only sanitized relative paths, container types, safe SQLite schema names, and occurrence counts. No cookie/token/value payload is returned or logged.

**Tech Stack:** Python 3.12 standard library (`pathlib`, `sqlite3`, `hashlib`), FastAPI, pytest, existing bearer-token control API.

**Spec:** `docs/superpowers/specs/2026-09-02-v1-public-account-discovery-design.md`

## Global Constraints

- `state/` remains the private trust boundary.
- Never return Cookie values, Local Storage values, bearer/session tokens, QR content, raw DB rows, messages, contacts, or encryption keys.
- Only `.xwechat/radium/web` may be inspected in Phase B.
- File contents may be scanned internally only for fixed host/key-name needles; output may contain only aggregate occurrence counts and hashes, never matched bytes or surrounding text.
- SQLite output is limited to database class, sanitized path, table names, and column names; never query rows.
- CI uses synthetic fixtures only.

---

### Task 1: WebView Container Inventory

**Files:**
- Create: `app/webview_probe.py`
- Create: `tests/test_webview_probe.py`

**Interfaces:**
- Produces: `probe_webview_state(state_dir: Path) -> dict[str, object]`
- Produces: `classify_webview_container(path: Path, web_root: Path) -> str | None`
- Produces: `scan_fixed_markers(path: Path, needles: Sequence[bytes]) -> dict[str, int]`

- [ ] **Step 1: Write failing tests** with synthetic `profiles/web_shell`, `profiles/multitab_*`, `Local Storage/leveldb`, `Network/Cookies`, `Cookies`, `History`, and cache files. Assert only sanitized profile/path classes and counts are returned.
- [ ] **Step 2: Run** `python -m pytest tests/test_webview_probe.py -q` and verify RED because `app.webview_probe` does not exist.
- [ ] **Step 3: Implement** deterministic container classes: `profile_root`, `local_storage_leveldb`, `cookie_sqlite`, `history_sqlite`, `cache_store`, `other_webview_store`.
- [ ] **Step 4: Implement** fixed-marker scanning for `mp.weixin.qq.com`, `__biz`, `pass_ticket`, and `appmsg_token`; return counts only.
- [ ] **Step 5: Run** `python -m pytest tests/test_webview_probe.py -q` and verify GREEN.

### Task 2: Safe SQLite Schema Inspection

**Files:**
- Modify: `app/webview_probe.py`
- Modify: `tests/test_webview_probe.py`

**Interfaces:**
- Produces: `inspect_sqlite_schema(path: Path) -> dict[str, object]`

- [ ] **Step 1: Add failing tests** using synthetic SQLite files containing tables/columns plus secret-looking row values. Assert table/column names are returned while row values never appear.
- [ ] **Step 2: Run** targeted tests and verify RED.
- [ ] **Step 3: Implement** read-only SQLite schema inspection using `sqlite_master` plus `PRAGMA table_info`, with a maximum number of tables/columns and explicit `not_sqlite`/`locked` status.
- [ ] **Step 4: Re-run** targeted and full tests; verify GREEN.

### Task 3: Protected WebView Probe API

**Files:**
- Modify: `app/main.py`
- Create: `tests/test_webview_probe_api.py`

**Interfaces:**
- API: `GET /v1/wechat/webview-probe`

- [ ] **Step 1: Write failing API tests** for bearer protection, sanitized output, missing-web-root behavior, and absence of secret values.
- [ ] **Step 2: Run** `python -m pytest tests/test_webview_probe_api.py -q` and verify RED.
- [ ] **Step 3: Add** the protected endpoint using existing bearer auth and `settings.state_dir`.
- [ ] **Step 4: Run** API and V0 regression tests; verify GREEN.

### Task 4: One-Command Real Codespace Handoff

**Files:**
- Create: `scripts/probe-wechat-webview.sh`
- Modify: `README.md`
- Modify: `DEVELOPMENT.md`
- Create: `tests/test_v1_phase_b_handoff.py`

**Interfaces:**
- Command: `bash scripts/probe-wechat-webview.sh`
- Output: sanitized JSON from `/v1/wechat/webview-probe`

- [ ] **Step 1: Write failing tests** requiring the handoff command and security statement in README/DEVELOPMENT.
- [ ] **Step 2: Implement** a one-command script that force-reloads the control API, reads the local control token without printing it, calls loopback `/v1/wechat/webview-probe`, and prints only sanitized JSON.
- [ ] **Step 3: Run** `bash -n scripts/probe-wechat-webview.sh` and full pytest; verify GREEN.
- [ ] **Step 4: Require final-head CI success** on `feat/v1-public-account-discovery`.
- [ ] **Step 5: Physical gate:** run the probe in the already logged-in Codespace. Use only container type/schema/marker-count output to select the concrete authenticated history implementation.

## Phase B Exit Criteria

Phase B software is PASS when synthetic CI confirms container classification, marker-count-only scanning, schema-only SQLite inspection, protected API output, and one-command handoff. Phase B physical evidence is PASS when the real Codespace identifies at least one concrete profile/container carrying `mp.weixin.qq.com` markers or a standard cookie/history store without exposing any session value.
