from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    control_token: str
    codespace_name: str | None
    state_dir: Path
    wechat_host: str
    wechat_port: int
    probe_timeout: float

    @classmethod
    def from_env(cls) -> "Settings":
        codespace_name = os.getenv("CODESPACE_NAME") or None
        return cls(
            control_token=os.getenv("WECHAT_CONTROL_TOKEN", ""),
            codespace_name=codespace_name,
            state_dir=Path(os.getenv("WECHAT_STATE_DIR", "state")),
            wechat_host=os.getenv("WECHAT_WEB_HOST", "wechat"),
            wechat_port=int(os.getenv("WECHAT_WEB_PORT", "3001")),
            probe_timeout=float(os.getenv("WECHAT_PROBE_TIMEOUT", "0.5")),
        )
