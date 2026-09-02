import os
import time
from pathlib import Path

from app.credential_scanner import scan_credentials


def test_linux_scanner_finds_recent_matching_legacy_and_token_candidates_without_leaking_values(tmp_path: Path):
    web_root = tmp_path / ".xwechat" / "radium" / "web"
    cache = web_root / "profiles" / "multitab_deadbeef" / "Cache" / "Cache_Data"
    cache.mkdir(parents=True)
    now = time.time()

    legacy = (
        b"prefix https://mp.weixin.qq.com/mp/profile_ext?action=getmsg&__biz=TARGET_BIZ"
        b"&uin=UIN_SECRET&key=KEY_SECRET&pass_ticket=PASS_SECRET&offset=0 suffix"
    )
    token = (
        b"https%3A%2F%2Fmp.weixin.qq.com%2Fmp%2Fprofile_ext%3Faction%3Dgetmsg%26__biz%3DTARGET_BIZ"
        b"%26appmsg_token%3DTOKEN_SECRET%26pass_ticket%3DPASS_TOKEN%26poc_sid%3DPOC_SID%26poc_token%3DPOC_TOKEN"
    )
    wrong = b"https://mp.weixin.qq.com/mp/profile_ext?action=getmsg&__biz=OTHER&uin=X&key=Y&pass_ticket=Z"
    (cache / "a.bin").write_bytes(legacy + b"\x00" + wrong)
    (cache / "b.bin").write_bytes(token)
    os.utime(cache / "a.bin", (now, now))
    os.utime(cache / "b.bin", (now + 1, now + 1))

    report = scan_credentials(
        "TARGET_BIZ",
        roots=[web_root],
        since_minutes=60,
        max_files=100,
        max_total_bytes=1024 * 1024,
        max_directories=100,
        max_scan_seconds=5.0,
    )

    assert len(report.candidates) == 2
    summaries = [candidate.safe_summary() for candidate in report.candidates]
    assert summaries[0]["field_names"] == ["appmsg_token", "biz", "pass_ticket", "poc_sid", "poc_token"]
    assert summaries[1]["field_names"] == ["biz", "key", "pass_ticket", "uin"]
    rendered = repr(report.safe_summary()) + repr(report.candidates)
    for secret in ["UIN_SECRET", "KEY_SECRET", "PASS_SECRET", "TOKEN_SECRET", "PASS_TOKEN", "POC_SID", "POC_TOKEN", "TARGET_BIZ"]:
        assert secret not in rendered
    assert report.safe_summary()["sensitive_values_returned"] is False


def test_linux_scanner_ignores_stale_large_and_skipped_media_files(tmp_path: Path):
    web_root = tmp_path / ".xwechat" / "radium" / "web"
    old_dir = web_root / "profiles" / "old"
    video_dir = web_root / "video"
    old_dir.mkdir(parents=True)
    video_dir.mkdir(parents=True)
    payload = b"https://mp.weixin.qq.com/mp/profile_ext?action=getmsg&__biz=TARGET_BIZ&uin=U&key=K&pass_ticket=P"
    stale = old_dir / "stale.bin"
    stale.write_bytes(payload)
    old = time.time() - 7200
    os.utime(stale, (old, old))
    (video_dir / "media.bin").write_bytes(payload)

    report = scan_credentials(
        "TARGET_BIZ",
        roots=[web_root],
        since_minutes=30,
        max_files=100,
        max_total_bytes=1024 * 1024,
        max_directories=100,
        max_scan_seconds=5.0,
    )

    assert report.candidates == []


def test_linux_scanner_bounds_file_count_total_bytes_directories_and_time(tmp_path: Path):
    web_root = tmp_path / ".xwechat" / "radium" / "web"
    root = web_root / "profiles" / "many"
    root.mkdir(parents=True)
    for index in range(8):
        (root / f"{index}.bin").write_bytes(b"x" * 64)

    report = scan_credentials(
        "TARGET_BIZ",
        roots=[web_root],
        since_minutes=60,
        max_files=3,
        max_total_bytes=128,
        max_directories=10,
        max_scan_seconds=5.0,
    )

    assert report.scanned_files <= 3
    assert report.scanned_bytes <= 128
    assert report.truncated is True
    assert set(report.truncation_reasons) & {"file_count_budget", "total_byte_budget"}


def test_linux_scanner_uses_only_supplied_roots_and_safe_root_labels(tmp_path: Path):
    web_root = tmp_path / ".xwechat" / "radium" / "web"
    web_root.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.bin").write_bytes(
        b"https://mp.weixin.qq.com/mp/profile_ext?action=getmsg&__biz=TARGET_BIZ&uin=U&key=K&pass_ticket=P"
    )

    report = scan_credentials(
        "TARGET_BIZ",
        roots=[web_root],
        since_minutes=60,
        max_files=100,
        max_total_bytes=1024 * 1024,
        max_directories=100,
        max_scan_seconds=5.0,
    )

    assert report.candidates == []
    assert report.safe_summary()["roots"] == [".xwechat/radium/web"]
