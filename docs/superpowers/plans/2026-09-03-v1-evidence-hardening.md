# V1 Evidence Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use test-driven development and execute this plan task-by-task. Do not start the physical Codespace acceptance until Task 9 is complete and the final review has no Critical or Important findings.

**Goal:** Make the newest-20 acceptance verdict depend on independently established public-account identity and a successful live offset-zero history observation, while removing unsafe persistence, diagnostics, redirect and CI behaviors.

**Architecture:** A public seed article is the only origin of `VerifiedAccountIdentity`. That evidence is threaded explicitly through the live discovery service into the authenticated provider; caller strings and UI deltas remain unverified. A successful `UrllibHistoryTransport` response carries live-observation evidence, and only a successful offset-zero response in the current provider call establishes freshness. The public-account index stores only version-2 verified seed identities. Pending acceptance calls the seed endpoint and keys cached PASS results by target, code and a safe session generation.

**Tech Stack:** Python 3.12, FastAPI/Pydantic, Python standard library (`dataclasses`, `urllib`, `sqlite3`, `hashlib`, `pathlib`), Bash, GitHub Actions, pytest.

**Spec:** `docs/superpowers/specs/2026-09-03-v1-evidence-hardening-design.md`

## Global Constraints

- Keep WeChat session values in process memory and `state/`; never serialize credential values, cookies, request URLs containing auth data, chats or contacts.
- A caller-provided account name, caller-provided `biz`, credential candidate or UI delta is not identity evidence.
- `freshness_verified` defaults to false. Only a successful live response for `action=getmsg&offset=0` during the current call may set it true.
- All articles in a verified result must contain the exact evidence `biz`; missing or mismatched values fail with `ACCOUNT_NOT_FOUND`.
- Only a seed-verified identity may be persisted. Version-1 index entries are legacy-unverified and cannot be upgraded implicitly.
- Keep public API response fields backward compatible; verification flags become more conservative.
- Each task follows RED -> GREEN -> REFACTOR -> focused tests -> local commit. Do not combine task commits.

## Interface Contract

Implement these interfaces exactly unless a focused RED test proves a small typing adjustment is required:

```text
app.public_accounts.VerifiedAccountIdentity
  fields: account_name: str, biz: str, provenance: str, canonical_seed_url: str
  method: safe_summary() -> dict[str, str]

app.seed_article.SeedIdentity
  method: to_verified_identity() -> VerifiedAccountIdentity

app.providers.HistoryPageResponse
  fields: payload: bytes, live_observation: bool = False

app.providers.HistoryTransport
  method: get(url: str) -> bytes | HistoryPageResponse

app.providers.AuthenticatedHistoryProvider
  method: recent_articles(account: str, limit: int, since: datetime | None = None,
                          *, verified_identity: VerifiedAccountIdentity | None = None)
          -> DiscoveryResult

app.account_index.PublicAccountIndex
  method: resolve_verified(account_name: str) -> VerifiedAccountIdentity | None
  method: remember_verified(identity: VerifiedAccountIdentity) -> None

app.live_discovery.LiveDiscoveryService
  method: recent_articles(account_name: str, biz: str | None, limit: int,
                          *, verified_identity: VerifiedAccountIdentity | None = None)
          -> DiscoveryResult
```

`VerifiedAccountIdentity.provenance` must equal `public_seed_article`, and `canonical_seed_url` must have canonical host `mp.weixin.qq.com` and an `/s` article path. The index preserves this original provenance; it does not invent a new `verified_index` provenance.

### Task 1: Establish the identity evidence type and safe parser defaults

**Files:** modify `app/public_accounts.py`, `app/seed_article.py`, `app/history_pager.py`; modify `tests/test_public_accounts.py`, `tests/test_seed_article_resolver.py`, `tests/test_history_pager.py`, `tests/test_profile_ext_compatibility.py`.

**Step 1 — RED: add evidence construction and parser-default tests**

Add tests that prove:

- `SeedIdentity.to_verified_identity()` normalizes surrounding/repeated display-name whitespace, preserves `biz`, sets provenance to `public_seed_article`, and canonicalizes the seed URL;
- invalid provenance, blank name/biz and non-WeChat seed URLs are rejected without including the bad value in the exception;
- `parse_profile_ext_page(payload, caller_name)` keeps every returned `ArticleRecord.verified_account` false;
- a caller name is never sufficient to mark a parsed article verified.

Run:

```powershell
python -m pytest -q tests/test_public_accounts.py tests/test_seed_article_resolver.py tests/test_history_pager.py tests/test_profile_ext_compatibility.py
```

Expected: failures for the missing evidence object/conversion and the current parser’s `verified_account=True`.

**Step 2 — GREEN: implement the minimum evidence object**

In `app/public_accounts.py`, add `normalize_account_display_name()` using NFKC normalization plus collapsed whitespace while preserving display case. Add `VerifiedAccountIdentity` with a secret-safe `repr`, strict provenance validation, canonical seed URL validation through `canonicalize_mp_url()`, and `safe_summary()`.

In `app/seed_article.py`, add:

```python
def to_verified_identity(self) -> VerifiedAccountIdentity:
    return VerifiedAccountIdentity(
        account_name=self.account_name,
        biz=self.biz,
        provenance="public_seed_article",
        canonical_seed_url=self.canonical_url,
    )
```

In `app/history_pager.py`, change `_article_raw()` to emit `"verified_account": False`. Do not give the parser an evidence parameter; evidence is applied centrally by the provider after all article `biz` values have been checked.

**Step 3 — REFACTOR and verify**

Keep URL/name validation in public helpers so the index and provider reuse the same rules. Confirm error strings contain stable codes only.

Run the focused command again; expect all selected tests to pass.

**Step 4 — Commit**

```powershell
git add app/public_accounts.py app/seed_article.py app/history_pager.py tests/test_public_accounts.py tests/test_seed_article_resolver.py tests/test_history_pager.py tests/test_profile_ext_compatibility.py
git commit -m "fix: model verified public account identity"
```

### Task 2: Make provider identity and freshness evidence explicit

**Files:** modify `app/providers.py`, `app/live_transport.py`; modify `tests/test_authenticated_history_provider.py`, `tests/test_live_history_transport.py`, `tests/test_providers.py`, `tests/test_profile_ext_response_semantics.py`.

**Step 1 — RED: cover false-positive cases**

Add tests for these exact outcomes:

- a byte-returning memory transport can return 20 articles but `freshness_verified` stays false;
- no verified identity means `account_verified` and every article’s `verified_account` stay false;
- a matching seed identity marks all records and the result verified;
- a wrong requested display name plus an unrelated valid `biz` cannot become verified;
- missing or mismatched article `biz` with identity evidence raises `ProviderError("ACCOUNT_NOT_FOUND")`;
- a successful live offset-zero response sets freshness true for later pages in that same invocation;
- a live response first observed at a nonzero offset cannot establish freshness;
- `SyntheticHistoryProvider` never grants live freshness or verified identity from fixture booleans.

Use `HistoryPageResponse(payload=page_bytes, live_observation=True)` only in tests that deliberately simulate a live response.

Run:

```powershell
python -m pytest -q tests/test_authenticated_history_provider.py tests/test_live_history_transport.py tests/test_providers.py tests/test_profile_ext_response_semantics.py
```

Expected: current unconditional verification assertions fail.

**Step 2 — GREEN: unwrap transport evidence and apply identity once**

In `app/providers.py`:

- add `HistoryPageResponse`;
- accept either legacy bytes or the response object from `HistoryTransport.get()`;
- track `live_offset_zero_observed` locally, setting it only after the current call successfully receives and parses a live response whose URL offset is zero;
- validate `verified_identity.account_name` against normalized `account` before transport use;
- validate every accumulated article has `biz == verified_identity.biz`; otherwise raise sanitized `ACCOUNT_NOT_FOUND`;
- only after validation, use `dataclasses.replace()` to set the evidence display name and `verified_account=True` on records;
- pass the two evidence-derived booleans into `build_discovery_result()`;
- set verification text to `public_seed_article+live_offset_zero`, `public_seed_article`, `live_offset_zero`, or `unverified`, matching the actual dimensions.

In `app/live_transport.py`, return:

```python
return HistoryPageResponse(payload=body, live_observation=True)
```

only after endpoint/context/status/size/challenge/final-URL checks have succeeded.

**Step 3 — REFACTOR and verify**

Extract one private response-unwrapping helper and one private verified-record helper. Do not infer live evidence from class name or `isinstance(UrllibHistoryTransport)`.

Run focused tests again; expect all selected tests to pass.

**Step 4 — Commit**

```powershell
git add app/providers.py app/live_transport.py tests/test_authenticated_history_provider.py tests/test_live_history_transport.py tests/test_providers.py tests/test_profile_ext_response_semantics.py
git commit -m "fix: require explicit identity and freshness evidence"
```

### Task 3: Replace the public-account index with verified version-2 entries

**Files:** modify `app/account_index.py`, `app/runtime.py`; modify `tests/test_account_index.py`, `tests/test_account_index_runtime_metadata.py`.

**Step 1 — RED: specify the migration boundary**

Add tests that prove:

- `remember_verified()` writes version 2 with `account_name`, `biz`, `provenance` and `canonical_seed_url` and never writes private session fields;
- `resolve_verified()` reconstructs the same evidence for normalized name variants;
- a handcrafted version-1 `{name: biz}` entry resolves to `None` and is not rewritten merely by reading;
- malformed provenance, URLs or entry shapes are ignored;
- unverified `remember(name, biz)` is no longer available;
- the index and temporary index files remain excluded from `summarize_state_dir()`;
- the POSIX `0600` assertion executes only when `os.name != "nt"`; Windows still verifies existence, JSON content and atomic replacement behavior.

Run:

```powershell
python -m pytest -q tests/test_account_index.py tests/test_account_index_runtime_metadata.py
```

Expected: version/schema/API tests fail before implementation.

**Step 2 — GREEN: implement strict version-2 loading and writing**

Use this on-disk shape:

```json
{
  "version": 2,
  "accounts": {
    "normalized name": {
      "account_name": "Display Name",
      "biz": "PUBLIC_BIZ",
      "provenance": "public_seed_article",
      "canonical_seed_url": "https://mp.weixin.qq.com/s/example"
    }
  }
}
```

Make `_load()` return `dict[str, VerifiedAccountIdentity]`. Keep the 500-entry bound, atomic replace, corrupt-file tolerance and Linux file mode. Remove or make private any API that accepts only name plus biz.

**Step 3 — REFACTOR and verify**

Reuse the public-account name normalization and evidence validation from Task 1. Never “upgrade” version 1 based on caller data.

Run focused tests again; expect pass.

**Step 4 — Commit**

```powershell
git add app/account_index.py app/runtime.py tests/test_account_index.py tests/test_account_index_runtime_metadata.py
git commit -m "fix: persist only seed-verified account identities"
```

### Task 4: Thread evidence through live discovery and both acceptance endpoints

**Files:** modify `app/live_discovery.py`, `app/main.py`; modify `tests/test_live_discovery.py`, `tests/test_live_candidate_rotation.py`, `tests/test_account_index_live_discovery.py`, `tests/test_name_only_discovery.py`, `tests/test_name_only_delta_safety.py`, `tests/test_live_discovery_api.py`, `tests/test_name_only_discovery_api.py`, `tests/test_seed_acceptance_api.py`, `tests/test_v1_newest20_acceptance_api.py`.

**Step 1 — RED: add adversarial service/API tests**

Add tests that prove:

- generic explicit-biz discovery can return articles and live freshness but remains account-unverified and does not write the index;
- `POST /v1/public-accounts/acceptance` with a wrong display name plus a valid unrelated biz returns `AUTOMATED_GATE_FAIL` with `account_verified=false`;
- `acceptance-from-url` converts the resolved seed to verified evidence and passes it to `LiveDiscoveryService.recent_articles(account_name, biz, 20, verified_identity=evidence)`;
- seed evidence whose biz differs from any returned article fails with `ACCOUNT_NOT_FOUND` and cannot be persisted;
- successful seed-verified discovery persists the identity and later name-only discovery can reuse it without UI search;
- a unique UI delta may guide one unverified discovery, but does not write the index and cannot pass newest-20 acceptance;
- a truncated baseline scan fails immediately with `HISTORY_SURFACE_UNAVAILABLE` before dispatching the UI search;
- a truncated post-search scan fails with the same code and no mapping is stored.

Run:

```powershell
python -m pytest -q tests/test_live_discovery.py tests/test_live_candidate_rotation.py tests/test_account_index_live_discovery.py tests/test_name_only_discovery.py tests/test_name_only_delta_safety.py tests/test_live_discovery_api.py tests/test_name_only_discovery_api.py tests/test_seed_acceptance_api.py tests/test_v1_newest20_acceptance_api.py
```

Expected: current persistence, truncation and API evidence tests fail.

**Step 2 — GREEN: pass evidence without synthesizing it**

Update private service helpers `_attempt_candidates()` and `_recent_known_biz()` to accept `VerifiedAccountIdentity | None` and pass it into the provider. At the public service boundary:

```python
if verified_identity is not None:
    # normalized name and optional biz must match evidence or ACCOUNT_NOT_FOUND
    target_biz = verified_identity.biz
elif biz is not None:
    target_biz = validated_caller_biz
else:
    verified_identity = self._account_index.resolve_verified(normalized_account)
```

Only call `remember_verified()` after a result is identity-verified and all returned article biz values match. Do not persist generic explicit-biz or UI-delta results.

In `_resolve_biz_by_ui_delta()`, reject `baseline.truncated` before UI dispatch and reject every truncated post-search report. Use `HISTORY_SURFACE_UNAVAILABLE` with stable messages `ui_baseline_scan_truncated` and `ui_post_scan_truncated`.

In `app/main.py`, keep `/acceptance` evidence-free. For `/acceptance-from-url`, call `identity.to_verified_identity()` and pass it with the new keyword argument. Keep the public seed summary and sanitized provider error mapping.

**Step 3 — REFACTOR and verify**

Centralize the name/biz/evidence consistency check in one private service method. Update fake service signatures in API tests; do not weaken production typing to accommodate a fake.

Run the focused suite again; expect pass.

**Step 4 — Commit**

```powershell
git add app/live_discovery.py app/main.py tests/test_live_discovery.py tests/test_live_candidate_rotation.py tests/test_account_index_live_discovery.py tests/test_name_only_discovery.py tests/test_name_only_delta_safety.py tests/test_live_discovery_api.py tests/test_name_only_discovery_api.py tests/test_seed_acceptance_api.py tests/test_v1_newest20_acceptance_api.py
git commit -m "fix: enforce evidence across discovery and acceptance"
```

### Task 5: Make pending physical acceptance seed-based and cache-safe

**Files:** create `app/pending_acceptance.py`; modify `scripts/run-pending-acceptance.sh`, `app/runtime.py`, `app/wechat_probe.py`; modify `tests/test_pending_physical_acceptance.py`, `tests/test_runtime.py`, `tests/test_wechat_probe.py`; create `tests/test_pending_acceptance_cache.py`.

**Step 1 — RED: specify endpoint, cache identity and runtime metadata**

Add behavior tests for:

- the script requests `/v1/public-accounts/acceptance-from-url` and sends only `{"article_url": target["article_url"]}`;
- target fingerprint changes when any target field changes;
- code identity is the exact `git rev-parse HEAD` value, with stable `unknown` fallback outside Git;
- safe session generation changes when sanitized artifact-class metadata changes and is stable when only `.control-token`, `.public-account-index.json` or the acceptance result changes;
- `can_reuse_pass(previous, cache_identity)` requires exact target fingerprint, Git head, session generation and `AUTOMATED_GATE_PASS_UI_PENDING`;
- changed Git head or session generation invalidates PASS;
- `.v1-newest20-acceptance-latest.json` does not set `summarize_state_dir()["initialized"]` or `probe_state()["state_initialized"]`.

Run:

```powershell
python -m pytest -q tests/test_pending_physical_acceptance.py tests/test_pending_acceptance_cache.py tests/test_runtime.py tests/test_wechat_probe.py
```

Expected: missing module and current target-only cache behavior fail.

**Step 2 — GREEN: implement safe cache helpers**

In `app/pending_acceptance.py`, implement pure helpers:

```text
AcceptanceCacheIdentity
  fields: target_fingerprint: str, git_head: str, session_generation: str

build_target_fingerprint(target: Mapping[str, object]) -> str
read_git_head(repo_root: Path) -> str
build_safe_session_generation(state_dir: Path) -> str
can_reuse_pass(previous: Mapping[str, object], identity: AcceptanceCacheIdentity) -> bool
```

Build the session digest only from structural artifact class, already-sanitized relative root, file size and nanosecond mtime. Explicitly skip `RUNTIME_METADATA_FILES` and index/result temporary files. Never hash file contents, raw relative paths, account IDs, credentials or token files. Store only the resulting digest.

Update the script so it waits for runtime readiness, builds the current cache identity, reuses only an exact PASS, posts the seed URL to `acceptance-from-url`, recomputes the safe session generation after the attempt, and atomically writes the final JSON with the three cache fields. Use a sibling temp file plus `os.replace()`; apply `0600` on POSIX.

Add `.v1-newest20-acceptance-latest.json` and its temp prefix to runtime metadata exclusions shared by `summarize_state_dir()` and `probe_state()`.

**Step 3 — REFACTOR and verify**

Keep network/retry orchestration in the script and cache decisions in importable Python helpers. Ensure the persisted result has no control token or request headers.

Run focused tests again; expect pass.

**Step 4 — Commit**

```powershell
git add app/pending_acceptance.py scripts/run-pending-acceptance.sh app/runtime.py app/wechat_probe.py tests/test_pending_physical_acceptance.py tests/test_pending_acceptance_cache.py tests/test_runtime.py tests/test_wechat_probe.py
git commit -m "fix: bind pending acceptance to seed code and session"
```

### Task 6: Bound and redact all diagnostic scans

**Files:** modify `app/webview_probe.py`, `app/wechat_probe.py`; modify `tests/test_webview_probe.py`, `tests/test_webview_probe_api.py`, `tests/test_wechat_probe.py`.

**Step 1 — RED: add adversarial names and global-budget tests**

Create path segments, SQLite tables and columns containing sentinel strings such as `PRIVATE_ACCOUNT_123`, `SECRET_TABLE_456` and `TOKEN_COLUMN_789`. Assert none appears in `repr(result)`.

Add tests for `probe_webview_state()` with deliberately tiny file, byte, directory and elapsed-time budgets. Each must return:

```python
{
    "truncated": True,
    "truncation_reasons": ["file_count_budget"],
    "sensitive_values_returned": False,
    # existing public structural fields remain present
}
```

Use the corresponding reason for each budget and assert no truncated result claims a complete/successful scan. Add equivalent unknown-path redaction coverage for `probe_state()`.

Run:

```powershell
python -m pytest -q tests/test_webview_probe.py tests/test_webview_probe_api.py tests/test_wechat_probe.py
```

Expected: raw identifiers and unbounded traversal make tests fail.

**Step 2 — GREEN: use allowlists and one shared scan budget**

Allow only known structural path segments (`.xwechat`, `radium`, `web`, `profiles`, `web_shell`, `Network`, `Local Storage`, `leveldb`, `Cache`, `Code Cache`, `GPUCache`, `History`, `Cookies`, `xwechat_files`, `Msg`, `User Data`, `Default`). Preserve the existing `multitab_<redacted>` rule. Render every other segment as `<redacted>`.

Allow only expected Chromium table/column identifiers needed by diagnostics (`cookies`, `urls`, `visits`, `meta`, `host_key`, `name`, `encrypted_value`, `expires_utc`, `url`, `title`, `last_visit_time`). Render any other identifier as stable positional labels such as `<redacted-table-1>` and `<redacted-column-1>`.

Make `probe_webview_state()` accept keyword-only defaults for `max_files`, `max_total_bytes`, `max_directories` and `max_scan_seconds`. Thread one mutable budget across profile discovery, container counting, marker counting and schema inspection. Stop traversal promptly, return sorted unique reasons, and include explicit `truncated` fields even when the WebView root is missing.

**Step 3 — REFACTOR and verify**

Avoid `list(path.rglob("*"))` and generator-wide `sum()` calls; both defeat the budget. Keep deterministic ordering within the visited subset.

Run focused tests again; expect pass.

**Step 4 — Commit**

```powershell
git add app/webview_probe.py app/wechat_probe.py tests/test_webview_probe.py tests/test_webview_probe_api.py tests/test_wechat_probe.py
git commit -m "fix: bound and redact runtime diagnostics"
```

### Task 7: Disable authenticated history redirects completely

**Files:** modify `app/live_transport.py`; modify `tests/test_live_history_transport.py`.

**Step 1 — RED: exercise same-origin redirect rejection**

Add tests that call the redirect handler with a same-host `/mp/profile_ext` target and assert it returns `None`. Add an injected-response test whose `geturl()` differs from the requested URL only by query/offset and assert sanitized `HISTORY_SURFACE_UNAVAILABLE` with `history_redirect_not_allowed`. Confirm the redirected URL is absent from the exception text.

Run:

```powershell
python -m pytest -q tests/test_live_history_transport.py
```

Expected: the current handler follows same-origin redirects.

**Step 2 — GREEN: install a no-redirect handler and require exact final URL**

Replace `_RestrictedRedirectHandler` with a handler whose `redirect_request()` always returns `None`. After open succeeds, require `response.geturl() == request.full_url`; any difference raises the stable redirect error before body processing.

Do not change the public seed resolver redirect behavior in `app/seed_article.py`; this task applies only to authenticated history requests.

**Step 3 — Verify and commit**

```powershell
python -m pytest -q tests/test_live_history_transport.py
git add app/live_transport.py tests/test_live_history_transport.py
git commit -m "fix: reject authenticated history redirects"
```

### Task 8: Stop CI self-commits and correct evidence claims/portable mode tests

**Files:** modify `.github/workflows/runtime-cli-probe.yml`, `.github/workflows/runtime-launcher-probe.yml`, `.github/workflows/runtime-smoke.yml`, `DEVELOPMENT.md`, `tests/test_runtime_cli_probe_workflow.py`, `tests/test_account_index.py`, `tests/test_runtime.py`; create `tests/test_workflow_diagnostics.py`.

**Step 1 — RED: make branch-head integrity executable**

Add workflow text tests that assert for all three diagnostic workflows:

- `git push` and `git commit` are absent;
- permissions are `contents: read`;
- sanitized output is written below `/tmp/` and uploaded with `actions/upload-artifact@v4`;
- a bounded sanitized summary is appended to `$GITHUB_STEP_SUMMARY`;
- no workflow writes a tracked `docs/*-latest.md` file.

Update Windows-host tests so POSIX mode equality is asserted only when `os.name != "nt"`; do not skip the rest of either test.

Add a documentation assertion that the current live runtime smoke is named/described as an unauthenticated failure-path integration smoke and does not claim a successful credential-to-pagination flow.

Run:

```powershell
python -m pytest -q tests/test_runtime_cli_probe_workflow.py tests/test_workflow_diagnostics.py tests/test_account_index.py tests/test_runtime.py
```

Expected: workflow self-commit and old documentation assertions fail.

**Step 2 — GREEN: convert tracked diagnostics to artifacts and summaries**

Set read-only contents permissions. Generate the sanitized Markdown in `/tmp/<probe>/summary.md`, append it to `$GITHUB_STEP_SUMMARY`, and include it in the existing one-day artifact. Delete bot Git configuration/commit/push steps.

In `DEVELOPMENT.md`, replace `V1_LIVE_RUNTIME_SMOKE = PASS` with `V1_LIVE_RUNTIME_FAILURE_PATH_SMOKE = PASS` and state precisely that the current hosted smoke validates the unauthenticated FastAPI/bridge/scanner/error path; it does not prove logged-in newest-20 pagination.

Retain historical tracked diagnostics as historical files; do not update them from Actions.

**Step 3 — REFACTOR and verify**

Run the focused command again. Then search for remaining self-push behavior:

```powershell
rg -n "git push|contents: write" .github/workflows
```

Expected: no match in diagnostic workflows.

**Step 4 — Commit**

```powershell
git add .github/workflows/runtime-cli-probe.yml .github/workflows/runtime-launcher-probe.yml .github/workflows/runtime-smoke.yml DEVELOPMENT.md tests/test_runtime_cli_probe_workflow.py tests/test_workflow_diagnostics.py tests/test_account_index.py tests/test_runtime.py
git commit -m "ci: preserve exact tested branch heads"
```

### Task 9: Full regression, security review and exact-head handoff

**Files:** all files changed in Tasks 1–8; no production changes until failures are understood.

**Step 1 — Run the complete local suite**

```powershell
python -m pytest -q
```

Expected on Windows: all tests pass; POSIX-only mode equality is conditionally omitted while the rest of each test runs.

If anything fails, use systematic debugging: reproduce the first failure alone, identify its cause, add/adjust a behavioral test, implement the smallest fix, rerun focused then full suites. Do not weaken identity or freshness assertions.

**Step 2 — Run static repository checks**

```powershell
rg -n "verified_account.?[:=].?True|account_verified=True|freshness_verified=True" app
rg -n "git push|contents: write" .github/workflows
rg -n "pass_ticket|appmsg_token|poc_token|authorization|cookie" config tests --glob "!tests/fixtures/**"
git status --short
git log --oneline --decorate -12
```

Manually classify every first-search match. Allowed cases are evidence application after checks, explicit test fixtures/fakes, and public-key names without values. There must be no unconditional production verification or committed secret value.

**Step 3 — Fresh final review**

Request an independent code review against:

- base `f5158b37d5bf0b5059c51f7911c1ec970b1c1935`;
- design `docs/superpowers/specs/2026-09-03-v1-evidence-hardening-design.md`;
- this plan;
- all Task 1–8 commits.

The review must explicitly try these attacks:

1. wrong display name + unrelated valid `biz`;
2. UI delta created by unrelated concurrent WebView activity;
3. legacy index entry granting identity;
4. byte-only/synthetic transport granting freshness;
5. stale PASS reused after code or session changes;
6. adversarial path/schema names leaking through probes;
7. same-origin authenticated redirect;
8. Actions creating an untested bot head.

Any Critical or Important finding returns to the owning task with RED/GREEN tests and a separate fix commit. Repeat full regression and fresh review until none remain.

**Step 4 — Prepare exact-head remote verification**

Before pushing, record:

```powershell
git rev-parse HEAD
git status --short --branch
```

Push only after user authorization for the shared remote action. Verify Push + PR Test jobs run on that exact SHA and succeed. Do not merge PR #2 or mark V1 complete yet.

**Step 5 — Physical gate remains separate**

After exact-head CI is green, obtain the one required GitHub Codespaces authorization with `codespace` scope, start/reconnect to `musical-guide-vxp45jxgj442wg75`, and run the existing seed-based pending acceptance. Physical success requires:

- automated seed identity -> real live newest 20 -> all six checks true;
- first and twentieth public metadata match the logged-in WeChat UI;
- no session secret in API output, logs or artifacts.

Only then may `V1_REAL_NEWEST20` change from `PENDING_PHYSICAL` to `PASS`.

## Completion Definition

This implementation plan is complete when Tasks 1–8 are committed locally, Task 9 full regression and independent review are clean, exact-head CI passes, and the physical gate is either completed or clearly reported as the sole remaining external gate. Software completion alone does not authorize merging the draft PR.
