# WeChat Lite Runtime

A lightweight, on-demand GitHub Codespaces runtime for the official Linux WeChat client.

V0 deliberately does not rebuild or redistribute WeChat. It composes the upstream `ghcr.io/nickrunning/wechat-selkies:minimal` image with a small FastAPI control service. The upstream container downloads/contains the official Linux WeChat client and exposes it through Selkies WebRTC.

Persistent session path: `state/ -> /config`.

Physical V0 gate: `scan -> stop -> start -> verify`.

Runtime image: `ghcr.io/nickrunning/wechat-selkies:minimal`.

## One-command V0 acceptance

After the first QR scan has completed and the WeChat profile exists:

```bash
python -m app.acceptance before
```

Stop the Codespace, start the same Codespace again, then run:

```bash
python -m app.acceptance after
```

The helper records only aggregate storage counts and runtime readiness. It never reads or prints WeChat database contents, cookies, filenames, contacts, messages, or QR data.

Expected automated verdict after restart:

- `STORAGE_PASS_AUTH_PENDING` — persistent state survived and WeChat Web UI is ready; open the UI and confirm the account is still logged in.
- `RUNTIME_NOT_READY` — the state exists but the WeChat Web UI is not listening yet.
- `STATE_LOST` — the persistent acceptance marker or initialized profile is missing.

## Open or resume the V0 Codespace

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/QuJindai/wechat-lite-runtime/tree/feat/v0-codespace-runtime?quickstart=1)

The `quickstart=1` link resumes your most recent matching Codespace when available; otherwise it opens the create-Codespace page for the V0 feature branch.

## Control-token behavior

No manual secret setup is required for V0. If `WECHAT_CONTROL_TOKEN` is not provided, the runtime creates a cryptographically random token at `state/.control-token` with mode `0600` and reuses it after Codespace stop/start.

If you explicitly configure `WECHAT_CONTROL_TOKEN` as a Codespaces secret, that value takes precedence and no local token file is created.
