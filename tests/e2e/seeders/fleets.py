from __future__ import annotations

from seeders._client import E2ESeederClient, delete_paths
from seeders.base import SeederBase, SeedRunSummary


FLEETS = (
    {
        "name": "test-eng-fleet",
        "leader": "test-eng:seeded-planner",
        "members": ["test-eng:seeded-orchestrator", "default:seeded-executor"],
    },
)


class Seeder(SeederBase):
    name = "fleets"
    dependencies = ("agents",)

    async def seed(self) -> SeedRunSummary:
        seeded = 0
        skipped = 0
        async with E2ESeederClient() as client:
            await client.login()
            headers = client._auth_headers()
            headers["X-Workspace-ID"] = await client.workspace_id()
            existing = await client.client.get("/api/v1/fleets", headers=headers)
            existing.raise_for_status()
            existing_names = {
                item.get("name")
                for item in existing.json().get("items", [])
                if isinstance(item, dict)
            }
            for fleet in FLEETS:
                if fleet["name"] in existing_names:
                    skipped += 1
                    continue
                response = await client.client.post(
                    "/api/v1/fleets",
                    json={
                        "name": fleet["name"],
                        "topology_type": "hierarchical",
                        "quorum_min": 1,
                        "topology_config": {"lead_fqn": fleet["leader"]},
                        "member_fqns": [fleet["leader"], *fleet["members"]],
                    },
                    headers=headers,
                )
                response.raise_for_status()
                seeded += 1
        return SeedRunSummary(seeded={self.name: seeded}, skipped={self.name: skipped})

    async def reset(self, *, include_baseline: bool = True) -> dict[str, int]:
        if not include_baseline:
            return {self.name: 0}
        return await delete_paths(
            self.name,
            (f"/api/v1/fleets/{fleet['name']}" for fleet in FLEETS),
        )
