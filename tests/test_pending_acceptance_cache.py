import json
import subprocess
from pathlib import Path

from app.pending_acceptance import (
    AcceptanceCacheIdentity,
    build_safe_session_generation,
    build_target_fingerprint,
    can_reuse_pass,
    read_git_head,
)


def cache_identity(**overrides):
    values = {
        "target_fingerprint": "target-one",
        "git_head": "abc123",
        "session_generation": "session-one",
    }
    values.update(overrides)
    return AcceptanceCacheIdentity(**values)


def passing_record():
    return {
        "target_fingerprint": "target-one",
        "git_head": "abc123",
        "session_generation": "session-one",
        "response": {"verdict": "AUTOMATED_GATE_PASS_UI_PENDING"},
    }


def test_target_fingerprint_is_canonical_and_changes_with_any_target_field():
    target = {"account_name": "dSPACE德斯拜思", "biz": "BIZ", "article_url": "https://mp.weixin.qq.com/s/a"}
    reordered = {"article_url": target["article_url"], "biz": "BIZ", "account_name": target["account_name"]}
    assert build_target_fingerprint(target) == build_target_fingerprint(reordered)
    assert build_target_fingerprint(target) != build_target_fingerprint({**target, "biz": "OTHER"})


def test_read_git_head_returns_exact_head_and_stable_unknown_fallback(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    expected = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert read_git_head(repo_root) == expected
    assert read_git_head(tmp_path) == "unknown"


def test_safe_session_generation_ignores_runtime_metadata_but_tracks_artifacts(tmp_path):
    baseline = build_safe_session_generation(tmp_path)
    for name in [
        ".control-token",
        ".public-account-index.json",
        ".v1-newest20-acceptance-latest.json",
    ]:
        (tmp_path / name).write_text("PRIVATE", encoding="utf-8")
    assert build_safe_session_generation(tmp_path) == baseline

    cookie = tmp_path / "webview" / "User Data" / "Default" / "Cookies"
    cookie.parent.mkdir(parents=True)
    cookie.write_bytes(b"SECRET_COOKIE")
    with_artifact = build_safe_session_generation(tmp_path)
    assert with_artifact != baseline

    (tmp_path / ".v1-newest20-acceptance-latest.json").write_text("changed", encoding="utf-8")
    assert build_safe_session_generation(tmp_path) == with_artifact


def test_safe_session_generation_tracks_real_wechat_webview_credential_surfaces(tmp_path):
    baseline = build_safe_session_generation(tmp_path)
    profile = (
        tmp_path
        / ".xwechat"
        / "radium"
        / "web"
        / "profiles"
        / "multitab_PRIVATE_ACCOUNT"
    )
    leveldb_log = profile / "Local Storage" / "leveldb" / "000003.log"
    leveldb_log.parent.mkdir(parents=True)
    leveldb_log.write_bytes(b"PRIVATE_CREDENTIAL_ONE")
    after_leveldb = build_safe_session_generation(tmp_path)
    assert after_leveldb != baseline

    leveldb_log.write_bytes(b"PRIVATE_CREDENTIAL_TWO_WITH_DIFFERENT_SIZE")
    after_leveldb_change = build_safe_session_generation(tmp_path)
    assert after_leveldb_change != after_leveldb

    history = profile / "History"
    history.write_bytes(b"SQLite format 3\x00PUBLIC_HISTORY_SHAPE")
    assert build_safe_session_generation(tmp_path) != after_leveldb_change


def test_cached_pass_requires_exact_target_code_session_and_verdict():
    previous = passing_record()
    assert can_reuse_pass(previous, cache_identity()) is True
    assert can_reuse_pass(previous, cache_identity(target_fingerprint="other")) is False
    assert can_reuse_pass(previous, cache_identity(git_head="def456")) is False
    assert can_reuse_pass(previous, cache_identity(session_generation="session-two")) is False
    assert can_reuse_pass({**previous, "response": {"verdict": "AUTOMATED_GATE_FAIL"}}, cache_identity()) is False
    assert can_reuse_pass(json.loads(json.dumps(previous)), cache_identity()) is True
