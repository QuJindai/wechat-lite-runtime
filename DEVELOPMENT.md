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

## V1 Phase A: safe discovery foundation

Status:

- `V1_PHASE_A_SOFTWARE = PASS`
- `V1_SAFE_RUNTIME_PROBE = PASS`

Real logged-in Codespace evidence:

- `cookie_store`: 5 candidates
- `mp_weixin_trace`: 5 candidates under `.xwechat/radium/web`
- `webview_cache`: 30 candidates including `.xwechat/radium/web`
- `xwechat_db`: 16 candidates
- `sensitive_values_returned = false`

Implemented:

- sanitized artifact classifier and bearer-protected `GET /v1/wechat/probe`
- article URL canonicalization / auth-query redaction
- normalized article/discovery models with independent completeness flags
- provider abstraction + synthetic pagination
- bearer-protected recent-article API contract

## V1 Phase B: WebView container locator

Status:

- `V1_PHASE_B_SOFTWARE = PASS`
- `V1_WEBVIEW_CONTAINER_PROBE = PASS`

Real logged-in Codespace evidence selected `.xwechat/radium/web/profiles/multitab_<redacted>` as the high-value profile:

- standard Chromium `Cookies` SQLite exists
- standard Chromium `History` SQLite exists with `urls`, `visits`, and related tables
- `Local Storage/leveldb` exists
- active multitab profile contained `mp.weixin.qq.com` markers
- `web_shell` had materially fewer relevant markers
- no cookie/token value was returned

This selects the authenticated WebView/History route and avoids unrelated chat DBs.

## V1 Phase C: private History seed and pagination

Status:

- `V1_PHASE_C_HISTORY_SEED_SOFTWARE = PASS`
- `V1_AUTHENTICATED_HISTORY_PROVIDER_SOFTWARE = PASS`

Implemented and CI-verified:

- read-only Chromium History seed locator restricted to `https://mp.weixin.qq.com/mp/profile_ext`
- safe seed summary: host/path, auth-key presence booleans and fingerprint only
- private `profile_ext?action=getmsg` pagination URL builder
- `general_msg_list` parser for main and multi-article items
- authenticated History provider with injected transport
- 20-article / two-page synthetic pagination with deterministic dedupe
- bearer-protected `GET /v1/wechat/history-seed-status`
- zero raw seed URL / auth values in API output

## Autonomous runtime CLI evidence

All CLI evidence below was generated on fresh isolated GitHub-hosted runners; it did not use the user's real WeChat profile.

- `V1_RUNTIME_CLI_PROBE = PASS`
- `V1_X11_CAPABILITY = PASS`
- `V1_CDP_ROUTE = NOT_AVAILABLE`

Findings:

- `WeChatAppEx` has no `--remote-debugging-port`
- common CDP ports did not expose `/json/version` or `/json/list`
- port `8082` belongs to Selkies WebSocket transport, not WeChat DevTools
- `xdotool`, `xprop`, and `xclip` are present
- `DISPLAY=:1`
- one visible `WM_CLASS="wechat"` window is detectable and its geometry can be read
- `/usr/share/applications/wechat.desktop` contains `Exec=/usr/bin/wechat %U`
- `/usr/bin/wechat` is a symlink to `/opt/wechat/wechat`
- secondary invocation comparison produced the same exit code `255` for no arguments, a plain HTTPS URL, and a WeChat `profile_ext` URL, through both paths; therefore `255` is treated as generic secondary-instance dispatch evidence, not URL-navigation success
- empty-state runner URL invocation did not create the test marker in History/cache, so actual navigation success must be judged by observing runtime WebView state, not the launcher exit code

## Linux WebView credential scanner

Status:

- `V1_CREDENTIAL_SCANNER_SOFTWARE = PASS`

Implemented:

- bounded recent-file scan restricted to supplied WebView roots, intended `.xwechat/radium/web`
- direct and percent-encoded `mp.weixin.qq.com` URL detection
- target `__biz` matching
- legacy candidate fields: `uin + key + pass_ticket`
- token candidate fields: `appmsg_token + pass_ticket`
- optional `poc_sid / poc_token`
- file-count, directory-count, total-byte and wall-time budgets
- media/cache-directory exclusions
- safe summaries return only field names, safe root, timestamps and fingerprints; raw candidate URLs and credential values remain private

## V1 Phase D: automated public-account bootstrap

Status:

- `V1_ACCOUNT_BOOTSTRAP_SOFTWARE = PASS`
- final manual head: `a884557b84a22a92a291c907bcd36b08c564b4de`
- final Push Test: PASS
- final PR Test: PASS

Implemented:

- `SubprocessWechatURLLauncher` builds the public account home URL and invokes the existing Linux WeChat client
- secondary exit `255` is recorded only as dispatch evidence
- bounded polling observes `.xwechat/radium/web` through the private credential scanner
- success requires a matching credential candidate, not an exit code
- bearer-protected `POST /v1/public-accounts/bootstrap` body `{ "biz": "..." }`
- API returns only safe launch/candidate summaries; raw credentials never leave runtime process memory

This removes the need for a user terminal command from the intended product flow. The runtime API can perform the bootstrap operation once deployed into the logged-in Codespace.

## Remaining V1 gate

The remaining end-to-end gate is still real-account data, not software scaffolding:

**one named public account -> newest 20 articles -> verified timestamps -> unique canonical URLs -> verified freshness/account identity -> manual first/20th UI cross-check -> zero session secrets in output/logs**.

The next engineering step is to connect a private validated credential candidate to the real HTTP transport used by `AuthenticatedHistoryProvider`, with URL-launch/X11 navigation as bootstrap/fallback. This should be tested autonomously in CI with synthetic credentials and only later exercised against the already logged-in runtime through the local API rather than terminal input.

## Later

- bounded time-window / all-history pagination after newest-20 PASS
- automatic Codespaces Start/Stop wake gateway
- standalone `@微信` MCP packaging
- optional `深析` provider that receives only article metadata/URLs, never WeChat session material
