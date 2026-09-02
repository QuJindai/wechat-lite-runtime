from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.public_accounts import canonicalize_mp_url

_ALLOWED_HOST = "mp.weixin.qq.com"
_MAX_RESPONSE_BYTES = 4 * 1024 * 1024


class SeedResolutionError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, repr=False)
class SeedIdentity:
    account_name: str
    biz: str
    canonical_url: str

    def safe_summary(self) -> dict[str, str]:
        return {"account_name": self.account_name, "biz": self.biz, "canonical_url": self.canonical_url}

    def __repr__(self) -> str:
        return f"SeedIdentity({self.safe_summary()!r})"


class ResponseLike(Protocol):
    status: int
    def read(self, amount: int = -1) -> bytes: ...
    def geturl(self) -> str: ...
    def close(self) -> None: ...


OpenFn = Callable[[urllib.request.Request, float], ResponseLike]


class _WeChatOnlyRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        try:
            parsed = urlsplit(newurl)
        except ValueError:
            return None
        if parsed.scheme != "https" or parsed.hostname != _ALLOWED_HOST:
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_DEFAULT_OPENER = urllib.request.build_opener(_WeChatOnlyRedirectHandler())


def _default_open(request: urllib.request.Request, timeout: float) -> ResponseLike:
    return _DEFAULT_OPENER.open(request, timeout=timeout)  # type: ignore[return-value]


class _MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.account_name = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "meta":
            return
        values = {str(key).lower(): str(value or "") for key, value in attrs}
        marker = (values.get("property") or values.get("name") or "").lower()
        if marker in {"og:article:author", "author"} and values.get("content"):
            self.account_name = values["content"].strip()


_BIZ_PATTERNS = (
    re.compile(r'''\bvar\s+biz\s*=\s*["']([^"']+)["']'''),
    re.compile(r'''["']biz["']\s*:\s*["']([^"']+)["']'''),
    re.compile(r'''(?:[?&]|&amp;)__biz=([^&"'<>\s]+)'''),
)
_NICKNAME_PATTERNS = (
    re.compile(r'''\bvar\s+nickname\s*=\s*htmlDecode\(\s*["']([^"']+)["']\s*\)'''),
    re.compile(r'''\bvar\s+nickname\s*=\s*["']([^"']+)["']'''),
    re.compile(r'''["']nickname["']\s*:\s*["']([^"']+)["']'''),
)


def _validate_seed_url(url: str) -> str:
    try:
        parsed = urlsplit(url.strip())
    except ValueError as exc:
        raise SeedResolutionError("SEED_URL_NOT_ALLOWED") from exc
    if parsed.scheme != "https" or parsed.hostname != _ALLOWED_HOST:
        raise SeedResolutionError("SEED_URL_NOT_ALLOWED")
    if not (parsed.path == "/s" or parsed.path.startswith("/s/")):
        raise SeedResolutionError("SEED_URL_NOT_ALLOWED")
    try:
        return canonicalize_mp_url(url)
    except ValueError as exc:
        raise SeedResolutionError("SEED_URL_NOT_ALLOWED") from exc


def _fetch_url(article_url: str) -> str:
    parsed = urlsplit(article_url.strip())
    pairs = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key != "nwr_flag"]
    pairs.append(("nwr_flag", "1"))
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(pairs), ""))


def _extract_identity(page: str, canonical_url: str) -> SeedIdentity:
    parser = _MetaParser()
    try:
        parser.feed(page)
    except Exception:
        pass
    account_name = parser.account_name
    if not account_name:
        for pattern in _NICKNAME_PATTERNS:
            match = pattern.search(page)
            if match:
                account_name = html.unescape(match.group(1)).strip()
                break

    biz = ""
    for pattern in _BIZ_PATTERNS:
        match = pattern.search(page)
        if match:
            biz = html.unescape(match.group(1)).strip()
            break

    if not account_name or not biz:
        raise SeedResolutionError("SEED_IDENTITY_NOT_FOUND")
    return SeedIdentity(account_name=account_name, biz=biz, canonical_url=canonical_url)


def _load_cached_identity(cache_path: Path | None, canonical_url: str) -> SeedIdentity | None:
    if cache_path is None or not cache_path.is_file():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    raw = payload.get(canonical_url)
    if not isinstance(raw, dict):
        return None
    account_name = str(raw.get("account_name") or "").strip()
    biz = str(raw.get("biz") or "").strip()
    if not account_name or not biz:
        return None
    allowed = {"account_name", "biz"}
    if any(str(key) not in allowed for key in raw):
        return None
    return SeedIdentity(account_name=account_name, biz=biz, canonical_url=canonical_url)


class SeedArticleResolver:
    def __init__(self, *, opener: OpenFn = _default_open, timeout_seconds: float = 10.0, max_response_bytes: int = _MAX_RESPONSE_BYTES, cache_path: Path | None = None) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds_out_of_range")
        if max_response_bytes < 1:
            raise ValueError("max_response_bytes_out_of_range")
        self._opener = opener
        self.timeout_seconds = float(timeout_seconds)
        self.max_response_bytes = int(max_response_bytes)
        self.cache_path = Path(cache_path) if cache_path is not None else None

    def resolve(self, article_url: str) -> SeedIdentity:
        canonical_url = _validate_seed_url(article_url)
        cached = _load_cached_identity(self.cache_path, canonical_url)
        if cached is not None:
            return cached

        fetch_url = _fetch_url(article_url)
        request = urllib.request.Request(
            fetch_url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36 MicroMessenger/8.0",
            },
            method="GET",
        )
        response: ResponseLike | None = None
        try:
            response = self._opener(request, self.timeout_seconds)
            final = urlsplit(response.geturl())
            if final.scheme != "https" or final.hostname != _ALLOWED_HOST:
                raise SeedResolutionError("SEED_REDIRECT_NOT_ALLOWED")
            body = response.read(self.max_response_bytes + 1)
            if len(body) > self.max_response_bytes:
                raise SeedResolutionError("SEED_RESPONSE_TOO_LARGE")
            return _extract_identity(body.decode("utf-8", errors="replace"), canonical_url)
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
