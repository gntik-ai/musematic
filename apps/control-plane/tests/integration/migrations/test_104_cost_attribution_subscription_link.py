from __future__ import annotations

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_104_cost_attribution_subscription_link(async_engine: AsyncEngine) -> None:
    async with async_engine.connect() as connection:
        columns = {
            column["name"]: column
            for column in await connection.run_sync(
                lambda sync: inspect(sync).get_columns("cost_attributions")
            )
        }
        indexes = {
            index["name"]
            for index in await connection.run_sync(
                lambda sync: inspect(sync).get_indexes("cost_attributions")
            )
        }

    assert "subscription_id" in columns
    assert columns["subscription_id"]["nullable"] is True
    assert "cost_attributions_subscription_idx" in indexes
