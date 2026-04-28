from __future__ import annotations

from seeders._client import SeedItem, delete_paths, seed_items
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
        return await seed_items(
            self.name,
            (
                SeedItem(key=fleet["name"], path="/api/v1/fleets", payload=fleet)
                for fleet in FLEETS
            ),
        )

    async def reset(self, *, include_baseline: bool = True) -> dict[str, int]:
        if not include_baseline:
            return {self.name: 0}
        return await delete_paths(
            self.name,
            (f"/api/v1/fleets/{fleet['name']}" for fleet in FLEETS),
        )
