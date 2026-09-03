# WeChat Lite Runtime

A lightweight, on-demand GitHub Codespaces runtime for the official Linux WeChat client.

The runtime pins `ghcr.io/nickrunning/wechat-selkies:0.0.16`, keeps WeChat profile data under `state/ -> /config`, exposes the Selkies UI on `3001`, and runs a private FastAPI control/discovery service on `8787`.

Physical V0 gate: `scan -> stop -> start -> verify`.

## V0 persistence

V0 is physically verified: the same Codespace can stop/start while preserving the local WeChat profile and logged-in state. The control API also self-heals after restart.

V0 acceptance commands remain available:

```bash
python -m app.acceptance before
python -m app.acceptance after
```

No manual `WECHAT_CONTROL_TOKEN` setup is required. If no explicit secret is supplied, the runtime creates a random token at `state/.control-token` with mode `0600` and reuses it after restart.

V0 Codespaces quickstart:

```text
https://codespaces.new/QuJindai/wechat-lite-runtime/tree/feat/v0-codespace-runtime?quickstart=1
```

## V1 public-account discovery

V1 development lives on `feat/v1-public-account-discovery` and uses the already logged-in official Linux WeChat runtime. Session material remains inside `state/` and process memory.

The preferred API is:

```text
POST /v1/public-accounts/discover
```

Minimal body:

```json
{
  "account_name": "目标公众号",
  "limit": 20
}
```

`biz` is optional. When it is already known it can be provided to skip identity resolution:

```json
{
  "account_name": "目标公众号",
  "biz": "PUBLIC_BIZ_ID",
  "limit": 20
}
```

The runtime attempts discovery in this order:

1. persisted seed-verified public-account identity, when available
2. matching private Chromium History seed already observed by WeChat
3. authenticated WebView credential candidates
4. URL bootstrap through the internal WeChat-container bridge
5. evidence-gated X11 search fallback

The X11 fallback only navigates the existing WeChat window by keyboard. It does not read chats, export contacts, read the clipboard, click chat content, or send messages. A unique credential delta may guide one unverified discovery, but UI navigation is not account-identity proof and is never persisted by itself. A caller-supplied name or biz is not identity evidence.

## Name-to-biz index

After successful public-seed identity validation, the runtime may save the non-sensitive verified identity in:

```text
state/.public-account-index.json
```

The version 2 index stores only seed-verified identities: normalized public-account display name, public `biz`, `public_seed_article` provenance and canonical public seed URL. The file is mode `0600` and contains no cookie, `key`, `pass_ticket`, `appmsg_token`, private request URL, message, contact or browser-session value. Generic explicit-biz and UI-delta discoveries are not written. Subsequent name-only requests may reuse only seed-verified identities.

## Newest-20 acceptance

The authoritative final V1 gate resolves identity from a public seed article:

```text
POST /v1/public-accounts/acceptance-from-url
```

Body:

```json
{
  "article_url": "https://mp.weixin.qq.com/s/PUBLIC_ARTICLE_ID"
}
```

`POST /v1/public-accounts/acceptance` remains compatible with name/biz callers, but those caller values cannot establish identity and therefore cannot pass by themselves. The seed endpoint always requests 20 articles and checks:

- exactly 20 articles
- count satisfied
- all timestamps present
- unique canonical URLs
- account identity verified
- freshness verified

Account verification requires a seed-resolved display-name-to-biz identity and matching article biz values. Freshness verification requires a successful live offset-zero `profile_ext?action=getmsg` observation during the current call; cached, byte-only and synthetic data remain unverified.

If those automated checks pass, the verdict is:

```text
AUTOMATED_GATE_PASS_UI_PENDING
```

The response includes only the first and twentieth article's public metadata for the final WeChat UI cross-check. Until that real logged-in cross-check is completed, `V1_REAL_NEWEST20` remains pending.

## Security boundary

Allowed outside the private runtime: public-account name, public biz identifier, article title, canonical article URL, publication time, order and completeness/verification flags.

Not exposed: cookies, bearer/session tokens, `key`, `pass_ticket`, `appmsg_token`, raw History rows, browser-profile files, QR contents, contacts, chats, request headers or encryption keys.

The internal workspace-to-WeChat launcher bridge is reachable only on the private Compose network as `wechat:8790`; it requires the runtime bearer token and is not published or forwarded through Codespaces.

## Diagnostic probes

The structural probes remain available for development:

```bash
bash scripts/probe-wechat-state.sh
bash scripts/probe-wechat-webview.sh
bash scripts/probe-history-seed.sh
```

The safe runtime probe does not print cookies, auth tokens, raw WeChat database contents, contacts or messages.

The WebView probe returns only sanitized paths, allowlisted schema names and marker counts; unknown path and SQLite identifiers are redacted. File, byte, directory and elapsed-time budgets are explicit, and a bounded scan reports truncation rather than success. It does not return cookie or token values, Local Storage values or database rows.
