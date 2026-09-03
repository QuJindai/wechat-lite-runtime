import os
from pathlib import Path

from app.runtime import build_codespace_port_url, summarize_state_dir


def test_build_codespace_port_url():
    assert build_codespace_port_url("silver-potato", 3001) == "https://silver-potato-3001.app.github.dev"


def test_build_codespace_port_url_without_codespace():
    assert build_codespace_port_url(None, 3001) is None


def test_summarize_empty_state_dir(tmp_path: Path):
    (tmp_path / ".gitignore").write_text("*\n", encoding="utf-8")
    assert summarize_state_dir(tmp_path) == {
        "initialized": False,
        "file_count": 0,
        "total_bytes": 0,
    }


def test_summarize_state_dir_with_profile(tmp_path: Path):
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "session.db").write_bytes(b"abc")
    assert summarize_state_dir(tmp_path) == {
        "initialized": True,
        "file_count": 1,
        "total_bytes": 3,
    }


def test_settings_from_env(monkeypatch, tmp_path: Path):
    from app.config import Settings

    monkeypatch.setenv("WECHAT_CONTROL_TOKEN", "token-123")
    monkeypatch.setenv("CODESPACE_NAME", "green-cloud")
    monkeypatch.setenv("WECHAT_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("WECHAT_WEB_HOST", "wechat")
    monkeypatch.setenv("WECHAT_WEB_PORT", "3001")
    monkeypatch.setenv("WECHAT_PROBE_TIMEOUT", "0.25")
    monkeypatch.setenv("WECHAT_LAUNCHER_ENDPOINT", "http://wechat:8790/open")

    settings = Settings.from_env()

    assert settings.control_token == "token-123"
    assert settings.codespace_name == "green-cloud"
    assert settings.state_dir == tmp_path
    assert settings.wechat_host == "wechat"
    assert settings.wechat_port == 3001
    assert settings.probe_timeout == 0.25
    assert settings.launcher_endpoint == "http://wechat:8790/open"


def test_probe_tcp_detects_listening_socket():
    import socket

    from app.runtime import probe_tcp

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    host, port = listener.getsockname()
    try:
        assert probe_tcp(host, port, timeout=0.1) is True
    finally:
        listener.close()


def test_settings_generates_and_reuses_persistent_control_token(monkeypatch, tmp_path: Path):
    from app.config import Settings

    monkeypatch.delenv("WECHAT_CONTROL_TOKEN", raising=False)
    monkeypatch.setenv("WECHAT_STATE_DIR", str(tmp_path))

    first = Settings.from_env()
    second = Settings.from_env()

    assert first.control_token
    assert first.control_token == second.control_token
    token_file = tmp_path / ".control-token"
    assert token_file.read_text(encoding="utf-8").strip() == first.control_token
    if os.name != "nt":
        assert token_file.stat().st_mode & 0o777 == 0o600


def test_explicit_control_token_wins_without_creating_token_file(monkeypatch, tmp_path: Path):
    from app.config import Settings

    monkeypatch.setenv("WECHAT_CONTROL_TOKEN", "explicit-secret")
    monkeypatch.setenv("WECHAT_STATE_DIR", str(tmp_path))

    settings = Settings.from_env()

    assert settings.control_token == "explicit-secret"
    assert not (tmp_path / ".control-token").exists()


def test_runtime_metadata_does_not_initialize_wechat_profile(tmp_path: Path):
    (tmp_path / ".control-token").write_text("secret", encoding="utf-8")
    (tmp_path / ".v0-acceptance-before.json").write_text("{}", encoding="utf-8")

    assert summarize_state_dir(tmp_path) == {
        "initialized": False,
        "file_count": 0,
        "total_bytes": 0,
    }


def test_pending_acceptance_result_does_not_initialize_session_storage(tmp_path: Path):
    (tmp_path / ".v1-newest20-acceptance-latest.json").write_text("{}", encoding="utf-8")
    (tmp_path / ".v1-newest20-acceptance-latest.json.tmp.123").write_text("{}", encoding="utf-8")

    assert summarize_state_dir(tmp_path) == {
        "initialized": False,
        "file_count": 0,
        "total_bytes": 0,
    }
