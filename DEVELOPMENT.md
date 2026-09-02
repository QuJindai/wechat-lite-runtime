# Development Status

## V0 objective

Prove the lightweight Codespaces architecture before adding wake orchestration, MCP packaging or public-account automation.

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

No manual `WECHAT_CONTROL_TOKEN` setup is required for V0. The runtime creates and persists a local control token automatically when an explicit secret is absent.

## V1 next phase

Build authenticated public-account discovery on top of the proven logged-in WeChat runtime. V1 scope:

1. Select or search a public account in the logged-in WeChat UI.
2. Open its history / all-messages surface.
3. Extract normalized article metadata: title, canonical URL, published time, account identity and pagination cursor.
4. Support `recent N` and bounded time-window collection.
5. Deduplicate and persist only article metadata outside the private WeChat session directory.
6. Expose a small local API suitable for later standalone `@微信` MCP packaging.
7. Keep WeChat credentials, cookies, local databases and session material private to the runtime.

The first V1 gate is: **one named public account -> newest 20 articles with verified timestamps and no duplicate URLs**.

## Later phases

- Wake gateway / automatic Codespaces Start/Stop orchestration.
- Standalone `@微信` MCP packaging.
- Optional integration: expose article URLs to `深析` as a provider without sharing WeChat session material.
