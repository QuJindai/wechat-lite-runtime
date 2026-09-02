# V1 Phase E Live Authenticated Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use TDD and execute this plan task-by-task.

**Goal:** Connect a private WebView credential candidate to a real same-origin HTTP transport and the existing `AuthenticatedHistoryProvider`, then expose one bearer-protected API call that performs bootstrap plus recent-article discovery without terminal input.

**Architecture:** A credential candidate remains private in process memory and becomes the authoritative private history seed. `UrllibHistoryTransport` only sends HTTPS requests to `mp.weixin.qq.com/mp/profile_ext`, requires the target request to preserve the candidate's biz/auth context, blocks cross-origin redirects, bounds response size/time, and maps auth failures to `LOGIN_REQUIRED`. `LiveDiscoveryService` runs the existing account bootstrap, chooses the newest matching candidate, builds the private provider, and returns only normalized article metadata.

**Tech Stack:** Python 3.12 standard library (`urllib`, `dataclasses`, `pathlib`), existing FastAPI/provider/bootstrap/scanner modules, pytest.

**Spec:** `docs/superpowers/specs/2026-09-02-v1-public-account-discovery-design.md`

## Global Constraints

- Candidate URL, `uin`, `key`, `pass_ticket`, `appmsg_token`, `poc_sid`, `poc_token`, cookies and request headers never leave runtime process memory.
- Network destination is fixed to HTTPS `mp.weixin.qq.com/mp/profile_ext`; cross-origin redirect is rejected before following.
- Target request must preserve the candidate's private auth values and target biz.
- No cookie decryption or chat database access.
- Response size and timeout are bounded.
- Provider/API errors contain stable codes and sanitized messages only.
- CI uses synthetic candidates and synthetic HTTP responses only.

### Task 1: Candidate Seed + Real HTTP Transport

**Files:** create `app/live_transport.py`, create `tests/test_live_history_transport.py`.

- RED tests: candidate validation; private seed creation; same-origin request; auth-context preservation; redirect/host escape rejection; 401/403 -> `LOGIN_REQUIRED`; payload bound; secret-safe repr/errors.
- GREEN: implement `history_seed_from_candidate()` and `UrllibHistoryTransport` with a restricted redirect handler and injected opener for tests.

### Task 2: Live Discovery Service

**Files:** create `app/live_discovery.py`, modify `app/providers.py`, create `tests/test_live_discovery.py`.

- RED tests: bootstrap -> newest matching candidate -> transport -> 20 articles; credential-not-observed; mismatched biz response; no secret serialization.
- GREEN: allow `AuthenticatedHistoryProvider` a private seed override; implement `LiveDiscoveryService` with injectable bootstrap/transport factories.

### Task 3: One-Call Local API

**Files:** modify `app/main.py`, create `tests/test_live_discovery_api.py`, modify `DEVELOPMENT.md`.

- API: `POST /v1/public-accounts/discover` body `{account_name,biz,limit}`.
- Require bearer auth, 1..100 limit, existing ProviderError mapping, normalized sanitized response.
- Default app wiring uses the real `LiveDiscoveryService`; tests inject a fake service.
- Final gate: full Push + PR Test success on final head.
