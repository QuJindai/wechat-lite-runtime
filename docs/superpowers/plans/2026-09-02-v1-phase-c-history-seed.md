# V1 Phase C Authenticated History Seed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn a WeChat-opened public-account history page into a private in-runtime authenticated pagination seed, then normalize recent article metadata without exposing authentication parameters.

**Architecture:** CDP is unavailable in the official Linux WeChat `WeChatAppEx`; port 8082 is Selkies WebSocket transport. Phase C therefore uses Chromium History as the bootstrap boundary: GUI navigation opens the public-account history surface once, a read-only History adapter selects the newest `mp.weixin.qq.com/mp/profile_ext` URL, and an internal HTTP pager reuses that private URL context while varying only pagination parameters. Raw seed URLs and auth-bearing query values never leave process memory or appear in logs/API responses.

**Tech Stack:** Python 3.12, sqlite3 read-only snapshots, urllib/url parsing, injected HTTP transport for synthetic tests, FastAPI/pytest, X11 automation later as a separate adapter.

**Spec:** `docs/superpowers/specs/2026-09-02-v1-public-account-discovery-design.md`

## Global Constraints

- `state/` remains the private trust boundary.
- Raw History rows, raw seed URLs, auth query values, request headers and session material must never be returned or logged.
- Only `mp.weixin.qq.com/mp/profile_ext` history candidates may become history seeds.
- CI uses synthetic History databases and synthetic HTTP pages only.
- Provider output remains the normalized `DiscoveryResult` model and independent completeness flags.
- The first real gate remains one named public account -> newest 20 -> complete timestamps -> unique URLs -> verified account/freshness -> first/20th UI cross-check.

---

### Task 1: Read-only Chromium History Seed Locator

**Files:**
- Create: `app/history_seed.py`
- Create: `tests/test_history_seed.py`

**Interfaces:**
- `locate_history_seed(history_db: Path) -> HistorySeed | None`
- `HistorySeed` stores the private raw URL but exposes only `safe_summary()`.

- [ ] Write RED tests using a synthetic Chromium `History` SQLite with `urls(id,url,title,last_visit_time,...)` and unrelated entries.
- [ ] Require newest matching `https://mp.weixin.qq.com/mp/profile_ext?...` selection by `last_visit_time`.
- [ ] Require `safe_summary()` to expose only host/path, presence booleans for `__biz`, `pass_ticket`, `appmsg_token`, `key`, `uin`, and a stable hash; never values or raw query.
- [ ] Implement SQLite URI `mode=ro` access; query only URL/title/timestamp columns needed for selection.
- [ ] Verify the adapter never mutates the database and all tests are GREEN.

### Task 2: Private Pagination Request Builder and Response Parser

**Files:**
- Create: `app/history_pager.py`
- Create: `tests/fixtures/profile_ext/page0.json`
- Create: `tests/fixtures/profile_ext/page10.json`
- Create: `tests/test_history_pager.py`

**Interfaces:**
- `build_page_url(seed: HistorySeed, offset: int, count: int = 10) -> str` is internal-only.
- `parse_profile_ext_page(payload: bytes, account_name: str) -> tuple[list[ArticleRecord], bool]`.

- [ ] RED tests require the builder to preserve the seed's private auth context while changing only `action=getmsg`, `offset`, `count`, and JSON response flags.
- [ ] RED tests require no helper representation/repr/error string to reveal auth-bearing parameters.
- [ ] Create synthetic WeChat `general_msg_list` payload fixtures with main articles plus multi-article items and timestamps.
- [ ] Parse canonical article URLs/titles/timestamps through existing `normalize_article` logic.
- [ ] Return a page continuation boolean from `can_msg_continue` / response metadata without exposing raw payload fields.

### Task 3: Authenticated History Provider with Injected Transport

**Files:**
- Modify: `app/providers.py`
- Create: `tests/test_authenticated_history_provider.py`

**Interfaces:**
- `AuthenticatedHistoryProvider(history_db: Path, transport: HistoryTransport)` implements `PublicAccountProvider`.
- `HistoryTransport.get(url: str) -> bytes` receives the private page URL only inside the provider.

- [ ] RED tests create a synthetic History DB containing a private `profile_ext` seed and an in-memory transport keyed by offset.
- [ ] Request `limit=20`; assert 20 unique newest-first normalized articles, complete timestamps and no auth value in `DiscoveryResult.to_dict()`.
- [ ] Require explicit `HISTORY_SURFACE_UNAVAILABLE` when no seed exists and `PAGINATION_INCOMPLETE` when continuation ends before requested count.
- [ ] Implement provider loop with deterministic dedupe and offset progression.
- [ ] Verify provider exceptions pass through existing API redaction.

### Task 4: Safe Seed Capability API and Real-Gate Handoff

**Files:**
- Modify: `app/main.py`
- Create: `tests/test_history_seed_api.py`
- Create: `scripts/probe-history-seed.sh`
- Modify: `DEVELOPMENT.md`

**Interfaces:**
- `GET /v1/wechat/history-seed-status` returns only `HistorySeed.safe_summary()` and candidate profile metadata.
- Command `bash scripts/probe-history-seed.sh` forces control API reload and prints sanitized status only.

- [ ] RED API tests require bearer authentication and prove raw query/auth values never appear.
- [ ] Implement deterministic active History candidate selection, preferring the Phase B `multitab_*` profile over `web_shell` when both exist and only one has recent `profile_ext` activity.
- [ ] Add one-command handoff script using local control token internally without printing it.
- [ ] Run full CI on final head.
- [ ] Physical gate: after GUI adapter opens a public-account all-messages surface, seed status must switch from absent to present without exposing auth values. Only then enable the real pager against the live runtime.

## Plan Self-Review

- No CDP dependency remains.
- No cookie decryption is required for the first implementation; the private profile-ext URL is the primary session bootstrap.
- History access is read-only and narrowly filtered to the public-account history endpoint.
- Raw authentication context has no external serialization path.
- GUI automation is deliberately separate from seed capture/pagination so it can be replaced or tuned without changing the provider.
