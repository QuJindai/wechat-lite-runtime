from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_control_start_script_supports_explicit_force_restart():
    script = (ROOT / "scripts/start-control-api.sh").read_text(encoding="utf-8")
    assert "WECHAT_CONTROL_FORCE_RESTART" in script


def test_v1_probe_forces_control_api_reload_after_branch_switch():
    script = (ROOT / "scripts/probe-wechat-state.sh").read_text(encoding="utf-8")
    assert "WECHAT_CONTROL_FORCE_RESTART=1 bash scripts/start-control-api.sh" in script
