from __future__ import annotations

import json
import os
import unicodedata
from pathlib import Path

_INDEX_FILE = ".public-account-index.json"
_VERSION = 1
_MAX_ENTRIES = 500


def _normalize_account_name(value: str) -> str:
    stripped = value.strip()
    if not stripped or len(stripped) > 256 or any(ord(char) < 32 for char in stripped):
        raise ValueError("invalid_account_name")
    normalized = unicodedata.normalize("NFKC", stripped)
    collapsed = " ".join(normalized.split()).casefold()
    if not collapsed:
        raise ValueError("invalid_account_name")
    return collapsed


def _validate_biz(value: str) -> str:
    stripped = value.strip()
    if not stripped or len(stripped) > 256 or any(char.isspace() for char in stripped):
        raise ValueError("invalid_target_biz")
    return stripped


class PublicAccountIndex:
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = Path(state_dir)
        self.path = self.state_dir / _INDEX_FILE

    def __repr__(self) -> str:
        return "PublicAccountIndex(path='<private-state>')"

    def _load(self) -> dict[str, str]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return {}
        if not isinstance(payload, dict) or payload.get("version") != _VERSION:
            return {}
        accounts = payload.get("accounts")
        if not isinstance(accounts, dict):
            return {}
        clean: dict[str, str] = {}
        for key, value in accounts.items():
            if not isinstance(key, str) or not isinstance(value, str):
                continue
            try:
                clean[_normalize_account_name(key)] = _validate_biz(value)
            except ValueError:
                continue
            if len(clean) >= _MAX_ENTRIES:
                break
        return clean

    def resolve(self, account_name: str) -> str | None:
        try:
            key = _normalize_account_name(account_name)
        except ValueError:
            return None
        return self._load().get(key)

    def remember(self, account_name: str, biz: str) -> None:
        key = _normalize_account_name(account_name)
        value = _validate_biz(biz)
        accounts = self._load()
        if key not in accounts and len(accounts) >= _MAX_ENTRIES:
            oldest_key = sorted(accounts)[0]
            accounts.pop(oldest_key, None)
        accounts[key] = value
        payload = {
            "version": _VERSION,
            "accounts": dict(sorted(accounts.items())),
        }

        self.state_dir.mkdir(parents=True, exist_ok=True)
        temp = self.state_dir / f"{_INDEX_FILE}.tmp.{os.getpid()}"
        data = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, self.path)
            self.path.chmod(0o600)
        finally:
            try:
                temp.unlink()
            except OSError:
                pass
