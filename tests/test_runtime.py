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

    settings = Settings.from_env()

    assert settings.control_token == "token-123"
    assert settings.codespace_name == "green-cloud"
    assert settings.state_dir == tmp_path
    assert settings.wechat_host == "wechat"
    assert settings.wechat_port == 3001
    assert settings.probe_timeout == 0.25


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
