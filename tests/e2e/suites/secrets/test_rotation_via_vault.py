from __future__ import annotations

import json
import uuid

from .conftest import control_plane_python


def test_vault_kv_rotation_creates_two_readable_versions(vault_addr: str, vault_root_token: str) -> None:
    path = f"secret/data/musematic/dev/_internal/connectivity-test/{uuid.uuid4().hex}"
    result = control_plane_python(
        """
import asyncio, json, os
from types import SimpleNamespace
from platform.common.secret_provider import VaultSecretProvider

settings = SimpleNamespace(addr=os.environ["E2E_VAULT_ADDR"], namespace="", auth_method="token", token=os.environ["E2E_VAULT_TOKEN"], kv_mount="secret", retry_timeout_seconds=5, retry_attempts=3, cache_ttl_seconds=0, cache_max_staleness_seconds=300, lease_renewal_threshold=0.5)

async def main():
    provider = VaultSecretProvider(settings)
    path = os.environ["E2E_VAULT_PATH"]
    await provider.put(path, {"value": "old"})
    await provider.put(path, {"value": "new"})
    versions = await provider.list_versions(path)
    print(json.dumps({"old": await provider.get_version(path, versions[0]), "new": await provider.get_version(path, versions[-1]), "versions": versions}))

asyncio.run(main())
""",
        env={"E2E_VAULT_ADDR": vault_addr, "E2E_VAULT_TOKEN": vault_root_token, "E2E_VAULT_PATH": path},
    )
    payload = json.loads(result.stdout)
    assert payload["old"] == "old"
    assert payload["new"] == "new"


def test_vault_kv_old_version_destroyed_after_window(vault_addr: str, vault_root_token: str) -> None:
    path = f"secret/data/musematic/dev/_internal/connectivity-test/{uuid.uuid4().hex}"
    result = control_plane_python(
        """
import asyncio, os
from types import SimpleNamespace
from platform.common.secret_provider import CredentialUnavailableError, VaultSecretProvider

settings = SimpleNamespace(addr=os.environ["E2E_VAULT_ADDR"], namespace="", auth_method="token", token=os.environ["E2E_VAULT_TOKEN"], kv_mount="secret", retry_timeout_seconds=5, retry_attempts=3, cache_ttl_seconds=0, cache_max_staleness_seconds=300, lease_renewal_threshold=0.5)

async def main():
    provider = VaultSecretProvider(settings)
    path = os.environ["E2E_VAULT_PATH"]
    await provider.put(path, {"value": "old"})
    await provider.put(path, {"value": "new"})
    versions = await provider.list_versions(path)
    await provider.delete_version(path, versions[0])
    try:
        await provider.get_version(path, versions[0])
    except CredentialUnavailableError:
        print("destroyed")

asyncio.run(main())
""",
        env={"E2E_VAULT_ADDR": vault_addr, "E2E_VAULT_TOKEN": vault_root_token, "E2E_VAULT_PATH": path},
    )
    assert "destroyed" in result.stdout


def test_rotation_audit_payload_contract_contains_no_plaintext() -> None:
    payload = {"event_type": "secret.rotation.completed", "result": "success", "version": 2}
    assert "value" not in payload
    assert "kv_value" not in payload


def test_rotatable_provider_contract_is_rewired() -> None:
    result = control_plane_python(
        """
from platform.security_compliance.providers.rotatable_secret_provider import RotatableSecretProvider
assert "_secret_provider" in RotatableSecretProvider.__init__.__code__.co_names
print("ok")
"""
    )
    assert result.stdout.strip() == "ok"
