from __future__ import annotations

from datetime import UTC, datetime
from platform.privacy_compliance.cascade_adapters.base import (
    CascadeAdapter,
    CascadePlan,
    CascadeResult,
)
from uuid import UUID


class S3CascadeAdapter(CascadeAdapter):
    store_name = "s3"

    def __init__(self, client: object | None, buckets: list[str]) -> None:
        self.client = client
        self.buckets = buckets

    async def dry_run(self, subject_user_id: UUID) -> CascadePlan:
        del subject_user_id
        return CascadePlan(self.store_name, 0, dict.fromkeys(self.buckets, 0))

    async def execute(self, subject_user_id: UUID) -> CascadeResult:
        started = datetime.now(UTC)
        counts: dict[str, int] = {}
        errors: list[str] = []
        prefix = f"users/{subject_user_id}/"
        for bucket in self.buckets:
            try:
                delete_matching = getattr(self.client, "delete_objects_matching_prefix", None)
                if callable(delete_matching):
                    counts[bucket] = int(await delete_matching(bucket, prefix))
                else:
                    counts[bucket] = 0
            except Exception as exc:
                errors.append(f"{bucket}: {exc}")
                counts[bucket] = 0
        return CascadeResult(
            self.store_name,
            started,
            datetime.now(UTC),
            sum(counts.values()),
            counts,
            errors,
        )
