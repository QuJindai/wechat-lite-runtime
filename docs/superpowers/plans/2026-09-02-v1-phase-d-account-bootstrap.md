# V1 Phase D Automated Account Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let the local runtime trigger an existing logged-in Linux WeChat instance to open a public-account home page and automatically observe a matching private WebView credential candidate without requiring terminal input.

**Architecture:** A launcher builds the public `profile_ext?action=home&__biz=...&scene=124` URL and invokes the already-running `/usr/bin/wechat`. Runtime CLI evidence established that secondary invocations always return 255 regardless of URL, so exit code is recorded as dispatch evidence only, not success/failure of navigation. A bounded polling loop then scans only `.xwechat/radium/web` with the existing credential scanner. The API returns only safe candidate summaries and never returns raw request URLs or credential values.

**Tech Stack:** Python 3.12, subprocess, pathlib, time, existing credential scanner/FastAPI bearer auth/pytest.

**Spec:** `docs/superpowers/specs/2026-09-02-v1-public-account-discovery-design.md`

## Global Constraints

- No raw credential candidate, request URL, token, cookie, pass_ticket, uin, key or poc value may leave runtime process memory.
- Secondary WeChat exit 255 is treated as `dispatch_attempted`, not as proof that the URL opened.
- Success requires observing a matching credential candidate after dispatch.
- Scan roots are limited to `<state>/.xwechat/radium/web`.
- Polling is bounded by timeout and scanner budgets.
- API is bearer protected and navigation-only; it never sends messages or changes account settings.

### Task 1: Launcher and bounded bootstrap loop

**Files:**
- Create: `app/account_bootstrap.py`
- Create: `tests/test_account_bootstrap.py`

**Interfaces:**
- `WechatURLLauncher.open_public_account(biz: str) -> LaunchEvidence`
- `bootstrap_public_account(biz: str, state_dir: Path, launcher: WechatURLLauncher, timeout_seconds: float, poll_seconds: float, scan_fn=scan_credentials) -> BootstrapResult`

Steps: RED tests for URL construction, accepted secondary exit 255, poll-until-candidate, timeout, and zero secret serialization; implement minimal launcher/loop; run GREEN.

### Task 2: Bearer-protected bootstrap API

**Files:**
- Modify: `app/main.py`
- Create: `tests/test_account_bootstrap_api.py`

**Interface:**
- `POST /v1/public-accounts/bootstrap` body `{ "biz": "..." }`

Steps: RED tests for bearer protection, validation, safe JSON, and no raw candidate fields; inject launcher/bootstrap service into `create_app`; implement; run full CI.

### Task 3: Runtime CLI evidence handoff

Use existing real-runner evidence rather than repeating the secondary-invocation experiment:
- `/usr/bin/wechat` -> `/opt/wechat/wechat`
- all secondary calls return 255
- window count unchanged in empty-state runner
- therefore bootstrap treats exit code only as dispatch evidence and relies on credential observation as the gate.

Real logged-in gate later runs through the API itself; no manual terminal command is part of the product flow.
