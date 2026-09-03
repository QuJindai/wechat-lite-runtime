# V1 Public Account Discovery Design

Date: 2026-09-02
Base: `feat/v0-codespace-runtime` after V0 physical login persistence PASS
Target branch: `feat/v1-public-account-discovery`

## 1. Objective

Use the already proven logged-in official Linux WeChat runtime to discover public-account article history without exposing WeChat credentials or session material.

First V1 gate:

> one named public account -> newest 20 articles -> verified timestamps -> unique canonical URLs -> manual head/tail cross-check against WeChat UI

V1 does not yet build a standalone MCP, wake gateway, or deep-analysis integration.

## 2. Architecture Decision

Use a three-layer strategy:

1. **Primary: authenticated WebView/history provider**
   - Reuse the authenticated WeChat session already present in the runtime.
   - Discover the public-account history/all-messages WebView and the local browser/session artifacts required to access `mp.weixin.qq.com` history pages.
   - Perform history pagination inside the private runtime.
   - Never return cookies, request headers, tokens, local database contents, or browser-profile material.

2. **UI guidance fallback**
   - Use GUI automation only to navigate the official Linux WeChat client to the selected public account and open the history/all-messages surface when the authenticated WebView cannot be reached directly.
   - Avoid coordinate-dependent per-article clicking as the normal extraction path.

3. **Local cache/database cross-check**
   - Inspect `xwechat_files` / local cache metadata only to confirm account identity, known URLs, or observed article records.
   - Local cache is not treated as exhaustive because it only contains material the client has observed or cached.

## 3. Security Boundary

The persistent `state/` directory is the private trust boundary.

Allowed outside the trust boundary:

- account display name
- account original/business identifier when already present in article URLs or public metadata
- article title
- canonical article URL
- published timestamp
- article order/position
- pagination completeness metadata
- provider/verification status
- aggregate probe counts and sanitized path classes

Forbidden outside the trust boundary:

- cookies
- auth/session tokens
- QR contents
- request authorization headers
- local WeChat databases or raw rows
- message/contact content unrelated to the requested public account
- browser-profile files
- encryption keys
- full filenames when they reveal user/account identifiers

Logs must redact query values for auth-bearing URLs and must never print cookies or headers.

## 4. V1 Phase A: Safe Runtime Probe

Add an explicit probe that examines the mounted `state/` tree and reports only sanitized structural evidence.

Output schema:

```json
{
  "state_initialized": true,
  "artifact_classes": [
    {
      "class": "xwechat_db",
      "count": 0,
      "relative_roots": ["xwechat_files/..."],
      "candidate": true
    },
    {
      "class": "webview_cache",
      "count": 0,
      "relative_roots": ["..."],
      "candidate": true
    },
    {
      "class": "mp_weixin_trace",
      "count": 0,
      "relative_roots": ["..."],
      "candidate": true
    }
  ],
  "sensitive_values_returned": false
}
```

Probe rules:

- file contents are not returned
- cookie stores are classified but not opened for API output
- SQLite schema may be inspected locally, but only sanitized table/column names required for routing may be returned
- no user message content is read
- probe failures are explicit and non-destructive

## 5. V1 Phase B: Provider Interface

Define one internal provider contract so WebView, GUI, and local-cache strategies can be swapped without changing the external API.

```python
class PublicAccountProvider(Protocol):
    def recent_articles(
        self,
        account: str,
        limit: int,
        since: datetime | None = None,
    ) -> DiscoveryResult: ...
```

Normalized article model:

```json
{
  "account_name": "example",
  "biz": "...",
  "title": "...",
  "canonical_url": "https://mp.weixin.qq.com/s/...",
  "published_at": "2026-09-01T08:00:00+08:00",
  "position": 1,
  "observed_at": "...",
  "source": "authenticated_wechat",
  "verified_account": true
}
```

Discovery result metadata:

```json
{
  "requested_count": 20,
  "article_count": 20,
  "timestamps_complete": true,
  "urls_unique": true,
  "is_exhaustive_for_window": false,
  "pagination_cursor": "opaque-or-null",
  "provider": "authenticated_wechat",
  "verification": "ui_cross_checked"
}
```

`pagination_cursor` is opaque. It must not expose auth-bearing parameters.

## 6. V1 Phase C: Local API

Extend the existing FastAPI service with authenticated local-only endpoints:

- `GET /v1/wechat/probe`
- `GET /v1/public-accounts/{account}/recent?limit=20`
- later: `GET /v1/public-accounts/{account}/articles?since=...&until=...`

Requirements:

- existing control bearer token protects the API
- API defaults to loopback / Codespace private forwarding
- no direct cookie/session endpoints
- provider errors use explicit classes such as `LOGIN_REQUIRED`, `ACCOUNT_NOT_FOUND`, `HISTORY_SURFACE_UNAVAILABLE`, `PAGINATION_INCOMPLETE`

## 7. Completeness Semantics

Do not repeat the previous deep-analysis problem where `count_satisfied=true` looked like success even when freshness was not proven.

V1 must keep these dimensions separate:

- `count_satisfied`
- `timestamps_complete`
- `urls_unique`
- `account_verified`
- `freshness_verified`
- `is_exhaustive_for_window`

For `recent 20`, PASS requires all except `is_exhaustive_for_window`, which is only required for bounded time-window/all-history requests.

## 8. Testing Strategy

### Unit tests

- artifact classifier never returns file contents
- redaction removes cookie/auth/query material
- article normalization canonicalizes URLs and timestamps
- duplicate URLs collapse deterministically
- count/freshness/completeness flags are independent
- provider fallbacks preserve normalized result shape

### Integration tests

Use synthetic fixtures only; no real session files in GitHub CI.

- synthetic `state/` tree -> probe output
- synthetic history pages -> newest 20 normalized results
- pagination across multiple fixtures
- malformed/expired session response -> explicit `LOGIN_REQUIRED`

### Codespace physical gate

Against a real logged-in runtime:

1. choose one named public account visible in WeChat
2. fetch newest 20
3. verify 20 unique canonical URLs
4. verify all 20 timestamps parse and are ordered newest-first
5. manually compare newest and oldest returned items with the WeChat history UI
6. confirm no cookie/token/session value appears in API output or logs

## 9. Non-Goals for V1

- chat message automation
- contact export
- sending messages
- background monitoring across many accounts
- wake/start/stop orchestration
- standalone MCP publication
- integration into `深析`
- scraping via unauthenticated search engines as the primary source

## 10. Delivery Sequence

1. Safe runtime probe
2. Redaction helpers and normalized models
3. Provider interface + synthetic provider
4. Authenticated WebView discovery implementation
5. UI guidance fallback only if required
6. Local-cache verification adapter
7. FastAPI endpoints
8. Real Codespace newest-20 gate
9. Only after gate PASS: time-window pagination

## 11. Acceptance Criteria

V1 newest-20 gate is PASS only when one real public account produces:

- `article_count == 20`
- `count_satisfied == true`
- `timestamps_complete == true`
- `urls_unique == true`
- `account_verified == true`
- `freshness_verified == true`
- first and twentieth article manually match the WeChat history surface
- zero sensitive session values in output/logs

Until then V1 remains experimental and must not be exposed as a general-purpose WeChat plugin.
