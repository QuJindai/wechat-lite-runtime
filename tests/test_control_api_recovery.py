import app.acceptance as acceptance


def test_main_self_heals_control_api_on_connection_refused(monkeypatch, tmp_path, capsys):
    status = {
        "codespace_name": "musical-guide",
        "wechat_web_ready": True,
        "ui_url": "https://example-3001.app.github.dev",
        "session_storage": {
            "initialized": True,
            "file_count": 2,
            "total_bytes": 10,
        },
    }
    calls = {"fetch": 0, "start": 0}

    def fake_fetch(token, url):
        calls["fetch"] += 1
        if calls["fetch"] == 1:
            raise RuntimeError("control_api_unreachable: [Errno 111] Connection refused")
        return status

    def fake_start():
        calls["start"] += 1
        return {"started": True, "detail": "CONTROL_API_READY=1"}

    monkeypatch.setattr(acceptance, "fetch_runtime_status", fake_fetch)
    monkeypatch.setattr(acceptance, "start_control_api", fake_start)
    monkeypatch.setenv("WECHAT_CONTROL_TOKEN", "secret")

    assert acceptance.main(["before", "--state-dir", str(tmp_path)]) == 0
    assert calls == {"fetch": 2, "start": 1}
    assert "BASELINE_RECORDED" in capsys.readouterr().out


def test_main_does_not_self_heal_http_auth_error(monkeypatch, tmp_path, capsys):
    calls = {"start": 0}

    def fail_fetch(token, url):
        raise RuntimeError("control_api_http_401: unauthorized")

    def fake_start():
        calls["start"] += 1
        return {"started": True, "detail": "unexpected"}

    monkeypatch.setattr(acceptance, "fetch_runtime_status", fail_fetch)
    monkeypatch.setattr(acceptance, "start_control_api", fake_start)
    monkeypatch.setenv("WECHAT_CONTROL_TOKEN", "secret")

    assert acceptance.main(["before", "--state-dir", str(tmp_path)]) == 2
    assert calls["start"] == 0
    assert "CONTROL_API_ERROR" in capsys.readouterr().out
