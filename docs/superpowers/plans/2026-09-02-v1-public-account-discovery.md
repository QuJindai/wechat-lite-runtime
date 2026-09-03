# V1 Public Account Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a safe, testable authenticated-WeChat discovery layer that can identify runtime artifacts, normalize public-account article metadata, and expose local APIs without leaking session material.

**Architecture:** V1 starts with a sanitized structural probe over the persisted WeChat state, then adds redaction helpers and normalized discovery models, then a provider protocol with synthetic fixtures, and finally authenticated FastAPI endpoints. Real WebView history extraction is only implemented after the safe probe identifies the concrete artifact classes present in the real Codespace.

**Tech Stack:** Python 3.12, FastAPI, pytest, standard-library pathlib/sqlite3/urllib/url parsing, existing bearer-token control API.

**Spec:** `docs/superpowers/specs/2026-09-02-v1-public-account-discovery-design.md`

## Global Constraints

- `state/` is the private trust boundary; no cookie, auth token, QR content, raw database row, chat/contact content, browser profile file or encryption key may be returned.
- CI uses synthetic fixtures only; no real WeChat session files are committed.
- API output may include only account/article metadata, completeness flags, sanitized artifact classes and sanitized relative roots.
- `count_satisfied`, `timestamps_complete`, `urls_unique`, `account_verified`, `freshness_verified`, and `is_exhaustive_for_window` remain independent flags.
- V1 newest-20 PASS requires 20 articles, valid timestamps, unique canonical URLs, verified account identity, verified freshness, and manual first/20th UI cross-check.

---

### Task 1: Safe Runtime Artifact Probe

**Files:**
- Create: `app/wechat_probe.py`
- Create: `tests/test_wechat_probe.py`
- Modify: `app/main.py`

**Interfaces:**
- Produces: `probe_state(state_dir: Path) -> dict[str, object]`
- Produces: `classify_artifact(path: Path, state_dir: Path) -> str | None`
- API: `GET /v1/wechat/probe`

- [ ] **Step 1: Write failing tests** for synthetic trees containing `xwechat_files`, Chromium/WebView cache names, SQLite files, `mp.weixin.qq.com` traces, and unrelated files. Assert the response contains only class/count/sanitized-root information and never file contents.
- [ ] **Step 2: Run** `python -m pytest tests/test_wechat_probe.py -q` and verify RED because `app.wechat_probe` does not exist.
- [ ] **Step 3: Implement** deterministic classification with classes `xwechat_db`, `webview_cache`, `mp_weixin_trace`, `cookie_store`, and `other_candidate`; sanitize roots to at most three path components and replace account-looking directory segments with `<redacted>`.
- [ ] **Step 4: Add** `/v1/wechat/probe` protected by the existing bearer dependency and returning `sensitive_values_returned=false`.
- [ ] **Step 5: Run** `python -m pytest tests/test_wechat_probe.py tests/test_api.py -q` and verify GREEN.

### Task 2: Article Models, URL Canonicalization, Redaction and Completeness

**Files:**
- Create: `app/public_accounts.py`
- Create: `tests/test_public_accounts.py`

**Interfaces:**
- Produces: `normalize_article(raw: Mapping[str, object], position: int) -> ArticleRecord`
- Produces: `canonicalize_mp_url(url: str) -> str`
- Produces: `build_discovery_result(records: Sequence[ArticleRecord], requested_count: int, ...) -> DiscoveryResult`
- Produces: `redact_sensitive_text(value: str) -> str`

- [ ] **Step 1: Write failing tests** for canonical `mp.weixin.qq.com/s/...` URLs, auth-bearing query removal, timestamp parsing, deterministic duplicate collapse, newest-first ordering, and independent completeness flags.
- [ ] **Step 2: Run** `python -m pytest tests/test_public_accounts.py -q` and verify RED.
- [ ] **Step 3: Implement** immutable dataclasses `ArticleRecord` and `DiscoveryResult`; canonicalization must retain only public article identity parameters and strip `key`, `pass_ticket`, `uin`, `token`, `auth`, `cookie`, `session`, `scene` and equivalent sensitive parameters.
- [ ] **Step 4: Implement** redaction that masks bearer/cookie/token-like text in error strings before logging or API return.
- [ ] **Step 5: Run** `python -m pytest tests/test_public_accounts.py -q` and verify GREEN.

### Task 3: Provider Protocol and Synthetic Pagination Provider

**Files:**
- Create: `app/providers.py`
- Create: `tests/fixtures/wechat_history/page1.json`
- Create: `tests/fixtures/wechat_history/page2.json`
- Create: `tests/test_providers.py`

**Interfaces:**
- Produces protocol: `PublicAccountProvider.recent_articles(account: str, limit: int, since: datetime | None = None) -> DiscoveryResult`
- Produces: `SyntheticHistoryProvider(fixture_dir: Path)`

- [ ] **Step 1: Write failing tests** where two fixture pages contain overlapping URLs; request 20 and assert exactly 20 unique, newest-first normalized records with complete timestamps.
- [ ] **Step 2: Run** `python -m pytest tests/test_providers.py -q` and verify RED.
- [ ] **Step 3: Implement** the provider protocol and synthetic provider with explicit errors `LOGIN_REQUIRED`, `ACCOUNT_NOT_FOUND`, `HISTORY_SURFACE_UNAVAILABLE`, `PAGINATION_INCOMPLETE`.
- [ ] **Step 4: Ensure** pagination cursor returned by the synthetic provider is opaque and contains no URL query/token material.
- [ ] **Step 5: Run** `python -m pytest tests/test_providers.py -q` and verify GREEN.

### Task 4: Authenticated Local API Contract

**Files:**
- Modify: `app/main.py`
- Create: `tests/test_public_account_api.py`

**Interfaces:**
- API: `GET /v1/public-accounts/{account}/recent?limit=20`
- Uses provider injected into `create_app(..., public_account_provider=...)`

- [ ] **Step 1: Write failing API tests** asserting bearer protection, limit validation `1..100`, normalized JSON shape, explicit provider error mapping, and zero sensitive fields.
- [ ] **Step 2: Run** `python -m pytest tests/test_public_account_api.py -q` and verify RED.
- [ ] **Step 3: Extend** `create_app` with an injectable provider while preserving all V0 endpoints and defaults.
- [ ] **Step 4: Implement** `/v1/public-accounts/{account}/recent` with structured error responses and no session-derived values.
- [ ] **Step 5: Run** `python -m pytest tests/test_public_account_api.py tests/test_api.py -q` and verify GREEN.

### Task 5: CI Gate and Real-Codespace Probe Handoff

**Files:**
- Create: `scripts/probe-wechat-state.sh`
- Modify: `README.md`
- Modify: `DEVELOPMENT.md`
- Test: `tests/test_codespace_config.py`

**Interfaces:**
- Command: `bash scripts/probe-wechat-state.sh`
- Output: sanitized JSON from `/v1/wechat/probe`

- [ ] **Step 1: Write failing tests** requiring README/DEVELOPMENT to document the safe probe command and the next physical gate.
- [ ] **Step 2: Implement** a one-command script that self-heals the control API, reads the persisted local control token without printing it, calls loopback `/v1/wechat/probe`, and prints only the sanitized JSON response.
- [ ] **Step 3: Run** `bash -n scripts/probe-wechat-state.sh` and `python -m pytest -q`.
- [ ] **Step 4: Push** the completed software layer to `feat/v1-public-account-discovery` and require Push/PR CI success on the final head.
- [ ] **Step 5: Physical handoff:** run the probe in the already logged-in Codespace and use its sanitized artifact-class output to choose the concrete WebView extraction implementation. Do not implement WebView cookie/session reading until this evidence exists.

## Plan Self-Review

- Spec coverage: safe probe, security boundary, normalized models, provider abstraction, API contract, completeness semantics, synthetic CI, and physical newest-20 progression are all represented.
- No real WeChat files enter CI or Git.
- The plan intentionally stops before real WebView extraction because the concrete storage/session artifact must be established by the safe probe first; this avoids guessing paths or reading unrelated user data.
- Type names and endpoint paths match the approved design spec.
