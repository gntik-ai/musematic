from __future__ import annotations

import asyncio
from platform.common.clients.clickhouse import AsyncClickHouseClient
from platform.common.config import PlatformSettings
from platform.common.config import settings as default_settings
from typing import Final

QUALITY_SCORES_DDL: Final[str] = """
CREATE TABLE IF NOT EXISTS context_quality_scores
(
    agent_fqn String,
    workspace_id UUID,
    assembly_id UUID,
    quality_score Float32,
    quality_subscores JSON,
    token_count UInt32,
    ab_test_id Nullable(UUID),
    ab_test_group Nullable(String),
    created_at DateTime
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(created_at)
ORDER BY (agent_fqn, created_at)
TTL created_at + INTERVAL 90 DAY
"""


async def create_context_quality_scores_table(client: AsyncClickHouseClient) -> None:
    await client.execute_command(QUALITY_SCORES_DDL)


async def run_setup(
    client: AsyncClickHouseClient | None = None,
    settings: PlatformSettings | None = None,
) -> None:
    resolved_settings = settings or default_settings
    resolved_client = client or AsyncClickHouseClient.from_settings(resolved_settings)
    should_close = client is None
    if should_close:
        await resolved_client.connect()
    try:
        await create_context_quality_scores_table(resolved_client)
    finally:
        if should_close:
            await resolved_client.close()


def main() -> None:
    asyncio.run(run_setup())


if __name__ == "__main__":
    main()
