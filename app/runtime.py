from __future__ import annotations

import socket
from pathlib import Path


def build_codespace_port_url(codespace_name: str | None, port: int) -> str | None:
    if not codespace_name:
        return None
    return f"https://{codespace_name}-{port}.app.github.dev"


def summarize_state_dir(path: Path) -> dict[str, int | bool]:
    if not path.exists():
        return {"initialized": False, "file_count": 0, "total_bytes": 0}

    file_count = 0
    total_bytes = 0
    for item in path.rglob("*"):
        if not item.is_file() or item.name == ".gitignore":
            continue
        file_count += 1
        try:
            total_bytes += item.stat().st_size
        except OSError:
            continue

    return {
        "initialized": file_count > 0,
        "file_count": file_count,
        "total_bytes": total_bytes,
    }


def probe_tcp(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
