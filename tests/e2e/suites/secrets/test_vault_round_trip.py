from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
import uuid

import pytest

from .conftest import control_plane_python


def _vault_env(vault_addr: str, vault_root_token: str, path: str) -> dict[str, str]:
    return {
        "E2E_VAULT_ADDR": vault_addr,
        "E2E_VAULT_TOKEN": vault_root_token,
        "E2E_VAULT_PATH": path,
    }


def _run_provider(code: str, *, vault_addr: str, vault_root_token: str, path: str) -> str:
    result = control_plane_python(code, env=_vault_env(vault_addr, vault_root_token, path))
    return result.stdout.strip()


@pytest.mark.asyncio
async def test_vault_provider_put_get_round_trip(vault_addr: str, vault_root_token: str) -> None:
    path = f"secret/data/musematic/dev/_internal/connectivity-test/{uuid.uuid4().hex}"
    output = _run_provider(
        """
import asyncio, os
from types import SimpleNamespace
from platform.common.secret_provider import VaultSecretProvider

settings = SimpleNamespace(addr=os.environ["E2E_VAULT_ADDR"], namespace="", auth_method="token", token=os.environ["E2E_VAULT_TOKEN"], kv_mount="secret", retry_timeout_seconds=5, retry_attempts=3, cache_ttl_seconds=60, cache_max_staleness_seconds=300, lease_renewal_threshold=0.5)

async def main():
    provider = VaultSecretProvider(settings)
    await provider.put(os.environ["E2E_VAULT_PATH"], {"value": "round-trip"})
    print(await provider.get(os.environ["E2E_VAULT_PATH"]))

asyncio.run(main())
""",
        vault_addr=vault_addr,
        vault_root_token=vault_root_token,
        path=path,
    )
    assert output == "round-trip"


def test_vault_provider_versions_and_delete(vault_addr: str, vault_root_token: str) -> None:
    path = f"secret/data/musematic/dev/_internal/connectivity-test/{uuid.uuid4().hex}"
    output = _run_provider(
        """
import asyncio, json, os
from types import SimpleNamespace
from platform.common.secret_provider import VaultSecretProvider

settings = SimpleNamespace(addr=os.environ["E2E_VAULT_ADDR"], namespace="", auth_method="token", token=os.environ["E2E_VAULT_TOKEN"], kv_mount="secret", retry_timeout_seconds=5, retry_attempts=3, cache_ttl_seconds=0, cache_max_staleness_seconds=300, lease_renewal_threshold=0.5)

async def main():
    provider = VaultSecretProvider(settings)
    path = os.environ["E2E_VAULT_PATH"]
    await provider.put(path, {"value": "v1"})
    await provider.put(path, {"value": "v2"})
    versions = await provider.list_versions(path)
    await provider.delete_version(path, versions[0])
    print(json.dumps({"versions": versions, "value": await provider.get(path)}))

asyncio.run(main())
""",
        vault_addr=vault_addr,
        vault_root_token=vault_root_token,
        path=path,
    )
    payload = json.loads(output)
    assert payload["versions"][-1] >= 2
    assert payload["value"] == "v2"


def test_vault_provider_health_check(vault_addr: str, vault_root_token: str) -> None:
    path = f"secret/data/musematic/dev/_internal/connectivity-test/{uuid.uuid4().hex}"
    output = _run_provider(
        """
import asyncio, os
from types import SimpleNamespace
from platform.common.secret_provider import VaultSecretProvider

settings = SimpleNamespace(addr=os.environ["E2E_VAULT_ADDR"], namespace="", auth_method="token", token=os.environ["E2E_VAULT_TOKEN"], kv_mount="secret", retry_timeout_seconds=5, retry_attempts=3, cache_ttl_seconds=60, cache_max_staleness_seconds=300, lease_renewal_threshold=0.5)

async def main():
    provider = VaultSecretProvider(settings)
    health = await provider.health_check()
    print(health.status)

asyncio.run(main())
""",
        vault_addr=vault_addr,
        vault_root_token=vault_root_token,
        path=path,
    )
    assert output in {"green", "yellow"}


def test_vault_read_metric_visible_in_prometheus() -> None:
    prometheus = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
    query = urllib.parse.urlencode({"query": "vault_read_total"})
    try:
        with urllib.request.urlopen(f"{prometheus}/api/v1/query?{query}", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        pytest.skip(f"Prometheus is not reachable: {exc}")
    assert payload["status"] == "success"
    assert payload["data"]["resultType"] == "vector"
