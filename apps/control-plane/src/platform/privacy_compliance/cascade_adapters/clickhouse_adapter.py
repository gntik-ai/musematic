from __future__ import annotations

from datetime import UTC, datetime
from platform.privacy_compliance.cascade_adapters.base import (
    CascadeAdapter,
    CascadePlan,
    CascadeResult,
)
from uuid import UUID


class ClickHouseCascadeAdapter(CascadeAdapter):
    store_name = "clickhouse"

    def __init__(self, client: object | None, tables: list[str]) -> None:
        self.client = client
        self.tables = tables

    async def dry_run(self, subject_user_id: UUID) -> CascadePlan:
        del subject_user_id
        return CascadePlan(self.store_name, 0, dict.fromkeys(self.tables, 0))

    async def execute(self, subject_user_id: UUID) -> CascadeResult:
        started = datetime.now(UTC)
        errors: list[str] = []
        counts: dict[str, int] = {}
        for table in self.tables:
            try:
                command = getattr(self.client, "execute_command", None)
                if callable(command):
                    await command(
                        f"ALTER TABLE {table} UPDATE is_deleted = 1 WHERE user_id = %(uid)s",
                        {"uid": str(subject_user_id)},
                    )
                counts[table] = 0
            except Exception as exc:
                errors.append(f"{table}: {exc}")
                counts[table] = 0
        return CascadeResult(
            self.store_name,
            started,
            datetime.now(UTC),
            sum(counts.values()),
            counts,
            errors,
        )

