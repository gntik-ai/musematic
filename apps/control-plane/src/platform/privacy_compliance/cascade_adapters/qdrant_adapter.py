from __future__ import annotations

from datetime import UTC, datetime
from platform.privacy_compliance.cascade_adapters.base import (
    CascadeAdapter,
    CascadePlan,
    CascadeResult,
)
from uuid import UUID


class QdrantCascadeAdapter(CascadeAdapter):
    store_name = "qdrant"

    def __init__(self, client: object | None, collections: list[str] | None = None) -> None:
        self.client = client
        self.collections = collections or ["*"]

    async def dry_run(self, subject_user_id: UUID) -> CascadePlan:
        del subject_user_id
        return CascadePlan(self.store_name, 0, dict.fromkeys(self.collections, 0))

    async def execute(self, subject_user_id: UUID) -> CascadeResult:
        started = datetime.now(UTC)
        errors: list[str] = []
        counts: dict[str, int] = {}
        for collection in self.collections:
            try:
                delete = getattr(self.client, "delete", None)
                if callable(delete):
                    await delete(
                        collection_name=collection,
                        points_selector={
                            "must": [{"key": "user_id", "match": str(subject_user_id)}]
                        },
                    )
                counts[collection] = 0
            except Exception as exc:
                errors.append(f"{collection}: {exc}")
                counts[collection] = 0
        return CascadeResult(
            self.store_name,
            started,
            datetime.now(UTC),
            sum(counts.values()),
            counts,
            errors,
        )
