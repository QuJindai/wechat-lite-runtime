# Development Status

## V0 final status

**V0 = PASS**

Verified on the real GitHub Codespace `musical-guide-vxp45jxgj442wg75` on 2026-09-02:

- repository is public
- official Linux WeChat runtime starts through `ghcr.io/nickrunning/wechat-selkies:0.0.16`
- port `3001` is reachable
- control API `8787` self-heals during acceptance
- `python -m app.acceptance before` -> `BASELINE_RECORDED`
- stop/start of the same Codespace preserved the state marker and profile
- `python -m app.acceptance after` -> `STORAGE_PASS_AUTH_PENDING`
- user visually confirmed WeChat remained logged in without rescanning a QR code

Therefore:

- `CODESPACE_STATE_PERSISTENCE = PASS`
- `PHYSICAL_LOGIN_PERSISTENCE = PASS`

## V1 Phase A-B: safe runtime and WebView evidence

Status:

- `V1_PHASE_A_SOFTWARE = PASS`
- `V1_SAFE_RUNTIME_PROBE = PASS`
- `V1_PHASE_B_SOFTWARE = PASS`
- `V1_WEBVIEW_CONTAINER_PROBE = PASS`

Real logged-in Codespace evidence:

- `cookie_store`: candidates present
- `mp_weixin_trace`: candidates present under `.xwechat/radium/web`
- `webview_cache`: candidates present including `.xwechat/radium/web`
- Chromium `Cookies` and `History` SQLite stores exist
- `Local Storage/leveldb` exists
- `multitab_<redacted>` is the high-value profile
- no cookie/token value was returned

This selected the authenticated WebView/History route and avoided unrelated chat databases.

The end-to-end target remains the newest 20 public-account articles with verified timestamps, unique canonical URLs, account identity and freshness.

## V1 Phase C: authenticated History pagination

Status:

- `V1_PHASE_C_HISTORY_SEED_SOFTWARE = PASS`
- `V1_AUTHENTICATED_HISTORY_PROVIDER_SOFTWARE = PASS`
- `V1_PROFILE_EXT_COMPATIBILITY = PASS`

Implemented and CI-verified:

- read-only Chromium History seed locator restricted to `https://mp.weixin.qq.com/mp/profile_ext`
- target-biz History seed lookup and newest-first ordering
- private `profile_ext?action=getmsg` pagination
- compatibility flags `scene=124`, `x5=1`, `wxtoken=`, `count<=10`
- main and multi-article parsing with timestamp normalization
- `ret=-3` / session/login/auth failure classification as `LOGIN_REQUIRED`
- other rejected responses remain explicit history-surface errors
- deterministic URL canonicalization removes auth-bearing query values

## V1 Phase D-E: bootstrap, transport and container bridge

Status:

- `V1_ACCOUNT_BOOTSTRAP_SOFTWARE = PASS`
- `V1_LIVE_HTTP_TRANSPORT_SOFTWARE = PASS`
- `V1_LAUNCHER_BRIDGE = PASS`
- `V1_LIVE_RUNTIME_FAILURE_PATH_SMOKE = PASS`

Implemented:

- bounded credential scanner over `.xwechat/radium/web`
- legacy `uin + key + pass_ticket` candidates
- token-style `appmsg_token + pass_ticket` candidates
- modern `/mp/relatedsearchword` session context support
- candidate rotation: stale newest credential automatically falls back to older valid candidates
- private History seed reuse before re-opening WeChat
- restricted `urllib` transport: same-host/path validation, redirect guard, timeout and response-size limits
- internal workspace -> WeChat-container bridge on `127.0.0.1:8790`
- bridge is not forwarded through Codespaces and does not require Docker socket access
- real GitHub-hosted Compose smoke is an unauthenticated failure-path integration smoke across FastAPI -> bridge -> WeChat container -> scanner/discover
- it does not prove logged-in newest-20 pagination; that remains part of the physical gate

## V1 UI fallback and name-only discovery

Status:

- `V1_UI_SEARCH_FALLBACK_SOFTWARE = PASS`
- `V1_NAME_ONLY_DISCOVERY_SOFTWARE = PASS`

Implemented:

- evidence-gated X11 fallback using the existing WeChat window
- keyboard-only sequence: activate window -> Ctrl+F -> write account name to clipboard -> Ctrl+V -> one Enter
- no clipboard read, mouse click, chat read or message send
- UI keystrokes are never considered success by themselves; target credential evidence remains mandatory
- `POST /v1/public-accounts/discover` accepts `account_name` with optional `biz`
- when `biz` is absent, before/after credential fingerprint delta resolves a unique new public-account identity
- baseline fingerprints are never treated as new merely because a cache file mtime changed
- multiple new identities return `ACCOUNT_IDENTITY_AMBIGUOUS` instead of guessing
- error output never returns candidate biz/token/session values

## V1 persistent public-account identity index

Status:

- `V1_PUBLIC_ACCOUNT_INDEX_SOFTWARE = PASS`
- `V1_PUBLIC_ACCOUNT_INDEX_RUNTIME = PASS`

Implemented:

- `state/.public-account-index.json`
- stores only normalized public-account display name -> public `biz`
- mode `0600`, atomic replace, corrupt-file tolerant
- no cookie, key, pass_ticket, appmsg_token, request URL or other session material is stored
- successful discovery records the mapping; failed discovery does not
- subsequent name-only requests try the saved `biz` before UI search
- the index is runtime metadata and does not by itself mark the WeChat profile as initialized
- real Compose smoke verifies the index survives workspace restart

## V1 newest-20 acceptance helper

Status:

- `V1_NEWEST20_ACCEPTANCE_SOFTWARE = PASS`
- `V1_REAL_NEWEST20 = PENDING_PHYSICAL`

Endpoint:

- `POST /v1/public-accounts/acceptance`
- request: `account_name`, optional `biz`
- always performs a 20-article discovery

Automated PASS requires all of:

- exactly 20 returned articles
- `count_satisfied = true`
- `timestamps_complete = true`
- `urls_unique = true`
- `account_verified = true`
- `freshness_verified = true`

On automated PASS it returns `AUTOMATED_GATE_PASS_UI_PENDING` plus only the first and twentieth article's public metadata for final UI cross-check. It never returns session credentials.

## Remaining V1 physical gate

Only one end-to-end gate remains unclosed:

**one real logged-in public account -> newest 20 articles -> all automated checks PASS -> first/20th match the WeChat history UI -> zero session secrets in output/logs**.

Until that real logged-in gate passes, V1 remains experimental and PR #2 should not be merged as a completed general-purpose WeChat discovery feature.

## Later

- bounded time-window / all-history pagination after newest-20 PASS
- automatic Codespaces Start/Stop wake gateway
- standalone `@微信` MCP packaging
- optional `深析` provider receiving only article metadata/URLs, never WeChat session material
