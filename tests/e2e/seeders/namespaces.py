from __future__ import annotations

from seeders._client import SeedItem, delete_paths, seed_items
from seeders.base import SeederBase, SeedRunSummary


NAMESPACES = (
    {"name": "default", "display_name": "Default"},
    {"name": "test-finance", "display_name": "E2E Finance"},
    {"name": "test-eng", "display_name": "E2E Engineering"},
)


class Seeder(SeederBase):
    name = "namespaces"
    dependencies = ("users",)

    async def seed(self) -> SeedRunSummary:
        return await seed_items(
            self.name,
            (
                SeedItem(key=item["name"], path="/api/v1/namespaces", payload=item)
                for item in NAMESPACES
            ),
        )

    async def reset(self, *, include_baseline: bool = True) -> dict[str, int]:
        paths = (
            f"/api/v1/namespaces/{item['name']}"
            for item in NAMESPACES
            if include_baseline or item["name"] != "default"
        )
        return await delete_paths(self.name, paths)
