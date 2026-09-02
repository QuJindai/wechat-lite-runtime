from __future__ import annotations

import json
import urllib.error
import urllib.request
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
            or parsed.hostname != "127.0.0.1"
            or parsed.port != 8790
            or parsed.path != "/open"
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("launcher_endpoint_must_be_loopback")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds_out_of_range")
        self._control_token = token
        self.endpoint = endpoint
        self._opener = opener
        self.timeout_seconds = float(timeout_seconds)

    def __repr__(self) -> str:
        return f"HttpWechatURLLauncher(endpoint={self.endpoint!r})"

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
        body = json.dumps({"url": target_url}, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=body,
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
                return self._failed_evidence(target_url)
            payload = json.loads(response.read(16 * 1024).decode("utf-8"))
            if not isinstance(payload, dict):
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
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
            return self._failed_evidence(target_url)
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass
