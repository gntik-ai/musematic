from __future__ import annotations

from uuid import UUID

from seeders._client import SeedItem, delete_paths, seed_items
from seeders.base import SeederBase, SeedRunSummary


USERS = (
    {
        "id": UUID("00000000-0000-4000-8000-000000000101"),
        "email": "admin@e2e.test",
        "password": "e2e-test-password",
        "display_name": "E2E Platform Admin",
        "roles": ["platform_admin"],
    },
    {
        "id": UUID("00000000-0000-4000-8000-000000000102"),
        "email": "operator1@e2e.test",
        "password": "e2e-test-password",
        "display_name": "E2E Operator One",
        "roles": ["workspace_admin"],
    },
    {
        "id": UUID("00000000-0000-4000-8000-000000000103"),
        "email": "operator2@e2e.test",
        "password": "e2e-test-password",
        "display_name": "E2E Operator Two",
        "roles": ["workspace_admin"],
    },
    {
        "id": UUID("00000000-0000-4000-8000-000000000104"),
        "email": "end_user1@e2e.test",
        "password": "e2e-test-password",
        "display_name": "E2E Workspace Member",
        "roles": ["workspace_member"],
    },
    {
        "id": UUID("00000000-0000-4000-8000-000000000105"),
        "email": "viewer@e2e.test",
        "password": "e2e-test-password",
        "display_name": "E2E Viewer",
        "roles": ["viewer"],
    },
)


class Seeder(SeederBase):
    name = "users"

    async def seed(self) -> SeedRunSummary:
        items = [
            SeedItem(
                key=str(user["email"]),
                path="/api/v1/_e2e/users",
                payload={**user, "id": str(user["id"])},
            )
            for user in USERS
        ]
        return await seed_items(self.name, items, authenticated=False)

    async def reset(self, *, include_baseline: bool = True) -> dict[str, int]:
        if not include_baseline:
            return {self.name: 0}
        return await delete_paths(
            self.name,
            (f"/api/v1/users/{user['id']}" for user in USERS),
        )
