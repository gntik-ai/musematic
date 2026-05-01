from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.common.config import settings as default_settings
from platform.common.logging import get_logger
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

LOGGER = get_logger(__name__)


async def record_tenant_enforcement_violation(
    session: AsyncSession,
    *,
    table_name: str,
    query_text: str,
    expected_tenant_id: UUID | None,
    observed_violation: str,
    settings: PlatformSettings | None = None,
) -> bool:
    """Record lenient-mode tenant isolation telemetry."""

    platform_settings = settings or default_settings
    if platform_settings.PLATFORM_TENANT_ENFORCEMENT_LEVEL != "lenient":
        return False

    await session.execute(
        text(
            """
            INSERT INTO tenant_enforcement_violations (
                table_name,
                query_text,
                expected_tenant_id,
                observed_violation
            )
            VALUES (
                :table_name,
                :query_text,
                :expected_tenant_id,
                :observed_violation
            )
            """
        ),
        {
            "table_name": table_name,
            "query_text": query_text,
            "expected_tenant_id": expected_tenant_id,
            "observed_violation": observed_violation,
        },
    )
    await session.flush()
    LOGGER.warning(
        "tenant_enforcement_violation",
        table_name=table_name,
        expected_tenant_id=str(expected_tenant_id) if expected_tenant_id else None,
        observed_violation=observed_violation,
    )
    return True
