# WeChat Lite Runtime

A lightweight, on-demand GitHub Codespaces runtime for the official Linux WeChat client.

V0 deliberately does not rebuild or redistribute WeChat. It composes the upstream `ghcr.io/nickrunning/wechat-selkies:minimal` image with a small FastAPI control service. The upstream container downloads/contains the official Linux WeChat client and exposes it through Selkies WebRTC.

## Why this shape

The runtime is intended to behave like a sleeping web service rather than a permanently powered cloud desktop:

- GitHub repository: source, tests and Codespaces definition.
- GitHub Codespaces: the temporary compute host.
- `wechat-selkies:minimal`: Linux WeChat + browser UI.
- repository-local `state/`: persistent WeChat profile storage.
- FastAPI on `8787`: readiness/status/UI discovery for future MCP integration.

GitHub documents that stopped Codespaces stop their processes while saved files remain available when the Codespace starts again. The persistent path used by this project is:

`state/ -> /config`

Everything inside `state/` is Git-ignored.

## First run

1. Create a Codespace from this repository/feature branch.
2. Add a Codespaces secret named `WECHAT_CONTROL_TOKEN` with a random value.
3. Wait for both forwarded ports to appear:
   - `3001` — WeChat Web UI (HTTPS)
   - `8787` — Runtime Control API
4. Open port `3001` in the browser.
5. Scan the WeChat QR code once and complete login.
6. Confirm files appear under `state/` inside the Codespace; never commit them.

## Physical V0 acceptance

The merge gate is intentionally simple:

`scan -> stop -> start -> verify`

Detailed sequence:

1. Scan and reach the normal WeChat UI.
2. Record a non-sensitive state summary from `/v1/runtime/status`.
3. Stop the Codespace using GitHub's normal Stop action.
4. Start the same Codespace again.
5. Re-open port `3001`.
6. PASS if the same `state/` profile is mounted and WeChat resumes/reuses the saved login without profile loss.
7. A security-driven WeChat re-authentication request is recorded separately from storage loss; V0 cannot guarantee Tencent will never require a fresh scan.

## Control API

Health is intentionally public inside the forwarded Codespaces port:

```bash
curl http://127.0.0.1:8787/healthz
```

Protected endpoints require the Codespaces secret:

```bash
curl -H "Authorization: Bearer $WECHAT_CONTROL_TOKEN" \
  http://127.0.0.1:8787/v1/runtime/status

curl -H "Authorization: Bearer $WECHAT_CONTROL_TOKEN" \
  http://127.0.0.1:8787/v1/runtime/ui
```

`/v1/runtime/status` reports only aggregate persistent-storage counts and TCP readiness. It does not expose WeChat filenames, cookies, database contents, QR images or chat content.

## Local tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

The unit suite requires no WeChat binary, Docker daemon or network access.

## Security

- Do not commit anything from `state/`.
- Do not commit `WECHAT_CONTROL_TOKEN`, GitHub tokens, cookies or QR codes.
- Keep Codespaces forwarded ports private for V0.
- This repository contains orchestration code only; WeChat remains proprietary software.

## Upstream

Runtime image: `ghcr.io/nickrunning/wechat-selkies:minimal`

The upstream project supports AMD64/ARM64, browser access, `/config` persistence, automatic WeChat startup and optional auto-login behavior.
