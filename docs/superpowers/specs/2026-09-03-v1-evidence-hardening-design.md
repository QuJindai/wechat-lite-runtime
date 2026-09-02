# V1 Evidence Hardening Design

Date: 2026-09-03

Base: `feat/v1-public-account-discovery` at `f5158b37d5bf0b5059c51f7911c1ec970b1c1935`

Target branch: `feat/v1-public-account-discovery`

## 1. Objective

Make the V1 newest-20 gate evidence-based before running the real logged-in Codespace acceptance. The gate must not report a verified account or verified freshness merely because the caller supplied a display name and a valid `biz`.

The existing V1 product boundary remains unchanged:

- the WeChat Runtime stays independent from `深析`;
- session material stays inside `state/` and process memory;
- V1 still ends at one-account newest-20 acceptance;
- time-window history, wake orchestration and MCP packaging remain later work.

## 2. Verified Review Findings

The current implementation has five trust gaps:

1. `parse_profile_ext_page()` copies the caller-provided account name into article records and marks them verified.
2. `AuthenticatedHistoryProvider` sets account and freshness verification to true without receiving evidence for either claim.
3. UI credential-delta resolution can associate unrelated concurrent WebView activity with the searched name and can operate on truncated scans.
4. the pending acceptance script calls the name/biz endpoint even though the physical target already contains a public seed article URL that can independently resolve name-to-biz identity;
5. a successful pending-acceptance result is cached only by target JSON, so it can survive code or runtime-session changes.

These gaps can create a false-positive `AUTOMATED_GATE_PASS_UI_PENDING`. They must be fixed before physical acceptance.

## 3. Considered Approaches

### A. Strict evidence chain — selected

Treat account identity and freshness as explicit evidence supplied to the provider. A public seed article independently proves display-name-to-biz identity. A successful live offset-zero `profile_ext` request proves freshness for that observation. Generic discovery remains usable but unverified until it has the same evidence.

This approach reduces name-only convenience for previously unseen accounts, but it preserves truthful gate semantics and reuses the already implemented seed resolver.

### B. Harden only the acceptance endpoint — rejected

The seed URL could be checked only at the final endpoint while leaving generic discovery and the persistent index unchanged. This would make the dSPACE gate safer but would preserve the ability to store an unrelated name-to-biz association and reuse it later.

### C. Rely on manual first/twentieth UI comparison — rejected

Manual comparison is still required, but it cannot repair a misleading automated verdict or prove that the requested display name belongs to the selected biz. Automation must remain conservative before asking for the manual cross-check.

## 4. Evidence Model

### 4.1 Account identity

`account_verified=true` requires an independent `VerifiedAccountIdentity` containing:

- normalized public-account display name;
- public `biz` identifier;
- provenance `public_seed_article`;
- canonical public seed article URL.

The identity is produced only by `SeedArticleResolver`. Caller-provided `account_name`, caller-provided `biz`, a credential candidate, or a UI search delta is not sufficient evidence by itself.

Every returned article must still contain the same public `biz` as the verified identity. A mismatch fails with `ACCOUNT_NOT_FOUND`; it is never downgraded to an unverified success.

Generic `/discover` requests may return normalized article metadata, but their records and result must keep `verified_account=false` and `account_verified=false` unless the service was explicitly given a verified identity.

### 4.2 Freshness

`freshness_verified=true` requires a successful live request for `profile_ext?action=getmsg&offset=0` during the current discovery call.

- locating a Chromium History seed is not freshness evidence;
- reading cached files is not freshness evidence;
- a synthetic or injected transport is not fresh unless the test explicitly supplies a transport capability representing a successful live offset-zero observation;
- subsequent pages inherit freshness only after the offset-zero page succeeded in the same provider invocation.

The provider must default both verification dimensions to false.

### 4.3 Persistent account index

The index remains public metadata only, but only verified identities may be written.

- UI delta resolution may guide a one-off unverified discovery;
- it must not persist the searched name-to-biz mapping;
- both baseline and post-search scans must be complete (`truncated=false`), otherwise resolution fails with `HISTORY_SURFACE_UNAVAILABLE`;
- a mapping created by verified seed acceptance may be reused by later name-only discovery as identity evidence.

The index format gains verification provenance. Legacy version-1 entries are read as unverified and must not grant `account_verified=true`.

## 5. API and Runtime Flow

### 5.1 Seed acceptance

`POST /v1/public-accounts/acceptance-from-url` remains the authoritative physical-gate endpoint:

1. resolve the article URL through `SeedArticleResolver`;
2. construct verified identity evidence;
3. run live newest-20 discovery with that evidence;
4. require all article biz values to match the evidence;
5. evaluate count, timestamps, URL uniqueness, identity and freshness independently;
6. persist the verified public identity only after successful evidence validation;
7. return the existing public seed summary plus the first/twentieth public metadata.

`POST /v1/public-accounts/acceptance` remains available for compatibility, but it cannot pass the account-verification check from caller-supplied name/biz alone.

### 5.2 Pending acceptance

`scripts/run-pending-acceptance.sh` must call `acceptance-from-url` with `article_url` from `config/v1-physical-acceptance-target.json`.

The cached result identity must include:

- target fingerprint;
- current Git HEAD;
- a non-secret runtime-session generation derived from safe state metadata.

A previous result is reusable only when all three match. Session credentials or their hashes must never enter the cache key or output.

The result file remains private runtime metadata and must be excluded from `session_storage.initialized` calculations.

## 6. Diagnostic Boundary

Safe probes must use allowlists for path and schema output:

- known Chromium/WeChat structural names may be returned;
- unknown profile/path components become `<redacted>`;
- unknown SQLite table or column identifiers become stable redacted placeholders rather than raw strings;
- global file, byte, directory and elapsed-time budgets apply to WebView scanning;
- truncation is explicit and never accompanied by a success claim.

No matched bytes, row values, filenames containing account identifiers, cookies, tokens, query values, chats or contacts may be returned.

## 7. Transport Boundary

Redirects are disabled for authenticated history requests. A redirect response is a stable `HISTORY_SURFACE_UNAVAILABLE` error. This avoids following a same-origin redirect that drops or replaces the candidate authentication context.

The existing HTTPS host/path, response-size and timeout restrictions remain in force.

## 8. CI and Evidence Claims

- generated runtime diagnostics are artifacts or job summaries, not bot commits to the feature branch;
- Push and PR tests must succeed on the exact final human-authored head;
- the current live runtime smoke is described as an unauthenticated failure-path integration smoke unless it executes a successful credential-to-pagination flow;
- POSIX `0600` assertions remain strict on Linux and are platform-aware on Windows/NTFS;
- no test may treat source-text presence as proof of runtime behavior when an executable behavior test is practical.

## 9. Test Strategy

### Identity and freshness

- wrong display name plus a valid unrelated biz cannot set `account_verified=true`;
- generic explicit-biz discovery returns articles but remains identity-unverified;
- seed-resolved name/biz evidence can set identity verification only when every article biz matches;
- missing or mismatched article biz fails safely;
- freshness defaults false and becomes true only after a live offset-zero observation;
- stale/history-only and synthetic paths cannot accidentally pass the physical gate.

### UI delta and index

- truncated baseline scan is rejected;
- truncated post-search scan is rejected;
- one unrelated credential delta is not persisted as the requested account;
- verified seed identity persists and can be reused;
- legacy unverified index entries never grant identity verification.

### Pending gate and diagnostics

- the script invokes `acceptance-from-url` with the configured article URL;
- changed Git head or session generation invalidates a cached PASS;
- the acceptance result file does not initialize an otherwise empty WeChat profile;
- adversarial path, table and column names are redacted;
- scan budgets report truncation;
- authenticated redirects are rejected without leaking their URL.

## 10. Acceptance Criteria

Software hardening is complete only when:

- all new adversarial tests pass;
- the full Linux CI suite passes on the exact final head;
- final code review has no Critical or Important findings;
- generic unverified discovery cannot produce an automated newest-20 PASS;
- the dSPACE seed acceptance can produce `account_verified=true` only through the public seed identity;
- no session secret or sensitive identifier appears in APIs, logs, artifacts or committed fixtures.

After software hardening, the remaining physical gate is unchanged:

> dSPACE seed identity -> real logged-in newest 20 -> all automated checks PASS -> first/twentieth match the WeChat UI -> zero session secrets in output/logs.
