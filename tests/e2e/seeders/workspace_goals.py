from __future__ import annotations

from seeders._client import E2ESeederClient
from seeders.base import SeederBase, SeedRunSummary


WORKSPACE_NAME = "test-workspace-alpha"
GOALS = (
    ("gid-open-001", "open", "Test open goal"),
    ("gid-inprogress-001", "in_progress", "Test in-progress goal"),
    ("gid-completed-001", "completed", "Test completed goal"),
    ("gid-cancelled-001", "cancelled", "Test cancelled goal"),
)


class Seeder(SeederBase):
    name = "workspace_goals"
    dependencies = ("users",)

    async def seed(self) -> SeedRunSummary:
        seeded = 0
        skipped = 0
        async with E2ESeederClient() as client:
            workspace_response = await client.post(
                "/api/v1/workspaces",
                {"name": WORKSPACE_NAME, "display_name": "E2E Workspace Alpha"},
            )
            workspace = (
                workspace_response.json()
                if workspace_response.content
                else {"id": WORKSPACE_NAME}
            )
            if workspace_response.status_code == 409:
                skipped += 1
            else:
                seeded += 1
            workspace_id = workspace.get("id") or WORKSPACE_NAME
            for gid, state, title in GOALS:
                response = await client.post(
                    f"/api/v1/workspaces/{workspace_id}/goals",
                    {"gid": gid, "state": state, "title": title},
                )
                if response.status_code == 409:
                    skipped += 1
                else:
                    seeded += 1
        return SeedRunSummary(
            seeded={self.name: seeded},
            skipped={self.name: skipped},
        )

    async def reset(self, *, include_baseline: bool = True) -> dict[str, int]:
        if not include_baseline:
            return {self.name: 0}
        async with E2ESeederClient() as client:
            response = await client.delete(f"/api/v1/workspaces/{WORKSPACE_NAME}")
        return {self.name: 0 if response.status_code == 404 else 1}
