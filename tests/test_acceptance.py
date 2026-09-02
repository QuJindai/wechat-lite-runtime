from app.acceptance import evaluate_restart, fetch_runtime_status, main, record_before, safe_snapshot, verify_after


def test_safe_snapshot_keeps_only_non_sensitive_runtime_fields():
    status = {
        "codespace_name": "silver-potato",
        "wechat_web_ready": True,
        "ui_url": "https://silver-potato-3001.app.github.dev",
        "session_storage": {
            "initialized": True,
            "file_count": 23,
            "total_bytes": 4567,
            "unexpected_secret": "must-not-leak",
        },
        "other_secret": "must-not-leak",
    }

    assert safe_snapshot(status) == {
        "codespace_name": "silver-potato",
        "wechat_web_ready": True,
        "ui_url": "https://silver-potato-3001.app.github.dev",
        "session_initialized": True,
        "file_count": 23,
        "total_bytes": 4567,
    }


def test_restart_verdict_is_storage_pass_when_marker_and_profile_survive():
    before = {
        "session_initialized": True,
        "file_count": 20,
        "total_bytes": 4000,
        "wechat_web_ready": True,
    }
    current = {
        "session_initialized": True,
        "file_count": 18,
        "total_bytes": 3900,
        "wechat_web_ready": True,
    }

    result = evaluate_restart(before, current, marker_exists=True)

    assert result["verdict"] == "STORAGE_PASS_AUTH_PENDING"
    assert result["manual_login_check_required"] is True


def test_restart_verdict_is_state_lost_when_marker_disappears():
    before = {"session_initialized": True}
    current = {"session_initialized": True, "wechat_web_ready": True}

    result = evaluate_restart(before, current, marker_exists=False)

    assert result["verdict"] == "STATE_LOST"


def test_restart_verdict_is_runtime_not_ready_when_wechat_port_is_down():
    before = {"session_initialized": True}
    current = {"session_initialized": True, "wechat_web_ready": False}

    result = evaluate_restart(before, current, marker_exists=True)

    assert result["verdict"] == "RUNTIME_NOT_READY"


def test_record_before_persists_safe_snapshot_inside_state_dir(tmp_path):
    result = record_before(
        tmp_path,
        {
            "codespace_name": "silver-potato",
            "wechat_web_ready": True,
            "ui_url": "https://silver-potato-3001.app.github.dev",
            "session_storage": {"initialized": True, "file_count": 5, "total_bytes": 100},
        },
    )

    assert result["verdict"] == "BASELINE_RECORDED"
    marker = tmp_path / ".v0-acceptance-before.json"
    assert marker.exists()
    assert "silver-potato" in marker.read_text(encoding="utf-8")


def test_verify_after_reads_persistent_marker_and_reports_storage_pass(tmp_path):
    record_before(
        tmp_path,
        {
            "codespace_name": "silver-potato",
            "wechat_web_ready": True,
            "ui_url": "https://silver-potato-3001.app.github.dev",
            "session_storage": {"initialized": True, "file_count": 5, "total_bytes": 100},
        },
    )

    result = verify_after(
        tmp_path,
        {
            "codespace_name": "silver-potato",
            "wechat_web_ready": True,
            "ui_url": "https://silver-potato-3001.app.github.dev",
            "session_storage": {"initialized": True, "file_count": 6, "total_bytes": 120},
        },
    )

    assert result["verdict"] == "STORAGE_PASS_AUTH_PENDING"
    assert result["marker_survived"] is True


def test_fetch_runtime_status_sends_bearer_token_to_real_local_http_server():
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen["authorization"] = self.headers.get("Authorization")
            body = json.dumps({
                "codespace_name": "test-space",
                "wechat_web_ready": True,
                "ui_url": "https://test-space-3001.app.github.dev",
                "session_storage": {"initialized": True, "file_count": 1, "total_bytes": 2},
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.handle_request)
    thread.start()
    try:
        host, port = server.server_address
        result = fetch_runtime_status("token-123", f"http://{host}:{port}/v1/runtime/status")
        assert result["codespace_name"] == "test-space"
        assert seen["authorization"] == "Bearer token-123"
    finally:
        thread.join(timeout=2)
        server.server_close()


def test_main_before_records_baseline(monkeypatch, tmp_path, capsys):
    status = {
        "codespace_name": "silver-potato",
        "wechat_web_ready": True,
        "ui_url": "https://silver-potato-3001.app.github.dev",
        "session_storage": {"initialized": True, "file_count": 5, "total_bytes": 100},
    }
    monkeypatch.setenv("WECHAT_CONTROL_TOKEN", "secret")
    monkeypatch.setattr("app.acceptance.fetch_runtime_status", lambda token, url: status)

    exit_code = main(["before", "--state-dir", str(tmp_path)])

    assert exit_code == 0
    assert (tmp_path / ".v0-acceptance-before.json").exists()
    assert "BASELINE_RECORDED" in capsys.readouterr().out


def test_main_after_returns_failure_code_for_lost_state(monkeypatch, tmp_path, capsys):
    status = {
        "codespace_name": "silver-potato",
        "wechat_web_ready": True,
        "ui_url": "https://silver-potato-3001.app.github.dev",
        "session_storage": {"initialized": False, "file_count": 0, "total_bytes": 0},
    }
    monkeypatch.setenv("WECHAT_CONTROL_TOKEN", "secret")
    monkeypatch.setattr("app.acceptance.fetch_runtime_status", lambda token, url: status)

    exit_code = main(["after", "--state-dir", str(tmp_path)])

    assert exit_code == 2
    assert "STATE_LOST" in capsys.readouterr().out


def test_main_uses_persistent_control_token_when_env_secret_is_absent(monkeypatch, tmp_path, capsys):
    status = {
        "codespace_name": "silver-potato",
        "wechat_web_ready": True,
        "ui_url": "https://silver-potato-3001.app.github.dev",
        "session_storage": {"initialized": True, "file_count": 5, "total_bytes": 100},
    }
    monkeypatch.delenv("WECHAT_CONTROL_TOKEN", raising=False)
    (tmp_path / ".control-token").write_text("persisted-secret", encoding="utf-8")
    seen = {}
    def fake_fetch(token, url):
        seen["token"] = token
        return status
    monkeypatch.setattr("app.acceptance.fetch_runtime_status", fake_fetch)

    exit_code = main(["before", "--state-dir", str(tmp_path)])

    assert exit_code == 0
    assert seen["token"] == "persisted-secret"
    assert "BASELINE_RECORDED" in capsys.readouterr().out
