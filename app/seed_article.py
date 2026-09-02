from __future__ import annotations

import html
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Protocol
from urllib.parse import urlsplit, urlunsplit

_ALLOWED_SCHEME = "https"
_ALLOWED_HOST = "mp.weixin.qq.com"
_MAX_RESPONSE_BYTES = 6 * 1024 * 1024


class ResponseLike(Protocol):
    status: int

    def read(self, amount: int = -1) -> bytes: ...

    def geturl(self) -> str: ...

    def close(self) -> None: ...


OpenFn = Callable[[urllib.request.Request, float], ResponseLike]


class SeedResolutionError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, repr=False)
class SeedIdentity:
    account_name: str
    biz: str
    canonical_url: str

    def safe_summary(self) -> dict[str, object]:
        return {
            "account_name": self.account_name,
            "biz": self.biz,
            "canonical_url": self.canonical_url,
        }

    def __repr__(self) -> str:
        return f"SeedIdentity({self.safe_summary()!r})"


class _RestrictedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        try:
            parsed = urlsplit(newurl)
        except ValueError:
            return None
        if parsed.scheme != _ALLOWED_SCHEME or parsed.hostname != _ALLOWED_HOST:
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_DEFAULT_OPENER = urllib.request.build_opener(_RestrictedRedirectHandler())


def _default_open(request: urllib.request.Request, timeout: float) -> ResponseLike:
    return _DEFAULT_OPENER.open(request, timeout=timeout)  # type: ignore[return-value]


def _canonical_seed_url(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
    except ValueError as exc:
        raise SeedResolutionError("SEED_URL_NOT_ALLOWED") from exc
    if (
        parsed.scheme != _ALLOWED_SCHEME
        or parsed.hostname != _ALLOWED_HOST
        or not (parsed.path == "/s" or parsed.path.startswith("/s/"))
    ):
        raise SeedResolutionError("SEED_URL_NOT_ALLOWED")
    return urlunsplit((_ALLOWED_SCHEME, _ALLOWED_HOST, parsed.path, "", ""))


def _extract_account_name(source: str) -> str | None:
    patterns = (
        r'<meta[^>]+property=["\']og:article:author["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:article:author["\']',
        r'(?:var\s+)?nickname\s*=\s*["\']([^"\']+)["\']',
    )
    for pattern in patterns:
        match = re.search(pattern, source, flags=re.IGNORECASE)
        if match:
            value = html.unescape(match.group(1)).strip()
            if value:
                return value
    return None


def _extract_biz(source: str) -> str | None:
    patterns = (
        r'(?:var\s+)?biz\s*=\s*["\']([A-Za-z0-9_+=\-/]{6,256})["\']',
        r'["\']__biz["\']\s*:\s*["\']([A-Za-z0-9_+=\-/]{6,256})["\']',
    )
    for pattern in patterns:
        match = re.search(pattern, source, flags=re.IGNORECASE)
        if match:
            value = html.unescape(match.group(1)).strip()
            if value:
                return value
    return None


class SeedArticleResolver:
    def __init__(
        self,
        *,
        opener: OpenFn = _default_open,
        timeout_seconds: float = 10.0,
        max_response_bytes: int = _MAX_RESPONSE_BYTES,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds_out_of_range")
        if max_response_bytes < 1:
            raise ValueError("max_response_bytes_out_of_range")
        self._opener = opener
        self.timeout_seconds = float(timeout_seconds)
        self.max_response_bytes = int(max_response_bytes)

    def resolve(self, article_url: str) -> SeedIdentity:
        canonical_url = _canonical_seed_url(article_url)
        request = urllib.request.Request(
            canonical_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "Chrome/120.0 Safari/537.36 MicroMessenger/8.0"
                ),
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "zh-CN,zh;q=0.9",
            },
            method="GET",
        )
        response: ResponseLike | None = None
        try:
            response = self._opener(request, self.timeout_seconds)
            status_code = int(getattr(response, "status", 200) or 200)
            if status_code < 200 or status_code >= 400:
                raise SeedResolutionError("SEED_FETCH_FAILED")
            try:
                final = urlsplit(response.geturl())
            except ValueError as exc:
                raise SeedResolutionError("SEED_REDIRECT_NOT_ALLOWED") from exc
            if final.scheme != _ALLOWED_SCHEME or final.hostname != _ALLOWED_HOST:
                raise SeedResolutionError("SEED_REDIRECT_NOT_ALLOWED")
            body = response.read(self.max_response_bytes + 1)
            if len(body) > self.max_response_bytes:
                raise SeedResolutionError("SEED_RESPONSE_TOO_LARGE")
            source = body.decode("utf-8", errors="replace")
        except SeedResolutionError:
            raise
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
            raise SeedResolutionError("SEED_FETCH_FAILED") from exc
        except Exception as exc:
            raise SeedResolutionError("SEED_FETCH_FAILED") from exc
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass

        account_name = _extract_account_name(source)
        biz = _extract_biz(source)
        if not account_name or not biz:
            raise SeedResolutionError("SEED_IDENTITY_NOT_FOUND")
        return SeedIdentity(
            account_name=account_name,
            biz=biz,
            canonical_url=canonical_url,
        )
