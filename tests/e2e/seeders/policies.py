from __future__ import annotations

from seeders._client import SeedItem, delete_paths, seed_items
from seeders.base import SeederBase, SeedRunSummary


POLICIES = (
    {
        "name": "default-allow",
        "effect": "allow",
        "rules": [{"action": "*", "resource": "*"}],
    },
    {
        "name": "finance-strict",
        "effect": "deny",
        "rules": [{"action": "tool.call", "resource": "secret*"}],
    },
    {
        "name": "test-budget-cap",
        "effect": "deny",
        "rules": [{"action": "execution.start", "condition": "max_tokens > 10000"}],
    },
)


class Seeder(SeederBase):
    name = "policies"

    async def seed(self) -> SeedRunSummary:
        return await seed_items(
            self.name,
            (
                SeedItem(key=policy["name"], path="/api/v1/policies", payload=policy)
                for policy in POLICIES
            ),
        )

    async def reset(self, *, include_baseline: bool = True) -> dict[str, int]:
        if not include_baseline:
            return {self.name: 0}
        return await delete_paths(
            self.name,
            (f"/api/v1/policies/{policy['name']}" for policy in POLICIES),
        )
