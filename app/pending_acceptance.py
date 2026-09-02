from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from app.runtime import is_runtime_metadata
from app.wechat_probe import classify_artifact, sanitize_relative_root


@dataclass(frozen=True)
class AcceptanceCacheIdentity:
    target_fingerprint: str
    git_head: str
    session_generation: str

    def to_dict(self) -> dict[str, str]:
        return {
            "target_fingerprint": self.target_fingerprint,
            "git_head": self.git_head,
            "session_generation": self.session_generation,
        }


def _digest_json(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def build_target_fingerprint(target: Mapping[str, object]) -> str:
    return _digest_json(dict(target))


def read_git_head(repo_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(repo_root),
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    head = completed.stdout.strip()
    if completed.returncode != 0 or len(head) != 40 or any(char not in "0123456789abcdefABCDEF" for char in head):
        return "unknown"
    return head.lower()


def build_safe_session_generation(state_dir: Path) -> str:
    state_dir = Path(state_dir)
    artifacts: list[dict[str, object]] = []
    if state_dir.exists():
        for path in state_dir.rglob("*"):
            if not path.is_file() or is_runtime_metadata(path):
                continue
            artifact_class = classify_artifact(path, state_dir)
            if artifact_class is None:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            artifacts.append(
                {
                    "class": artifact_class,
                    "relative_root": sanitize_relative_root(path, state_dir),
                    "size": int(stat.st_size),
                    "mtime_ns": int(stat.st_mtime_ns),
                }
            )
    artifacts.sort(
        key=lambda item: (
            str(item["class"]),
            str(item["relative_root"]),
            int(item["size"]),
            int(item["mtime_ns"]),
        )
    )
    return _digest_json(artifacts)


def can_reuse_pass(
    previous: Mapping[str, object],
    identity: AcceptanceCacheIdentity,
) -> bool:
    response = previous.get("response")
    return bool(
        previous.get("target_fingerprint") == identity.target_fingerprint
        and previous.get("git_head") == identity.git_head
        and previous.get("session_generation") == identity.session_generation
        and isinstance(response, Mapping)
        and response.get("verdict") == "AUTOMATED_GATE_PASS_UI_PENDING"
    )
