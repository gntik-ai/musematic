from __future__ import annotations

from seeders._client import E2ESeederClient, delete_paths
from seeders.base import SeederBase, SeedRunSummary


POLICIES = (
    {
        "name": "default-allow",
        "description": "Permissive baseline policy for E2E flows.",
        "rules": {
            "enforcement_rules": [
                {"id": "allow-all-tools", "action": "allow", "tool_patterns": ["*"]},
            ],
        },
    },
    {
        "name": "finance-strict",
        "description": "Finance policy denying secret-like tool invocations.",
        "rules": {
            "enforcement_rules": [
                {
                    "id": "deny-secret-tools",
                    "action": "deny",
                    "tool_patterns": ["secret*"],
                },
            ],
        },
    },
    {
        "name": "test-budget-cap",
        "description": "E2E policy with a deterministic budget cap.",
        "rules": {
            "budget_limits": {"max_tool_invocations_per_execution": 10000},
        },
    },
)


class Seeder(SeederBase):
    name = "policies"

    async def seed(self) -> SeedRunSummary:
        seeded = 0
        skipped = 0
        async with E2ESeederClient() as client:
            await client.login()
            headers = client._auth_headers()
            workspace_id = await client.workspace_id()
            existing = await client.client.get(
                "/api/v1/policies",
                params={"workspace_id": workspace_id, "page_size": 100},
                headers=headers,
            )
            existing.raise_for_status()
            existing_names = {
                item.get("name")
                for item in existing.json().get("items", [])
                if isinstance(item, dict)
            }
            for policy in POLICIES:
                if policy["name"] in existing_names:
                    skipped += 1
                    continue
                response = await client.client.post(
                    "/api/v1/policies",
                    json={
                        **policy,
                        "scope_type": "workspace",
                        "workspace_id": workspace_id,
                        "change_summary": "Seeded by E2E harness",
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
            (f"/api/v1/policies/{policy['name']}" for policy in POLICIES),
        )
