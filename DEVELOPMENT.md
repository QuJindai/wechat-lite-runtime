# Development Status

## V0 final status

**V0 = PASS**

Verified on the real GitHub Codespace `musical-guide-vxp45jxgj442wg75` on 2026-09-02:

- Repository visibility: **public**.
- WeChat Linux runtime starts successfully through the pinned `ghcr.io/nickrunning/wechat-selkies:0.0.16` image.
- Codespace workspace and WeChat service share the required network namespace.
- WeChat Web UI port `3001` is reachable and opens the normal WeChat interface.
- Runtime Control API `8787` has self-healing startup during acceptance.
- `python -m app.acceptance before` returned `BASELINE_RECORDED`.
- Baseline session state: initialized=true, file_count=1171, total_bytes=266600596.
- The same Codespace was stopped and restarted.
- `python -m app.acceptance after` returned `STORAGE_PASS_AUTH_PENDING`.
- Marker survived=true; session initialized before/after=true; WeChat Web UI ready after restart=true.
- Post-restart session state: file_count=1171, total_bytes=267093832.
- User visually confirmed the normal WeChat interface remained logged in without rescanning a QR code.

Therefore:

- `CODESPACE_STATE_PERSISTENCE = PASS`
- `PHYSICAL_LOGIN_PERSISTENCE = PASS`

## V1 Phase A software status

V1 branch: `feat/v1-public-account-discovery`.

Implemented and covered by synthetic CI contracts:

- sanitized runtime artifact classifier and bearer-protected `GET /v1/wechat/probe`
- article URL canonicalization and auth/query redaction
- normalized article/discovery models with independent completeness flags
- synthetic multi-page provider with deterministic URL deduplication and explicit provider errors
- bearer-protected `GET /v1/public-accounts/{account}/recent?limit=20` provider API contract
- one-command real-Codespace safe probe handoff

Status:

- `V1_PHASE_A_SOFTWARE = PASS`
- `V1_SAFE_RUNTIME_PROBE = PENDING_PHYSICAL`

The next physical action is to run `bash scripts/probe-wechat-state.sh` inside the already logged-in Codespace after switching it to this branch. Only sanitized artifact classes, counts and redacted relative roots may be shared back.

The probe evidence determines whether the authenticated history implementation can use a WebView/browser-session path directly or needs GUI guidance/local-cache verification. Do not guess cookie/database paths before this evidence exists.

The first end-to-end V1 gate remains: **one named public account -> newest 20 articles -> verified timestamps -> unique canonical URLs -> verified freshness/account identity -> manual first/20th UI cross-check -> zero session secrets in output/logs**.

## Later phases

- authenticated WebView/history extraction based on the physical safe-probe evidence
- bounded time-window/all-history pagination after newest-20 PASS
- wake gateway / automatic Codespaces Start/Stop orchestration
- standalone `@微信` MCP packaging
- optional integration: expose article URLs to `深析` as a provider without sharing WeChat session material
