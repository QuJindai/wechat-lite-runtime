# Development Status

## V0 objective

Prove the lightweight Codespaces architecture before adding a wake gateway, MCP layer or public-account automation.

## Current software gate

The branch must pass:

```bash
python -m pytest -q
python -m json.tool .devcontainer/devcontainer.json >/dev/null
bash -n scripts/start-control-api.sh
```

## Verified software status

- Local isolated workspace: `python -m pytest -q` -> **18 passed**.
- Dev Container JSON validation: PASS.
- Control startup shell syntax: PASS.
- GitHub push workflow run `33534140318`: **success**.
- GitHub pull-request workflow run `33534153102`: **success**.
- Draft PR: `#1 feat: add on-demand Codespaces WeChat runtime`.
- GitHub development status: `development_ready`.
- Remaining gate: `PHYSICAL_LOGIN_PERSISTENCE`.

## Physical gate: PHYSICAL_LOGIN_PERSISTENCE

This gate requires a real GitHub Codespace and a real WeChat login.

1. Create the Codespace from `feat/v0-codespace-runtime`.
2. Set `WECHAT_CONTROL_TOKEN` as a Codespaces secret.
3. Open forwarded HTTPS port `3001`.
4. Scan the login QR code and reach the normal WeChat interface.
5. Confirm `/v1/runtime/status` reports `session_storage.initialized=true`.
6. Stop the Codespace.
7. Start the same Codespace.
8. Confirm `session_storage.initialized=true` with nonzero persisted bytes.
9. Open port `3001` and verify the profile is reused.

PASS means the persistent profile survived stop/start and WeChat reused it without profile recreation. If Tencent explicitly requires account re-authentication while the stored profile remains intact, record `AUTH_RESCAN_REQUIRED` rather than `STATE_LOST`.

**Do not merge** the V0 branch into `main` until `PHYSICAL_LOGIN_PERSISTENCE` has a PASS result or the user explicitly accepts the remaining device-only gate.

## Deferred phases

- V1: external wake gateway for GitHub Codespaces Start/Stop REST API.
- V2: authenticated WeChat UI/session-state probe.
- V3: public-account history discovery and recent-article extraction.
- V4: standalone `@微信` MCP packaging.
- Optional later integration: expose article URLs to `深析` as a provider without sharing WeChat session material.
