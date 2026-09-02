# WeChat Lite Runtime

A lightweight, on-demand GitHub Codespaces runtime for the official Linux WeChat client.

V0 deliberately does not rebuild or redistribute WeChat. It pins the upstream published release `ghcr.io/nickrunning/wechat-selkies:0.0.16` with a small FastAPI control service. The upstream container contains the official Linux WeChat client and exposes it through Selkies WebRTC.

The upstream floating `minimal` tag returned `manifest unknown` during a real GitHub Runner smoke test on 2026-09-02, so V0 intentionally uses the published `0.0.16` full image until a reliable minimal image is available. QQ remains disabled with `AUTO_START_QQ=false`.

Persistent session path: `state/ -> /config`.

Physical V0 gate: `scan -> stop -> start -> verify`.

Runtime image: `ghcr.io/nickrunning/wechat-selkies:0.0.16`.

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

**Important after this networking/image fix:** if you already created a Codespace before commit `0d439822`, rebuild the container once so the updated `.devcontainer` networking is applied. GitHub Codespaces does not apply changed dev-container port configuration to an already-created container until it is rebuilt.

## Control-token behavior

No manual secret setup is required for V0. If `WECHAT_CONTROL_TOKEN` is not provided, the runtime creates a cryptographically random token at `state/.control-token` with mode `0600` and reuses it after Codespace stop/start.

If you explicitly configure `WECHAT_CONTROL_TOKEN` as a Codespaces secret, that value takes precedence and no local token file is created.

## V1 public-account discovery: safe probe

V1 development lives on `feat/v1-public-account-discovery`. The first physical step intentionally does **not** read or export message bodies, cookies, browser session tokens, QR data, raw database rows or encryption keys. It only classifies candidate runtime artifacts and returns sanitized aggregate roots/counts.

After switching the existing logged-in Codespace to the V1 branch, run:

```bash
bash scripts/probe-wechat-state.sh
```

The command self-heals the local control API, reads the private control token only inside the process, calls `127.0.0.1:8787/v1/wechat/probe`, and prints sanitized JSON. It does not print cookies, auth tokens, raw WeChat database contents, contacts or messages.

The probe result is used to choose the concrete authenticated WebView/history extraction path. Real session-reading code is not enabled until the sanitized probe establishes which artifact classes are actually present.
