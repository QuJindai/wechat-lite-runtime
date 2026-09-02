from __future__ import annotations

import hashlib
import urllib.error
import urllib.request
from typing import Callable, Protocol
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from app.credential_scanner import CaptureCandidate
from app.history_seed import HistorySeed
from app.providers import ProviderError

_ALLOWED_SCHEME = "https"
_ALLOWED_HOST = "mp.weixin.qq.com"
_ALLOWED_PATH = "/mp/profile_ext"
_ALLOWED_CREDENTIAL_PATHS = {"/mp/profile_ext", "/mp/relatedsearchword"}
_FIELD_TO_QUERY = {
    "biz": "__biz",
    "uin": "uin",
    "key": "key",
    "pass_ticket": "pass_ticket",
    "appmsg_token": "appmsg_token",
    "poc_sid": "poc_sid",
    "poc_token": "poc_token",
    "mid": "mid",
    "idx": "idx",
    "sessionid": "sessionid",
}


class ResponseLike(Protocol):
    status: int

    def read(self, amount: int = -1) -> bytes: ...

    def geturl(self) -> str: ...

    def close(self) -> None: ...


OpenFn = Callable[[urllib.request.Request, float], ResponseLike]


def _parsed_query(url: str) -> tuple[object, dict[str, list[str]]]:
    try:
        parsed = urlsplit(url)
        query = parse_qs(parsed.query, keep_blank_values=True)
    except (TypeError, ValueError) as exc:
        raise ProviderError("HISTORY_SURFACE_UNAVAILABLE", "invalid_private_history_url") from exc
    return parsed, query


def _validate_history_endpoint(url: str) -> tuple[object, dict[str, list[str]]]:
    parsed, query = _parsed_query(url)
    if (
        parsed.scheme != _ALLOWED_SCHEME
        or parsed.hostname != _ALLOWED_HOST
        or parsed.path != _ALLOWED_PATH
    ):
        raise ProviderError("HISTORY_SURFACE_UNAVAILABLE", "history_endpoint_not_allowed")
    return parsed, query


def _validate_credential_source(url: str) -> tuple[object, dict[str, list[str]]]:
    parsed, query = _parsed_query(url)
    if (
        parsed.scheme != _ALLOWED_SCHEME
        or parsed.hostname != _ALLOWED_HOST
        or parsed.path not in _ALLOWED_CREDENTIAL_PATHS
    ):
        raise ProviderError("HISTORY_SURFACE_UNAVAILABLE", "credential_source_not_allowed")
    return parsed, query


def _candidate_context(candidate: CaptureCandidate) -> tuple[str, dict[str, str]]:
    parsed, query = _validate_credential_source(candidate.request_url)
    context: dict[str, str] = {}
    for field_name, query_name in _FIELD_TO_QUERY.items():
        value = candidate.fields.get(field_name, "")
        if not value:
            continue
        values = query.get(query_name) or []
        if not values or values[0] != value:
            raise ProviderError("HISTORY_SURFACE_UNAVAILABLE", "credential_candidate_invalid")
        context[query_name] = value

    biz = context.get("__biz", "")
    if parsed.path == "/mp/relatedsearchword":
        required = ("__biz", "uin", "key", "pass_ticket", "appmsg_token", "mid", "idx", "sessionid")
        ready = all(context.get(name) for name in required)
    else:
        legacy_ready = all(context.get(name) for name in ("uin", "key", "pass_ticket"))
        token_ready = all(context.get(name) for name in ("appmsg_token", "pass_ticket"))
        ready = legacy_ready or token_ready
    if not biz or not ready:
        raise ProviderError("HISTORY_SURFACE_UNAVAILABLE", "credential_candidate_incomplete")
    return str(parsed.path), context


def candidate_from_history_seed(seed: HistorySeed) -> CaptureCandidate:
    parsed, query = _validate_history_endpoint(seed._raw_url)
    fields: dict[str, str] = {}
    for field_name, query_name in _FIELD_TO_QUERY.items():
        values = query.get(query_name) or []
        if values and values[0]:
            fields[field_name] = values[0]
    candidate = CaptureCandidate(
        request_url=seed._raw_url,
        fields=fields,
        modified_at=float(seed.last_visit_time),
        source_root="history_seed",
    )
    _candidate_context(candidate)
    return candidate


def history_seed_from_candidate(candidate: CaptureCandidate) -> HistorySeed:
    source_path, context = _candidate_context(candidate)
    if source_path == _ALLOWED_PATH:
        raw_url = candidate.request_url
    else:
        pairs = [(name, value) for name, value in context.items()]
        pairs.extend([("action", "home"), ("scene", "124")])
        raw_url = urlunsplit(("https", _ALLOWED_HOST, _ALLOWED_PATH, urlencode(pairs), ""))
    return HistorySeed(
        _raw_url=raw_url,
        title="authenticated-webview",
        last_visit_time=int(candidate.modified_at),
    )


def _validate_request_context(candidate: CaptureCandidate, url: str) -> None:
    _parsed, query = _validate_history_endpoint(url)
    _source_path, context = _candidate_context(candidate)
    if (query.get("action") or [""])[0] != "getmsg":
        raise ProviderError("HISTORY_SURFACE_UNAVAILABLE", "history_action_not_allowed")
    for query_name, expected in context.items():
        values = query.get(query_name) or []
        if not values or values[0] != expected:
            raise ProviderError("HISTORY_SURFACE_UNAVAILABLE", "history_auth_context_mismatch")


class _RestrictedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        try:
            parsed = urlsplit(newurl)
        except ValueError:
            return None
        if (
            parsed.scheme != _ALLOWED_SCHEME
            or parsed.hostname != _ALLOWED_HOST
            or parsed.path != _ALLOWED_PATH
        ):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_DEFAULT_OPENER = urllib.request.build_opener(_RestrictedRedirectHandler())


def _default_open(request: urllib.request.Request, timeout: float) -> ResponseLike:
    return _DEFAULT_OPENER.open(request, timeout=timeout)  # type: ignore[return-value]


class UrllibHistoryTransport:
    def __init__(
        self,
        candidate: CaptureCandidate,
        *,
        opener: OpenFn = _default_open,
        timeout_seconds: float = 10.0,
        max_response_bytes: int = 4 * 1024 * 1024,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds_out_of_range")
        if max_response_bytes < 1:
            raise ValueError("max_response_bytes_out_of_range")
        self._candidate = candidate
        _source_path, self._context = _candidate_context(candidate)
        self._opener = opener
        self.timeout_seconds = float(timeout_seconds)
        self.max_response_bytes = int(max_response_bytes)
        self._fingerprint = hashlib.sha256(
            "|".join(self._context.get(name, "") for name in sorted(self._context)).encode("utf-8")
        ).hexdigest()[:16]

    def __repr__(self) -> str:
        return f"UrllibHistoryTransport(candidate_fingerprint={self._fingerprint!r})"

    def _request(self, url: str) -> urllib.request.Request:
        _validate_request_context(self._candidate, url)
        return urllib.request.Request(
            url,
            headers={
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "Chrome/120.0 Safari/537.36 MicroMessenger/8.0"
                ),
                "X-Requested-With": "XMLHttpRequest",
                "Referer": self._candidate.request_url,
            },
            method="GET",
        )

    def get(self, url: str) -> bytes:
        request = self._request(url)
        response: ResponseLike | None = None
        try:
            response = self._opener(request, self.timeout_seconds)
            status_code = int(getattr(response, "status", 200) or 200)
            if status_code in {401, 403}:
                raise ProviderError("LOGIN_REQUIRED", "history_auth_rejected")
            final_url = response.geturl()
            parsed = urlsplit(final_url)
            if (
                parsed.scheme != _ALLOWED_SCHEME
                or parsed.hostname != _ALLOWED_HOST
                or parsed.path != _ALLOWED_PATH
            ):
                raise ProviderError("HISTORY_SURFACE_UNAVAILABLE", "history_redirect_not_allowed")
            body = response.read(self.max_response_bytes + 1)
            if len(body) > self.max_response_bytes:
                raise ProviderError("HISTORY_SURFACE_UNAVAILABLE", "history_response_too_large")
            if b"wappoc_appmsgcaptcha" in body.lower():
                raise ProviderError("LOGIN_REQUIRED", "history_auth_challenge")
            return body
        except ProviderError:
            raise
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                raise ProviderError("LOGIN_REQUIRED", "history_auth_rejected") from exc
            raise ProviderError("HISTORY_SURFACE_UNAVAILABLE", "history_http_error") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ProviderError("HISTORY_SURFACE_UNAVAILABLE", "history_transport_unavailable") from exc
        except Exception as exc:
            raise ProviderError("HISTORY_SURFACE_UNAVAILABLE", "history_transport_failed") from exc
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass
