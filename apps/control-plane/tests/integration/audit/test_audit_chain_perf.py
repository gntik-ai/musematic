from __future__ import annotations

import os
import time
from uuid import uuid4

import pytest
from platform.audit.service import AuditChainService

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_AUDIT_CHAIN_PERF") != "1",
    reason="Set RUN_AUDIT_CHAIN_PERF=1 to execute the 1M-entry perf check",
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_audit_chain_verify_one_million_entries_under_sixty_seconds(
    audit_chain_service: AuditChainService,
) -> None:
    for index in range(1_000_000):
        await audit_chain_service.append(
            uuid4(),
            "perf",
            f'{{"index":{index}}}'.encode("utf-8"),
        )

    started = time.perf_counter()
    result = await audit_chain_service.verify()
    elapsed = time.perf_counter() - started

    assert result.valid is True
    assert result.entries_checked == 1_000_000
    assert elapsed <= 60
