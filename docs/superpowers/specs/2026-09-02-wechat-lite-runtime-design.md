# WeChat Lite Runtime V0 Design

## Goal

Build a lightweight, on-demand WeChat runtime that lives in GitHub Codespaces, reuses the official Linux WeChat packaged by `nickrunning/wechat-selkies`, preserves login/session data under the Codespaces persistent `/workspaces` storage, and exposes a small control API. The runtime must be able to stop with the Codespace and restart without losing its local WeChat profile.

## V0 Acceptance Gates

1. A Codespace starts two services: a Python control workspace and `wechat-selkies:minimal`.
2. The WeChat Web UI is reachable through forwarded port `3001`.
3. WeChat runtime data is bind-mounted from repository-local `state/` to `/config` and is never committed to Git.
4. Stopping and starting the Codespace preserves `state/`.
5. The control API restarts automatically with the Codespace and reports whether the WeChat Web UI TCP port is ready.
6. The control API returns the Codespaces browser URL for the WeChat UI without hard-coding a host name.
7. Protected control endpoints require a bearer token; `/healthz` remains unauthenticated for readiness checks.
8. CI runs unit tests without needing the proprietary WeChat binary or a Docker daemon.

The first physical acceptance after code completion is: first scan -> stop Codespace -> start Codespace -> confirm saved session is reused. A forced re-scan by WeChat security policy is not treated as storage failure unless `state/` was lost or replaced.

## Architecture

```text
Browser / future @WeChat MCP
          |
          v
GitHub Codespaces forwarded ports
  8787 -> FastAPI control API
  3001 -> WeChat Selkies Web UI
          |
          v
.devcontainer/docker-compose.yml
  workspace (Python 3.12) ---- TCP probe ----> wechat service
                                           ghcr.io/nickrunning/wechat-selkies:minimal
                                                     |
                                                     v
                                             state/ -> /config
```

The project deliberately does not fork or rebuild `wechat-selkies` in V0. The upstream image already wraps the official Linux WeChat client, supports AMD64/ARM64, persists `/config`, exposes a Selkies browser UI, and supports auto-start/auto-login behavior. Keeping it as an external image makes our code small and allows upstream WeChat package updates to remain upstream concerns.

## Components

### `.devcontainer/devcontainer.json`

Defines the Codespaces development environment, the workspace service, automatic startup commands, and forwarded ports `3001` and `8787`. Port `3001` is treated as HTTPS and kept private by GitHub Codespaces defaults.

### `.devcontainer/docker-compose.yml`

Runs:

- `workspace`: Python 3.12 dev container used for the control API and tests.
- `wechat`: `ghcr.io/nickrunning/wechat-selkies:minimal` with `../state:/config`, 1 GiB shared memory, WeChat auto-start enabled, QQ disabled, and auto-login enabled.

No `/dev/dri` device is required for V0 because Codespaces should work without GPU acceleration.

### `app/`

A minimal FastAPI service with pure, testable runtime functions:

- `Settings.from_env()` reads runtime configuration.
- `build_codespace_port_url()` derives `https://<codespace>-<port>.app.github.dev`.
- `probe_tcp()` checks whether the WeChat web port is accepting connections.
- `summarize_state_dir()` reports whether persistent profile data exists without exposing filenames or contents.
- `/healthz` is public.
- `/v1/runtime/status` and `/v1/runtime/ui` require a bearer token.

### `scripts/start-control-api.sh`

Idempotently starts Uvicorn on `0.0.0.0:8787` during every Codespace start. Runtime logs and PID files live under `/tmp` and are intentionally non-persistent.

### `state/`

Runtime-only WeChat data. The directory exists in Git but all contents are ignored. This is the only path mounted to `/config` in the WeChat container.

## Security Boundaries

- No WeChat cookies, databases, device identity files, screenshots, QR codes, or chat data may be committed.
- `state/` is ignored by Git.
- No GitHub token is stored in the repository.
- Future wake-gateway credentials belong in platform secrets, not `.env` committed files.
- Control endpoints use a bearer token from `WECHAT_CONTROL_TOKEN`.
- The project does not expose a public automation endpoint in V0.

## Data Flow

### First login

1. Start Codespace.
2. Compose starts `wechat` and `workspace`.
3. Open the forwarded `3001` URL.
4. Scan the official WeChat login QR code.
5. WeChat writes its local profile into `/config`, which is actually repository-local `state/`.

### Restart

1. Codespace stops; processes stop but `/workspaces` files remain.
2. Codespace starts again.
3. Compose remounts the same `state/` into `/config`.
4. `ENABLE_WECHAT_AUTO_LOGIN=true` allows the upstream runtime to reuse the saved profile when WeChat permits it.
5. The control API reports readiness and returns the UI URL.

## Error Semantics

- Missing `WECHAT_CONTROL_TOKEN`: protected endpoints return HTTP 503 `control_token_not_configured`.
- Missing/incorrect bearer token: HTTP 401 `unauthorized`.
- Missing `CODESPACE_NAME`: UI URL is `null`; runtime status still works locally.
- WeChat TCP port unavailable: status remains HTTP 200 with `wechat_web_ready=false` so callers can distinguish runtime booting from API failure.
- Empty `state/`: `session_storage.initialized=false`.

## Testing

Unit tests run entirely without Docker or WeChat. Tests cover URL generation, state-directory summarization, authentication, and runtime status behavior using dependency injection for the TCP probe. CI runs `pytest -q` on Python 3.12.

## Deferred Work

The following are intentionally not part of this V0 implementation plan:

- External wake gateway that calls GitHub Codespaces Start/Stop APIs.
- MCP packaging.
- WeChat GUI automation and public-account history extraction.
- Integration with `深析`.
- Automatic detection of whether the WeChat account is actually logged in.

These are separate subsystems and will be added only after the login persistence gate passes.
