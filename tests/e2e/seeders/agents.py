from __future__ import annotations

from datetime import UTC, datetime, timedelta

from seeders._client import SeedItem, delete_paths, seed_items
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


class Seeder(SeederBase):
    name = "agents"
    dependencies = ("namespaces",)

    async def seed(self) -> SeedRunSummary:
        return await seed_items(
            self.name,
            (
                SeedItem(
                    key=f"{namespace}:{local_name}",
                    path="/api/v1/agents",
                    payload=_payload(namespace, local_name, role_type, patterns),
                )
                for namespace, local_name, role_type, patterns in AGENTS
            ),
        )

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
