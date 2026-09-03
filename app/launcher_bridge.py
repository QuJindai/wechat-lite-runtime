from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Protocol
from urllib.parse import urlsplit

from app.account_bootstrap import LaunchEvidence, build_public_account_home_url


class ResponseLike(Protocol):
    status: int

    def read(self, amount: int = -1) -> bytes: ...

    def close(self) -> None: ...


OpenFn = Callable[[urllib.request.Request, float], ResponseLike]


def _default_open(request: urllib.request.Request, timeout: float) -> ResponseLike:
    return urllib.request.urlopen(request, timeout=timeout)  # type: ignore[return-value]


@dataclass(frozen=True, repr=False)
class SearchEvidence:
    dispatch_attempted: bool
    window_found: bool
    search_submitted: bool
    _account_name: str

    def safe_summary(self) -> dict[str, object]:
        return {
            "dispatch_attempted": self.dispatch_attempted,
            "window_found": self.window_found,
            "search_submitted": self.search_submitted,
            "account_fingerprint": hashlib.sha256(self._account_name.encode("utf-8")).hexdigest()[:16],
        }

    def __repr__(self) -> str:
        return f"SearchEvidence({self.safe_summary()!r})"


class HttpWechatURLLauncher:
    def __init__(
        self,
        control_token: str,
        *,
        endpoint: str = "http://127.0.0.1:8790/open",
        opener: OpenFn = _default_open,
        timeout_seconds: float = 5.0,
    ) -> None:
        token = control_token.strip()
        if not token:
            raise ValueError("control_token_required")
        parsed = urlsplit(endpoint)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "wechat"}
            or parsed.port != 8790
            or parsed.path != "/open"
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("launcher_endpoint_not_allowed")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds_out_of_range")
        self._control_token = token
        self.endpoint = endpoint
        self.search_endpoint = f"http://{parsed.hostname}:8790/search"
        self._opener = opener
        self.timeout_seconds = float(timeout_seconds)

    def __repr__(self) -> str:
        return f"HttpWechatURLLauncher(endpoint={self.endpoint!r})"

    def _post(self, endpoint: str, payload: dict[str, object]) -> dict[str, object] | None:
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._control_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        response: ResponseLike | None = None
        try:
            response = self._opener(request, self.timeout_seconds)
            if int(getattr(response, "status", 200) or 200) != 200:
                return None
            decoded = json.loads(response.read(16 * 1024).decode("utf-8"))
            return decoded if isinstance(decoded, dict) else None
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
            return None
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass

    def _failed_evidence(self, target_url: str) -> LaunchEvidence:
        return LaunchEvidence(
            dispatch_attempted=False,
            exit_code=127,
            secondary_instance_exit=False,
            executable="wechat-container:/usr/bin/wechat",
            _target_url=target_url,
        )

    def open_public_account(self, biz: str) -> LaunchEvidence:
        target_url = build_public_account_home_url(biz)
        payload = self._post(self.endpoint, {"url": target_url})
        if payload is None:
            return self._failed_evidence(target_url)
        exit_code = int(payload.get("exit_code", 127))
        dispatch_attempted = bool(payload.get("dispatch_attempted", exit_code in {0, 255}))
        secondary_instance_exit = bool(payload.get("secondary_instance_exit", exit_code == 255))
        return LaunchEvidence(
            dispatch_attempted=dispatch_attempted,
            exit_code=exit_code,
            secondary_instance_exit=secondary_instance_exit,
            executable="wechat-container:/usr/bin/wechat",
            _target_url=target_url,
        )

    def search_public_account(self, account_name: str) -> SearchEvidence:
        value = account_name.strip()
        if not value or len(value) > 256 or any(ord(char) < 32 for char in value):
            raise ValueError("invalid_account_name")
        payload = self._post(self.search_endpoint, {"account_name": value})
        if payload is None:
            return SearchEvidence(False, False, False, value)
        return SearchEvidence(
            bool(payload.get("dispatch_attempted", False)),
            bool(payload.get("window_found", False)),
            bool(payload.get("search_submitted", False)),
            value,
        )
