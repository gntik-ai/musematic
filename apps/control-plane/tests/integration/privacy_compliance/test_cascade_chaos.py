from __future__ import annotations

from platform.privacy_compliance.cascade_adapters.base import STORE_ORDER
from uuid import uuid4

import pytest

from tests.integration.privacy_compliance.helpers import (
    build_orchestrator,
    populated_stores,
    run_dsr,
)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
@pytest.mark.parametrize("failing_store", STORE_ORDER)
async def test_cascade_chaos_records_store_failure_and_retry_is_idempotent(
    failing_store: str,
) -> None:
    subject_user_id = uuid4()
    stores = populated_stores(subject_user_id)
    orchestrator, _repository, adapters = build_orchestrator(
        stores=stores,
        failures={failing_store: "connection refused"},
    )

    failed = await run_dsr(
        orchestrator,
        dsr_id=uuid4(),
        subject_user_id=subject_user_id,
    )
    for adapter in adapters:
        adapter.failure = None
    retried = await run_dsr(
        orchestrator,
        dsr_id=uuid4(),
        subject_user_id=subject_user_id,
    )

    assert failed.status == "failed"
    assert failing_store in (failed.failure_reason or "")
    assert any(
        entry["store_name"] == failing_store and entry["status"] == "failed"
        for entry in failed.tombstone.cascade_log
    )
    assert retried.status == "completed"
    assert retried.tombstone.entities_deleted[failing_store] > 0
    assert all(str(subject_user_id) not in store for store in stores.values())
    assert all(len(adapter.calls) == 2 for adapter in adapters)
