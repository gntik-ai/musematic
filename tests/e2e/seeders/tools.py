from __future__ import annotations

from seeders._client import SeedItem, delete_paths, seed_items
from seeders.base import SeederBase, SeedRunSummary


TOOLS = (
    {
        "name": "mock-http-tool",
        "kind": "http",
        "endpoint": "http://mock-http-tool.platform.svc.cluster.local/execute",
        "schema": {"type": "object", "properties": {"input": {"type": "string"}}},
    },
    {
        "name": "mock-code-tool",
        "kind": "code",
        "runtime": "python",
        "source": "print('ok')",
    },
)


class Seeder(SeederBase):
    name = "tools"

    async def seed(self) -> SeedRunSummary:
        return await seed_items(
            self.name,
            (
                SeedItem(key=tool["name"], path="/api/v1/tools", payload=tool)
                for tool in TOOLS
            ),
        )

    async def reset(self, *, include_baseline: bool = True) -> dict[str, int]:
        if not include_baseline:
            return {self.name: 0}
        return await delete_paths(
            self.name,
            (f"/api/v1/tools/{tool['name']}" for tool in TOOLS),
        )
