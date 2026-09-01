# Development Status

## V0 objective

Prove the lightweight Codespaces architecture before adding a wake gateway, MCP layer or public-account automation.

## Verified software status

- Repository visibility: **public**.
- Local isolated workspace after acceptance-helper update: `python -m pytest -q` -> **29 passed**.
- Dev Container JSON validation: PASS.
- Control startup shell syntax: PASS.
- Codespaces WeChat UI port `3001` is configured to auto-open in the browser.
- Restart acceptance helper added: `python -m app.acceptance before|after`.
- Helper records only aggregate state counts and readiness; it does not read WeChat content.
- Draft PR: `#1 feat: add on-demand Codespaces WeChat runtime`.
- Remaining gate: `PHYSICAL_LOGIN_PERSISTENCE`.

## Physical gate: PHYSICAL_LOGIN_PERSISTENCE

1. Create the Codespace from `feat/v0-codespace-runtime`.
2. Set `WECHAT_CONTROL_TOKEN` as a Codespaces secret.
3. Port `3001` auto-opens the WeChat Web UI.
4. Scan the login QR code and reach the normal WeChat interface.
5. Run `python -m app.acceptance before`.
6. Stop the Codespace.
7. Start the same Codespace.
8. Run `python -m app.acceptance after`.
9. Automated target verdict: `STORAGE_PASS_AUTH_PENDING`.
10. Visually confirm WeChat is still logged in. Then the physical gate is PASS.

`STATE_LOST` means the persistent marker/profile disappeared. `AUTH_RESCAN_REQUIRED` means Tencent requested re-authentication while persistent storage remained intact; these are different failures.

**Do not merge** the V0 branch into `main` until `PHYSICAL_LOGIN_PERSISTENCE` has a PASS result or the user explicitly accepts the remaining device-only gate.

## Deferred phases

- V1: external wake gateway for GitHub Codespaces Start/Stop REST API.
- V2: authenticated WeChat UI/session-state probe.
- V3: public-account history discovery and recent-article extraction.
- V4: standalone `@微信` MCP packaging.
- Optional later integration: expose article URLs to `深析` as a provider without sharing WeChat session material.
