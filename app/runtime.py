from __future__ import annotations

import socket
from pathlib import Path


def build_codespace_port_url(codespace_name: str | None, port: int) -> str | None:
    if not codespace_name:
        return None
    return f"https://{codespace_name}-{port}.app.github.dev"


RUNTIME_METADATA_FILES = {
    ".gitignore",
    ".control-token",
    ".v0-acceptance-before.json",
    ".public-account-index.json",
    ".v1-newest20-acceptance-latest.json",
}


def is_runtime_metadata(item: Path) -> bool:
    return (
        item.name in RUNTIME_METADATA_FILES
        or item.name.startswith(".public-account-index.json.tmp.")
        or item.name.startswith(".v1-newest20-acceptance-latest.json.tmp.")
    )


def summarize_state_dir(path: Path) -> dict[str, int | bool]:
    if not path.exists():
        return {"initialized": False, "file_count": 0, "total_bytes": 0}

    file_count = 0
    total_bytes = 0
    for item in path.rglob("*"):
        if not item.is_file() or is_runtime_metadata(item):
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
