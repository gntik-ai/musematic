from __future__ import annotations

import json

from .conftest import control_plane_python


def test_kubernetes_mode_reads_seeded_secret(kubernetes_secret_seed: dict[str, str]) -> None:
    path = "secret/data/musematic/dev/oauth/e2e"
    result = control_plane_python(
        """
import asyncio, os
from types import SimpleNamespace
from platform.common.secret_provider import KubernetesSecretProvider

async def main():
    provider = KubernetesSecretProvider(SimpleNamespace(), namespace=os.environ["E2E_NAMESPACE"])
    print(await provider.get(os.environ["E2E_SECRET_PATH"]))

asyncio.run(main())
""",
        env={"E2E_NAMESPACE": "platform", "E2E_SECRET_PATH": path},
    )
    assert result.stdout.strip() == kubernetes_secret_seed[path]


def test_kubernetes_mode_put_get_round_trip() -> None:
    path = "secret/data/musematic/dev/notifications/e2e-channel"
    result = control_plane_python(
        """
import asyncio, os
from types import SimpleNamespace
from platform.common.secret_provider import KubernetesSecretProvider

async def main():
    provider = KubernetesSecretProvider(SimpleNamespace(), namespace=os.environ["E2E_NAMESPACE"])
    await provider.put(os.environ["E2E_SECRET_PATH"], {"value": "k8s-round-trip"})
    print(await provider.get(os.environ["E2E_SECRET_PATH"]))

asyncio.run(main())
""",
        env={"E2E_NAMESPACE": "platform", "E2E_SECRET_PATH": path},
    )
    assert result.stdout.strip() == "k8s-round-trip"


def test_kubernetes_mode_mapping_contract() -> None:
    result = control_plane_python(
        """
import json
from platform.common.secret_provider import k8s_secret_name_to_vault_path, vault_path_to_k8s_secret_name

path = "secret/data/musematic/dev/model-providers/openai"
name = vault_path_to_k8s_secret_name(path)
print(json.dumps({"name": name, "path": k8s_secret_name_to_vault_path(name)}))
"""
    )
    payload = json.loads(result.stdout)
    assert payload == {
        "name": "musematic-dev-model-providers-openai",
        "path": "secret/data/musematic/dev/model-providers/openai",
    }
