from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SaltRecord:
    salt: bytes
    salt_version: int
    rotated_at: str | None = None


class SaltHistoryProvider:
    def __init__(
        self,
        *,
        secret_provider: Any | None = None,
        vault_path: str | None = None,
        env_var: str = "PRIVACY_SUBJECT_HASH_SALT",
    ) -> None:
        self.secret_provider = secret_provider
        self.vault_path = vault_path
        self.env_var = env_var
        self._cache: dict[int, SaltRecord] | None = None
        self._current_version = 1

    async def get_current_salt(self) -> bytes:
        records = await self._records()
        return records[self._current_version].salt

    async def get_current_version(self) -> int:
        await self._records()
        return self._current_version

    async def get_salt(self, version: int) -> bytes:
        records = await self._records()
        return records[version].salt

    async def _records(self) -> dict[int, SaltRecord]:
        if self._cache is not None:
            return self._cache

        payload = await self._load_payload()
        current_salt = str(payload.get("current_salt") or os.getenv(self.env_var, "local-dev-salt"))
        current_version = int(payload.get("salt_version") or 1)
        records: dict[int, SaltRecord] = {
            current_version: SaltRecord(
                salt=_decode_salt(current_salt),
                salt_version=current_version,
                rotated_at=payload.get("rotated_at"),
            )
        }
        for item in payload.get("history") or []:
            if not isinstance(item, dict) or "salt" not in item:
                continue
            version = int(item.get("salt_version") or current_version)
            records[version] = SaltRecord(
                salt=_decode_salt(str(item["salt"])),
                salt_version=version,
                rotated_at=item.get("rotated_at"),
            )
        self._cache = records
        self._current_version = current_version
        return records

    async def _load_payload(self) -> dict[str, Any]:
        if self.secret_provider is not None and self.vault_path:
            getter = getattr(self.secret_provider, "get_secret", None) or getattr(
                self.secret_provider, "read_secret", None
            )
            if callable(getter):
                value = await getter(self.vault_path)
                if isinstance(value, dict):
                    return value
                if isinstance(value, str):
                    payload = json.loads(value)
                    if isinstance(payload, dict):
                        return payload
        return {"current_salt": os.getenv(self.env_var, "local-dev-salt"), "salt_version": 1}


def _decode_salt(value: str) -> bytes:
    normalized = value.strip()
    try:
        return bytes.fromhex(normalized)
    except ValueError:
        return normalized.encode("utf-8")
