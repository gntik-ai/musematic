from __future__ import annotations

import time
from platform.common.audit_hook import audit_chain_hook
from uuid import uuid4

import pytest


class FakeAuditChainService:
    async def append(self, audit_event_id, source, canonical_payload):
        return {
            "audit_event_id": audit_event_id,
            "source": source,
            "canonical_payload": canonical_payload,
        }


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["auth", "a2a_gateway", "registry", "mcp"])
async def test_audit_chain_hook_is_under_five_milliseconds(source: str) -> None:
    started = time.perf_counter()

    await audit_chain_hook(
        FakeAuditChainService(),
        uuid4(),
        source,
        {"event": "test", "source": source},
    )

    assert (time.perf_counter() - started) * 1000 <= 5
