from __future__ import annotations

from seeders._client import E2ESeederClient, delete_paths
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
        seeded = 0
        skipped = 0
        async with E2ESeederClient() as client:
            await client.login()
            headers = client._auth_headers()
            headers["X-Workspace-ID"] = await client.workspace_id()
            for tool in TOOLS:
                response = await client.client.put(
                    f"/api/v1/mcp/exposed-tools/e2e:{tool['name']}",
                    json={
                        "mcp_tool_name": tool["name"],
                        "mcp_description": f"E2E deterministic {tool['kind']} tool",
                        "mcp_input_schema": tool["schema"]
                        if tool["kind"] == "http"
                        else {"type": "object", "properties": {}},
                        "is_exposed": True,
                    },
                    headers=headers,
                )
                response.raise_for_status()
                if response.status_code == 200:
                    seeded += 1
                else:
                    skipped += 1
        return SeedRunSummary(seeded={self.name: seeded}, skipped={self.name: skipped})

    async def reset(self, *, include_baseline: bool = True) -> dict[str, int]:
        if not include_baseline:
            return {self.name: 0}
        return await delete_paths(
            self.name,
            (f"/api/v1/mcp/exposed-tools/e2e:{tool['name']}" for tool in TOOLS),
        )
