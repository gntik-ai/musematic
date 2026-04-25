from __future__ import annotations

from platform.privacy_compliance.cascade_adapters.base import STORE_ORDER
from uuid import uuid4

import pytest

from tests.integration.privacy_compliance.helpers import (
    Ed25519Signer,
    build_orchestrator,
    populated_stores,
    run_dsr,
)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_erasure_e2e_cascades_all_stores_and_exports_signed_tombstone() -> None:
    subject_user_id = uuid4()
    stores = populated_stores(subject_user_id)
    signer = Ed25519Signer()
    orchestrator, _repository, _adapters = build_orchestrator(
        stores=stores,
        signer=signer,
    )

    result = await run_dsr(
        orchestrator,
        dsr_id=uuid4(),
        subject_user_id=subject_user_id,
    )
    signed = await orchestrator.export_signed(result.tombstone.id)

    assert result.status == "completed"
    assert all(str(subject_user_id) not in store for store in stores.values())
    assert result.tombstone.proof_hash
    assert result.tombstone.entities_deleted == {
        store_name: index + 1
        for index, store_name in enumerate(STORE_ORDER)
    }
    assert [entry["store_name"] for entry in result.tombstone.cascade_log] == list(STORE_ORDER)
    assert signed.signature
    assert signed.key_version == "integration-test-key"
