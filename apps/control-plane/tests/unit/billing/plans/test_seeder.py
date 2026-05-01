from __future__ import annotations

from platform.billing.plans.seeder import provision_default_plans_if_missing
from typing import Any

import pytest
import sqlalchemy as sa


class _Session:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.flush_count = 0

    async def execute(self, statement: Any) -> None:
        assert isinstance(statement, sa.TextClause)
        self.statements.append(str(statement))

    async def flush(self) -> None:
        self.flush_count += 1


@pytest.mark.asyncio
async def test_default_plan_seeder_uses_idempotent_seed_for_three_plans() -> None:
    session = _Session()

    await provision_default_plans_if_missing(session)  # type: ignore[arg-type]
    await provision_default_plans_if_missing(session)  # second call must be a no-op in SQL

    assert session.flush_count == 2
    assert len(session.statements) == 2
    seed_sql = session.statements[0]
    for slug in ("'free'", "'pro'", "'enterprise'"):
        assert slug in seed_sql
    assert "ON CONFLICT (slug) DO NOTHING" in seed_sql
    assert "ON CONFLICT (plan_id, version) DO NOTHING" in seed_sql
