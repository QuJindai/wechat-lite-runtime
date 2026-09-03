from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path

from app.public_accounts import VerifiedAccountIdentity, normalize_account_display_name

_INDEX_FILE = ".public-account-index.json"
_VERSION = 2
_MAX_ENTRIES = 500
_ENTRY_FIELDS = {"account_name", "biz", "provenance", "canonical_seed_url"}
_INDEX_WRITE_LOCK = threading.RLock()


def _normalize_account_name(value: str) -> str:
    return normalize_account_display_name(value).casefold()


class PublicAccountIndex:
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = Path(state_dir)
        self.path = self.state_dir / _INDEX_FILE

    def __repr__(self) -> str:
        return "PublicAccountIndex(path='<private-state>')"

    def _load(self) -> dict[str, VerifiedAccountIdentity]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return {}
        if not isinstance(payload, dict) or payload.get("version") != _VERSION:
            return {}
        accounts = payload.get("accounts")
        if not isinstance(accounts, dict):
            return {}
        clean: dict[str, VerifiedAccountIdentity] = {}
        for key, value in accounts.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                continue
            if set(value) != _ENTRY_FIELDS:
                continue
            try:
                identity = VerifiedAccountIdentity(
                    account_name=str(value["account_name"]),
                    biz=str(value["biz"]),
                    provenance=str(value["provenance"]),
                    canonical_seed_url=str(value["canonical_seed_url"]),
                )
                normalized_key = _normalize_account_name(key)
            except (KeyError, TypeError, ValueError):
                continue
            if normalized_key != _normalize_account_name(identity.account_name):
                continue
            clean[normalized_key] = identity
            if len(clean) >= _MAX_ENTRIES:
                break
        return clean

    def resolve_verified(self, account_name: str) -> VerifiedAccountIdentity | None:
        try:
            key = _normalize_account_name(account_name)
        except ValueError:
            return None
        return self._load().get(key)

    def remember_verified(self, identity: VerifiedAccountIdentity) -> None:
        if not isinstance(identity, VerifiedAccountIdentity):
            raise TypeError("verified_identity_required")
        key = _normalize_account_name(identity.account_name)
        with _INDEX_WRITE_LOCK:
            accounts = self._load()
            if key not in accounts and len(accounts) >= _MAX_ENTRIES:
                oldest_key = sorted(accounts)[0]
                accounts.pop(oldest_key, None)
            accounts[key] = identity
            payload = {
                "version": _VERSION,
                "accounts": {
                    account_key: account_identity.safe_summary()
                    for account_key, account_identity in sorted(accounts.items())
                },
            }

            self.state_dir.mkdir(parents=True, exist_ok=True)
            temp = self.state_dir / (
                f"{_INDEX_FILE}.tmp.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}"
            )
            data = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
                "utf-8"
            )
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
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
