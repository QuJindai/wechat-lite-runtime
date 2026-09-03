from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from app.account_bootstrap import LaunchEvidence, SubprocessWechatURLLauncher, bootstrap_public_account
from app.credential_scanner import CaptureCandidate, ScanReport


class FakeRunner:
    def __init__(self, exit_code: int = 255) -> None:
        self.exit_code = exit_code
        self.calls: list[tuple[list[str], float]] = []

    def __call__(self, argv: list[str], timeout: float) -> int:
        self.calls.append((argv, timeout))
        return self.exit_code


def test_subprocess_launcher_builds_public_profile_url_and_treats_255_as_dispatch_evidence():
    runner = FakeRunner(exit_code=255)
    launcher = SubprocessWechatURLLauncher(runner=runner, executable="/usr/bin/wechat", timeout_seconds=3.0)

    evidence = launcher.open_public_account("MzA_TEST_BIZ")

    assert evidence.dispatch_attempted is True
    assert evidence.secondary_instance_exit is True
    assert evidence.exit_code == 255
    assert evidence.executable == "/usr/bin/wechat"
    assert len(runner.calls) == 1
    argv, timeout = runner.calls[0]
    assert timeout == 3.0
    assert argv[0] == "/usr/bin/wechat"
    parsed = urlsplit(argv[1])
    query = parse_qs(parsed.query)
    assert parsed.hostname == "mp.weixin.qq.com"
    assert parsed.path == "/mp/profile_ext"
    assert query["action"] == ["home"]
    assert query["__biz"] == ["MzA_TEST_BIZ"]
    assert query["scene"] == ["124"]
    assert parsed.fragment == "wechat_redirect"


def test_launch_evidence_safe_summary_does_not_echo_biz_or_url():
    evidence = LaunchEvidence(
        dispatch_attempted=True,
        exit_code=255,
        secondary_instance_exit=True,
        executable="/usr/bin/wechat",
        _target_url="https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz=BIZ_SECRET",
    )
    rendered = repr(evidence.safe_summary()) + repr(evidence)
    assert "BIZ_SECRET" not in rendered
    assert "mp/profile_ext?" not in rendered
    assert evidence.safe_summary()["target"] == "mp.weixin.qq.com/mp/profile_ext"


def candidate(modified_at: float = 100.0) -> CaptureCandidate:
    return CaptureCandidate(
        request_url="https://mp.weixin.qq.com/mp/profile_ext?action=getmsg&__biz=BIZ_SECRET&uin=UIN_SECRET&key=KEY_SECRET&pass_ticket=PASS_SECRET",
        fields={
            "biz": "BIZ_SECRET",
            "uin": "UIN_SECRET",
            "key": "KEY_SECRET",
            "pass_ticket": "PASS_SECRET",
        },
        modified_at=modified_at,
        source_root=".xwechat/radium/web",
    )


def report(candidates: list[CaptureCandidate], *, truncated: bool = False) -> ScanReport:
    return ScanReport(
        scanned_files=5,
        scanned_bytes=1024,
        roots=[".xwechat/radium/web"],
        candidates=candidates,
        duration_seconds=0.01,
        truncated=truncated,
        truncation_reasons=["file_count_budget"] if truncated else [],
    )


class FakeLauncher:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def open_public_account(self, biz: str) -> LaunchEvidence:
        self.calls.append(biz)
        return LaunchEvidence(
            dispatch_attempted=True,
            exit_code=255,
            secondary_instance_exit=True,
            executable="/usr/bin/wechat",
            _target_url=f"https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz={biz}",
        )


def test_bootstrap_polls_bounded_scanner_until_matching_candidate_is_observed(tmp_path: Path):
    launcher = FakeLauncher()
    scans = [report([]), report([]), report([candidate()])]
    calls = []

    def fake_scan(biz: str, *, roots, **kwargs):
        calls.append((biz, list(roots), kwargs))
        return scans.pop(0)

    result = bootstrap_public_account(
        "BIZ_SECRET",
        state_dir=tmp_path,
        launcher=launcher,
        timeout_seconds=1.0,
        poll_seconds=0.0,
        scan_fn=fake_scan,
    )

    assert launcher.calls == ["BIZ_SECRET"]
    assert result.credential_observed is True
    assert result.candidate_count == 1
    assert result.poll_count == 3
    assert calls[0][1] == [tmp_path / ".xwechat" / "radium" / "web"]
    rendered = repr(result.safe_summary()) + repr(result)
    for secret in ["BIZ_SECRET", "UIN_SECRET", "KEY_SECRET", "PASS_SECRET"]:
        assert secret not in rendered
    assert result.safe_summary()["candidates"][0]["field_names"] == ["biz", "key", "pass_ticket", "uin"]
    assert result.safe_summary()["sensitive_values_returned"] is False


def test_bootstrap_times_out_without_treating_secondary_exit_255_as_success(tmp_path: Path):
    launcher = FakeLauncher()

    def fake_scan(biz: str, *, roots, **kwargs):
        return report([])

    result = bootstrap_public_account(
        "BIZ_SECRET",
        state_dir=tmp_path,
        launcher=launcher,
        timeout_seconds=0.01,
        poll_seconds=0.0,
        scan_fn=fake_scan,
    )

    assert result.launch.dispatch_attempted is True
    assert result.launch.exit_code == 255
    assert result.credential_observed is False
    assert result.candidate_count == 0
    assert result.status == "CREDENTIAL_NOT_OBSERVED"


def test_bootstrap_rejects_invalid_biz_before_launch(tmp_path: Path):
    launcher = FakeLauncher()
    try:
        bootstrap_public_account("", state_dir=tmp_path, launcher=launcher)
    except ValueError as exc:
        assert str(exc) == "invalid_target_biz"
    else:
        raise AssertionError("expected ValueError")
    assert launcher.calls == []
