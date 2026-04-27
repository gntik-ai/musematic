from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from platform.connectors.exceptions import CredentialUnavailableError
from typing import Any, Literal, Protocol

CANONICAL_SECRET_PATH_RE = re.compile(
    r"^secret/data/musematic/"
    r"(production|staging|dev|test|ci)/"
    r"(oauth|model-providers|notifications|ibor|audit-chain|connectors|accounts)/"
    r"[a-zA-Z0-9_/-]+$"
)

__all__ = [
    "CredentialPolicyDeniedError",
    "CredentialUnavailableError",
    "HealthStatus",
    "InvalidVaultPathError",
    "MockSecretProvider",
    "SecretProvider",
    "validate_secret_path",
]


@dataclass(frozen=True, slots=True)
class HealthStatus:
    status: Literal["green", "yellow", "red"]
    auth_method: str | None = None
    token_expiry_at: datetime | None = None
    lease_count: int | None = None
    recent_failures: list[str] = field(default_factory=list)
    cache_hit_rate: float = 0.0
    error: str | None = None


class CredentialPolicyDeniedError(CredentialUnavailableError):
    status_code = 403

    def __init__(self, credential_key: str) -> None:
        super().__init__(credential_key)
        self.code = "CREDENTIAL_POLICY_DENIED"


class InvalidVaultPathError(ValueError):
    def __init__(self, path: str) -> None:
        super().__init__(f"Vault path does not match the canonical KV v2 scheme: {path}")


class SecretProvider(Protocol):
    async def get(self, path: str, key: str = "value") -> str: ...

    async def put(self, path: str, values: dict[str, str]) -> None: ...

    async def flush_cache(self, path: str | None = None) -> None: ...

    async def delete_version(self, path: str, version: int) -> None: ...

    async def list_versions(self, path: str) -> list[int]: ...

    async def health_check(self) -> HealthStatus: ...


def validate_secret_path(path: str) -> None:
    if not CANONICAL_SECRET_PATH_RE.fullmatch(path):
        raise InvalidVaultPathError(path)


class MockSecretProvider:
    def __init__(
        self,
        settings: Any,
        *,
        secrets_file: str | None = None,
        validate_paths: bool = True,
    ) -> None:
        self.settings = settings
        self.secrets_file = secrets_file or str(
            getattr(getattr(settings, "connectors", object()), "vault_mock_secrets_file", "")
            or ".vault-secrets.json"
        )
        self.validate_paths = validate_paths

    async def get(self, path: str, key: str = "value") -> str:
        if self.validate_paths:
            validate_secret_path(path)
        return await asyncio.to_thread(self._get_sync, path, key)

    async def put(self, path: str, values: dict[str, str]) -> None:
        if self.validate_paths:
            validate_secret_path(path)
        await asyncio.to_thread(self._put_sync, path, values)

    async def flush_cache(self, path: str | None = None) -> None:
        del path

    async def delete_version(self, path: str, version: int) -> None:
        del path, version

    async def list_versions(self, path: str) -> list[int]:
        if self.validate_paths:
            validate_secret_path(path)
        return [1]

    async def health_check(self) -> HealthStatus:
        readable = await asyncio.to_thread(self._has_readable_file)
        if readable:
            return HealthStatus(status="green", auth_method="mock")
        return HealthStatus(
            status="red",
            auth_method="mock",
            error=f"Mock secrets file is not readable: {self.secrets_file}",
        )

    def _get_sync(self, path: str, key: str) -> str:
        for candidate in self._candidate_paths():
            if not candidate.exists():
                continue
            content = json.loads(candidate.read_text(encoding="utf-8"))
            if isinstance(content, dict):
                value = content.get(path)
                if isinstance(value, str):
                    return value
                if isinstance(value, dict):
                    keyed = value.get(key)
                    if isinstance(keyed, str):
                        return keyed
        env_value = os.environ.get(self._env_key(path, key))
        if env_value is not None:
            return env_value
        raise CredentialUnavailableError(key)

    def _put_sync(self, path: str, values: dict[str, str]) -> None:
        candidates = self._candidate_paths()
        target = candidates[0]
        target.parent.mkdir(parents=True, exist_ok=True)
        content: dict[str, Any] = {}
        if target.exists():
            loaded = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                content = loaded
        content[path] = values.get("value") if set(values) == {"value"} else dict(values)
        target.write_text(json.dumps(content, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    def _has_readable_file(self) -> bool:
        for candidate in self._candidate_paths():
            if not candidate.exists():
                continue
            try:
                json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                return False
            return True
        return False

    def _candidate_paths(self) -> list[Path]:
        configured = Path(self.secrets_file)
        candidates = [configured]
        if not configured.is_absolute():
            candidates.insert(0, Path.cwd() / configured)
        return candidates

    @staticmethod
    def _env_key(path: str, key: str) -> str:
        return "CONNECTOR_SECRET_" + "".join(
            char if char.isalnum() else "_" for char in f"{key}_{path}"
        ).upper()
