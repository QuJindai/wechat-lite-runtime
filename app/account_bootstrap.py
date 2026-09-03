from __future__ import annotations

import hashlib
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol
from urllib.parse import urlencode, urlunsplit

from app.credential_scanner import CaptureCandidate, ScanReport, scan_credentials


Runner = Callable[[list[str], float], int]
ScanFn = Callable[..., ScanReport]


def _default_runner(argv: list[str], timeout: float) -> int:
    try:
        completed = subprocess.run(
            argv,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )
        return int(completed.returncode)
    except subprocess.TimeoutExpired:
        return 124
    except OSError:
        return 127


def _validate_biz(biz: str) -> str:
    value = biz.strip()
    if not value or len(value) > 256 or any(char.isspace() for char in value):
        raise ValueError("invalid_target_biz")
    return value


def build_public_account_home_url(biz: str) -> str:
    value = _validate_biz(biz)
    query = urlencode({"action": "home", "__biz": value, "scene": "124"})
    return urlunsplit(("https", "mp.weixin.qq.com", "/mp/profile_ext", query, "wechat_redirect"))


@dataclass(frozen=True, repr=False)
class LaunchEvidence:
    dispatch_attempted: bool
    exit_code: int
    secondary_instance_exit: bool
    executable: str
    _target_url: str

    def safe_summary(self) -> dict[str, object]:
        return {
            "dispatch_attempted": self.dispatch_attempted,
            "exit_code": self.exit_code,
            "secondary_instance_exit": self.secondary_instance_exit,
            "executable": self.executable,
            "target": "mp.weixin.qq.com/mp/profile_ext",
            "target_fingerprint": hashlib.sha256(self._target_url.encode("utf-8")).hexdigest()[:16],
        }

    def __repr__(self) -> str:
        return f"LaunchEvidence({self.safe_summary()!r})"


class WechatURLLauncher(Protocol):
    def open_public_account(self, biz: str) -> LaunchEvidence: ...


class SubprocessWechatURLLauncher:
    def __init__(
        self,
        *,
        runner: Runner = _default_runner,
        executable: str = "/usr/bin/wechat",
        timeout_seconds: float = 3.0,
    ) -> None:
        self.runner = runner
        self.executable = executable
        self.timeout_seconds = timeout_seconds

    def open_public_account(self, biz: str) -> LaunchEvidence:
        target_url = build_public_account_home_url(biz)
        exit_code = self.runner([self.executable, target_url], self.timeout_seconds)
        return LaunchEvidence(
            dispatch_attempted=exit_code in {0, 255},
            exit_code=exit_code,
            secondary_instance_exit=exit_code == 255,
            executable=self.executable,
            _target_url=target_url,
        )


@dataclass(slots=True, repr=False)
class BootstrapResult:
    status: str
    launch: LaunchEvidence
    credential_observed: bool
    candidate_count: int
    poll_count: int
    candidates: list[CaptureCandidate]
    scanner_truncated: bool

    def safe_summary(self) -> dict[str, object]:
        return {
            "status": self.status,
            "launch": self.launch.safe_summary(),
            "credential_observed": self.credential_observed,
            "candidate_count": self.candidate_count,
            "poll_count": self.poll_count,
            "candidates": [candidate.safe_summary() for candidate in self.candidates],
            "scanner_truncated": self.scanner_truncated,
            "sensitive_values_returned": False,
        }

    def __repr__(self) -> str:
        return f"BootstrapResult({self.safe_summary()!r})"


def bootstrap_public_account(
    biz: str,
    *,
    state_dir: Path,
    launcher: WechatURLLauncher,
    timeout_seconds: float = 15.0,
    poll_seconds: float = 0.5,
    scan_fn: ScanFn = scan_credentials,
) -> BootstrapResult:
    target_biz = _validate_biz(biz)
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds_out_of_range")
    if poll_seconds < 0:
        raise ValueError("poll_seconds_out_of_range")

    launch = launcher.open_public_account(target_biz)
    web_root = Path(state_dir) / ".xwechat" / "radium" / "web"
    deadline = time.monotonic() + timeout_seconds
    poll_count = 0
    last_report: ScanReport | None = None

    while True:
        poll_count += 1
        last_report = scan_fn(
            target_biz,
            roots=[web_root],
            since_minutes=60,
            max_files=5000,
            max_total_bytes=512 * 1024 * 1024,
            max_directories=20_000,
            max_scan_seconds=min(5.0, max(0.1, timeout_seconds)),
        )
        if last_report.candidates:
            return BootstrapResult(
                status="CREDENTIAL_OBSERVED",
                launch=launch,
                credential_observed=True,
                candidate_count=len(last_report.candidates),
                poll_count=poll_count,
                candidates=list(last_report.candidates),
                scanner_truncated=last_report.truncated,
            )
        if time.monotonic() >= deadline:
            break
        if poll_seconds:
            time.sleep(min(poll_seconds, max(0.0, deadline - time.monotonic())))

    return BootstrapResult(
        status="CREDENTIAL_NOT_OBSERVED",
        launch=launch,
        credential_observed=False,
        candidate_count=0,
        poll_count=poll_count,
        candidates=[],
        scanner_truncated=bool(last_report and last_report.truncated),
    )
