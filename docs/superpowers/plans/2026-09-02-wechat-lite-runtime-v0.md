# WeChat Lite Runtime V0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a GitHub Codespaces runtime that launches the upstream WeChat Selkies container, persists `/config` under `/workspaces`, and exposes a token-protected status/UI control API.

**Architecture:** A two-service Dev Container Compose project runs a Python 3.12 workspace beside `ghcr.io/nickrunning/wechat-selkies:minimal`. The WeChat container mounts repository-local `state/` at `/config`; the Python service probes WeChat TCP readiness and constructs Codespaces forwarded-port URLs.

**Tech Stack:** GitHub Codespaces, Dev Containers, Docker Compose, Python 3.12, FastAPI, Uvicorn, pytest.

**Spec:** `docs/superpowers/specs/2026-09-02-wechat-lite-runtime-design.md`

## Global Constraints

- Reuse `ghcr.io/nickrunning/wechat-selkies:minimal`; do not fork or rebuild it in V0.
- Persist WeChat runtime data only under repository-local `state/`, mounted to `/config`.
- Never commit session/profile data from `state/`.
- Keep WeChat Web UI on port `3001` and control API on `8787`.
- Protected API endpoints require `WECHAT_CONTROL_TOKEN`.
- Tests must not require Docker, WeChat, network access, or proprietary binaries.

---

### Task 1: Runtime Pure Functions and Configuration

**Files:**
- Create: `app/__init__.py`
- Create: `app/config.py`
- Create: `app/runtime.py`
- Create: `tests/test_runtime.py`
- Create: `requirements.txt`
- Create: `requirements-dev.txt`

**Interfaces:**
- Produces: `Settings.from_env() -> Settings`
- Produces: `build_codespace_port_url(codespace_name: str | None, port: int) -> str | None`
- Produces: `summarize_state_dir(path: Path) -> dict[str, int | bool]`
- Produces: `probe_tcp(host: str, port: int, timeout: float = 0.5) -> bool`

- [ ] **Step 1: Write failing pure-function tests**

```python
from pathlib import Path

from app.runtime import build_codespace_port_url, summarize_state_dir


def test_build_codespace_port_url():
    assert build_codespace_port_url("silver-potato", 3001) == "https://silver-potato-3001.app.github.dev"


def test_build_codespace_port_url_without_codespace():
    assert build_codespace_port_url(None, 3001) is None


def test_summarize_empty_state_dir(tmp_path: Path):
    (tmp_path / ".gitignore").write_text("*\n", encoding="utf-8")
    assert summarize_state_dir(tmp_path) == {"initialized": False, "file_count": 0, "total_bytes": 0}


def test_summarize_state_dir_with_profile(tmp_path: Path):
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "session.db").write_bytes(b"abc")
    assert summarize_state_dir(tmp_path) == {"initialized": True, "file_count": 1, "total_bytes": 3}
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `pytest tests/test_runtime.py -q`

Expected: collection/import failure because `app.runtime` does not exist.

- [ ] **Step 3: Implement minimal runtime functions and settings**

`app/config.py` defines an immutable `Settings` dataclass with environment-backed values for token, Codespace name, state directory, host and port. `app/runtime.py` implements the URL builder, recursive state summary excluding `.gitignore`, and a TCP connection probe using `socket.create_connection`.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `pytest tests/test_runtime.py -q`

Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add app requirements*.txt tests/test_runtime.py
git commit -m "feat: add runtime configuration and probes"
```

### Task 2: Token-Protected Control API

**Files:**
- Create: `app/main.py`
- Create: `tests/test_api.py`

**Interfaces:**
- Consumes: `Settings`, `build_codespace_port_url`, `summarize_state_dir`, `probe_tcp`
- Produces: `create_app(settings: Settings, tcp_probe: Callable[[str, int, float], bool] = probe_tcp) -> FastAPI`
- Produces HTTP: `GET /healthz`, `GET /v1/runtime/status`, `GET /v1/runtime/ui`

- [ ] **Step 1: Write failing API tests**

```python
from pathlib import Path
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def settings(tmp_path: Path, token: str = "secret") -> Settings:
    return Settings(
        control_token=token,
        codespace_name="silver-potato",
        state_dir=tmp_path,
        wechat_host="wechat",
        wechat_port=3001,
        probe_timeout=0.1,
    )


def test_health_is_public(tmp_path):
    client = TestClient(create_app(settings(tmp_path), tcp_probe=lambda *_: True))
    assert client.get("/healthz").json() == {"status": "ok"}


def test_status_requires_bearer_token(tmp_path):
    client = TestClient(create_app(settings(tmp_path), tcp_probe=lambda *_: True))
    assert client.get("/v1/runtime/status").status_code == 401


def test_status_reports_runtime(tmp_path):
    (tmp_path / "profile.db").write_bytes(b"1234")
    client = TestClient(create_app(settings(tmp_path), tcp_probe=lambda *_: True))
    response = client.get("/v1/runtime/status", headers={"Authorization": "Bearer secret"})
    assert response.status_code == 200
    body = response.json()
    assert body["wechat_web_ready"] is True
    assert body["session_storage"]["initialized"] is True
    assert body["ui_url"] == "https://silver-potato-3001.app.github.dev"


def test_missing_configured_token_is_service_error(tmp_path):
    client = TestClient(create_app(settings(tmp_path, token=""), tcp_probe=lambda *_: True))
    response = client.get("/v1/runtime/status", headers={"Authorization": "Bearer anything"})
    assert response.status_code == 503
```

- [ ] **Step 2: Run and verify RED**

Run: `pytest tests/test_api.py -q`

Expected: import failure because `app.main` does not exist.

- [ ] **Step 3: Implement minimal FastAPI app**

Use `HTTPBearer(auto_error=False)` and `secrets.compare_digest`. Return `401` for missing/wrong tokens and `503` when the server token is not configured. Status uses the injected TCP probe so tests require no network.

- [ ] **Step 4: Run API and full test suite**

Run: `pytest -q`

Expected: `8 passed`.

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/test_api.py
git commit -m "feat: add protected runtime control api"
```

### Task 3: Codespaces and WeChat Compose Runtime

**Files:**
- Create: `.devcontainer/devcontainer.json`
- Create: `.devcontainer/docker-compose.yml`
- Create: `scripts/start-control-api.sh`
- Modify: `.gitignore`
- Keep: `state/.gitignore`

**Interfaces:**
- Provides forwarded HTTPS UI port `3001`.
- Provides control API port `8787`.
- Provides container DNS name `wechat` to the workspace service.
- Persists `../state` into WeChat `/config`.

- [ ] **Step 1: Add a configuration-contract test**

Create `tests/test_codespace_config.py` that parses the two JSON/YAML files and asserts: service `wechat` uses an image ending in `wechat-selkies:minimal`, has a `../state:/config` mount, sets `ENABLE_WECHAT_AUTO_LOGIN=true`, and `devcontainer.json` forwards ports `3001` and `8787`.

- [ ] **Step 2: Run and verify RED**

Run: `pytest tests/test_codespace_config.py -q`

Expected: failure because the Dev Container files do not exist.

- [ ] **Step 3: Write Compose and Dev Container configuration**

Compose uses `mcr.microsoft.com/devcontainers/python:1-3.12-bookworm` for `workspace`, `ghcr.io/nickrunning/wechat-selkies:minimal` by default for `wechat`, no GPU device mapping, `shm_size: 1gb`, and the persistent state mount. Dev Container runs `pip install -r requirements-dev.txt` at create time and `bash scripts/start-control-api.sh` at start time.

- [ ] **Step 4: Run tests and static config validation**

Run: `pytest -q`

Run: `python -m json.tool .devcontainer/devcontainer.json >/dev/null`

Expected: all tests pass and JSON validation exits zero.

- [ ] **Step 5: Commit**

```bash
git add .devcontainer scripts/start-control-api.sh .gitignore state/.gitignore tests/test_codespace_config.py
git commit -m "feat: add codespaces wechat runtime"
```

### Task 4: CI and Operator Documentation

**Files:**
- Create: `.github/workflows/test.yml`
- Create: `README.md`
- Create: `DEVELOPMENT.md`

**Interfaces:**
- CI: Python 3.12 `pytest -q`.
- Operator path: create Codespace -> set `WECHAT_CONTROL_TOKEN` Codespaces secret -> open `3001` -> scan once -> stop/start -> verify state.

- [ ] **Step 1: Add documentation/config assertions**

Extend `tests/test_codespace_config.py` to assert CI invokes `pytest -q` and README explicitly names the persistent path `state/ -> /config` plus the physical acceptance sequence `scan -> stop -> start -> verify`.

- [ ] **Step 2: Run and verify RED**

Run: `pytest tests/test_codespace_config.py -q`

Expected: failure because workflow/docs do not exist.

- [ ] **Step 3: Add CI, README, and DEVELOPMENT.md**

Document that the repository contains no WeChat binary and relies on upstream `wechat-selkies`; explain Codespaces storage lifecycle and that WeChat may independently require re-authentication. Include commands for local tests and control API curl calls.

- [ ] **Step 4: Run final verification**

Run: `pytest -q`

Run: `git status --short`

Expected: all tests pass; only intended files are changed/committed.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/test.yml README.md DEVELOPMENT.md tests/test_codespace_config.py
git commit -m "docs: add runtime acceptance and ci"
```

### Task 5: GitHub Delivery Branch

**Files:** all files from Tasks 1-4.

**Interfaces:** feature branch `feat/v0-codespace-runtime` with a draft PR to `main`.

- [ ] **Step 1: Re-run verification**

Run: `pytest -q`

Expected: all tests pass.

- [ ] **Step 2: Verify no runtime state is tracked**

Run: `git ls-files state`

Expected: only `state/.gitignore`.

- [ ] **Step 3: Push the branch and create a draft PR**

Push `feat/v0-codespace-runtime`; create a draft PR titled `feat: add on-demand Codespaces WeChat runtime` against `main`.

- [ ] **Step 4: Inspect CI status**

Read the workflow result for the branch/PR. Do not merge until CI is green and the physical login-persistence acceptance has been run in a Codespace.
