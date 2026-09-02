from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

CONTROL_TOKEN_FILE = ".control-token"


def ensure_control_token(state_dir: Path, explicit_token: str | None = None) -> str:
    if explicit_token and explicit_token.strip():
        return explicit_token.strip()

    state_dir.mkdir(parents=True, exist_ok=True)
    token_file = state_dir / CONTROL_TOKEN_FILE

    if token_file.exists():
        token = token_file.read_text(encoding="utf-8").strip()
        if token:
            token_file.chmod(0o600)
            return token

    token = secrets.token_urlsafe(32)
    try:
        fd = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        existing = token_file.read_text(encoding="utf-8").strip()
        if existing:
            token_file.chmod(0o600)
            return existing
        fd = os.open(token_file, os.O_WRONLY | os.O_TRUNC, 0o600)

    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(token + "\n")
    token_file.chmod(0o600)
    return token


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
        state_dir = Path(os.getenv("WECHAT_STATE_DIR", "state"))
        return cls(
            control_token=ensure_control_token(
                state_dir,
                os.getenv("WECHAT_CONTROL_TOKEN"),
            ),
            codespace_name=codespace_name,
            state_dir=state_dir,
            wechat_host=os.getenv("WECHAT_WEB_HOST", "wechat"),
            wechat_port=int(os.getenv("WECHAT_WEB_PORT", "3001")),
            probe_timeout=float(os.getenv("WECHAT_PROBE_TIMEOUT", "0.5")),
        )
