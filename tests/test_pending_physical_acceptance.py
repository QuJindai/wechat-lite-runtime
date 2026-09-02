import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_current_physical_target_is_dspace_seed_and_contains_only_public_identity():
    target = json.loads((ROOT / "config/v1-physical-acceptance-target.json").read_text(encoding="utf-8"))
    assert target == {
        "article_url": "https://mp.weixin.qq.com/s/STxoDJyTsG6rrlZBDcBK9g",
        "account_name": "dSPACE德斯拜思",
        "biz": "Mzg2Mzg3NzgxNw==",
    }


def test_poststart_runs_pending_acceptance_without_terminal_input():
    devcontainer = json.loads((ROOT / ".devcontainer/devcontainer.json").read_text(encoding="utf-8"))
    command = devcontainer["postStartCommand"]
    assert "start-control-api.sh" in command
    assert "run-pending-acceptance.sh" in command

    script = (ROOT / "scripts/run-pending-acceptance.sh").read_text(encoding="utf-8")
    assert "/v1/public-accounts/acceptance" in script
    assert "config/v1-physical-acceptance-target.json" in script
    assert "state/.v1-newest20-acceptance-latest.json" in script
    assert "ensure_control_token" in script
    assert "cat state/.control-token" not in script
