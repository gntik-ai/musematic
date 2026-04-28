from __future__ import annotations

import json
import tarfile
from datetime import UTC, datetime, timedelta
from io import BytesIO

from seeders._client import E2ESeederClient, delete_paths
from seeders.base import SeederBase, SeedRunSummary


AGENTS = (
    ("default", "seeded-executor", "executor", ["*"]),
    ("test-eng", "seeded-planner", "planner", ["workspace:test-*/agent:*"]),
    ("test-eng", "seeded-orchestrator", "orchestrator", ["workspace:test-*/agent:*"]),
    ("test-finance", "seeded-observer", "observer", ["workspace:test-*/agent:*"]),
    ("test-finance", "seeded-judge", "judge", ["workspace:test-*/agent:*"]),
    ("test-finance", "seeded-enforcer", "enforcer", ["workspace:test-*/agent:*"]),
)


def _payload(namespace: str, local_name: str, role_type: str, patterns: list[str]) -> dict:
    valid_until = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    return {
        "namespace": namespace,
        "local_name": local_name,
        "fqn": f"{namespace}:{local_name}",
        "role_type": role_type,
        "purpose": f"{role_type} seeded for deterministic e2e coverage.".ljust(60, "."),
        "approach": (
            f"{role_type} follows the deterministic mock-LLM and fixture path for e2e checks."
        ).ljust(80, "."),
        "visibility_patterns": patterns,
        "certification": {"status": "active", "valid_until": valid_until},
    }


def _package_bytes(payload: dict) -> bytes:
    manifest = {
        "local_name": payload["local_name"],
        "version": "1.0.0",
        "purpose": payload["purpose"],
        "role_types": [payload["role_type"]],
        "approach": payload["approach"],
        "maturity_level": 1,
        "reasoning_modes": ["deterministic"],
        "tags": ["e2e", payload["namespace"]],
        "display_name": payload["local_name"].replace("-", " ").title(),
    }
    data = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
    buffer = BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        item = tarfile.TarInfo(name="manifest.json")
        item.size = len(data)
        archive.addfile(item, BytesIO(data))
    return buffer.getvalue()


class Seeder(SeederBase):
    name = "agents"
    dependencies = ("namespaces",)

    async def seed(self) -> SeedRunSummary:
        seeded = 0
        skipped = 0
        async with E2ESeederClient() as client:
            await client.login()
            headers = client._auth_headers()
            headers["X-Workspace-ID"] = await client.workspace_id()
            for namespace, local_name, role_type, patterns in AGENTS:
                payload = _payload(namespace, local_name, role_type, patterns)
                response = await client.client.post(
                    "/api/v1/agents/upload",
                    headers=headers,
                    data={"namespace_name": namespace},
                    files={
                        "package": (
                            "agent_package.tar.gz",
                            _package_bytes(payload),
                            "application/gzip",
                        ),
                    },
                )
                if response.status_code not in {200, 201, 409}:
                    response.raise_for_status()
                if response.status_code == 409 or (
                    response.status_code == 200
                    and response.json().get("created") is False
                ):
                    skipped += 1
                else:
                    seeded += 1
        return SeedRunSummary(seeded={self.name: seeded}, skipped={self.name: skipped})

    async def reset(self, *, include_baseline: bool = True) -> dict[str, int]:
        if not include_baseline:
            return {self.name: 0}
        return await delete_paths(
            self.name,
            (
                f"/api/v1/agents/{namespace}:{local_name}"
                for namespace, local_name, _role_type, _patterns in AGENTS
            ),
        )
