from __future__ import annotations

from datetime import UTC, datetime
from platform.privacy_compliance.cascade_adapters.base import (
    CascadeAdapter,
    CascadePlan,
    CascadeResult,
)
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class Neo4jCascadeAdapter(CascadeAdapter):
    store_name = "neo4j"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._table_cache: dict[str, bool] = {}

    async def dry_run(self, subject_user_id: UUID) -> CascadePlan:
        if not await self._table_exists("graph_nodes"):
            return CascadePlan(self.store_name, 0, {"graph_nodes": 0})
        result = await self.session.execute(
            text("SELECT count(*) FROM graph_nodes WHERE owner_user_id = :uid"),
            {"uid": str(subject_user_id)},
        )
        count = int(result.scalar_one())
        return CascadePlan(self.store_name, count, {"graph_nodes": count})

    async def execute(self, subject_user_id: UUID) -> CascadeResult:
        started = datetime.now(UTC)
        errors: list[str] = []
        counts: dict[str, int] = {"graph_edges": 0, "graph_nodes": 0}
        if not await self._table_exists("graph_nodes"):
            return CascadeResult(
                self.store_name,
                started,
                datetime.now(UTC),
                0,
                counts,
                errors,
            )
        try:
            if await self._table_exists("graph_edges"):
                edge_result = await self.session.execute(
                    text(
                        """
                        DELETE FROM graph_edges
                        WHERE source_node_id IN (
                            SELECT id FROM graph_nodes WHERE owner_user_id = :uid
                        )
                        OR target_node_id IN (
                            SELECT id FROM graph_nodes WHERE owner_user_id = :uid
                        )
                        """
                    ),
                    {"uid": str(subject_user_id)},
                )
                counts["graph_edges"] = _rowcount(edge_result)
            node_result = await self.session.execute(
                text(
                    """
                    DELETE FROM graph_nodes
                    WHERE owner_user_id = :uid
                    """
                ),
                {"uid": str(subject_user_id)},
            )
            counts["graph_nodes"] = _rowcount(node_result)
            await self.session.flush()
        except Exception as exc:
            errors.append(str(exc))
        return CascadeResult(
            self.store_name,
            started,
            datetime.now(UTC),
            sum(counts.values()),
            counts,
            errors,
        )

    async def _table_exists(self, table: str) -> bool:
        if table not in self._table_cache:
            result = await self.session.execute(
                text("SELECT to_regclass(:table_name)"),
                {"table_name": f"public.{table}"},
            )
            self._table_cache[table] = result.scalar_one() is not None
        return self._table_cache[table]


def _rowcount(result: object) -> int:
    value = getattr(result, "rowcount", 0)
    return int(value or 0)
