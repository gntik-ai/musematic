from __future__ import annotations

from seeders._client import SeedItem, delete_paths, seed_items
from seeders.base import SeederBase, SeedRunSummary


CERTIFIERS = (
    {"name": "internal-cert", "kind": "internal", "enabled": True},
    {
        "name": "third-party-cert",
        "kind": "http",
        "endpoint": "https://cert.e2e.test/v1/verify",
        "enabled": True,
    },
)


class Seeder(SeederBase):
    name = "certifiers"

    async def seed(self) -> SeedRunSummary:
        return await seed_items(
            self.name,
            (
                SeedItem(
                    key=certifier["name"],
                    path="/api/v1/trust/certifiers",
                    payload=certifier,
                )
                for certifier in CERTIFIERS
            ),
        )

    async def reset(self, *, include_baseline: bool = True) -> dict[str, int]:
        if not include_baseline:
            return {self.name: 0}
        return await delete_paths(
            self.name,
            (
                f"/api/v1/trust/certifiers/{certifier['name']}"
                for certifier in CERTIFIERS
            ),
        )
