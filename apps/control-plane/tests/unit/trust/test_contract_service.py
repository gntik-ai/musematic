from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.exceptions import AuthorizationError, ValidationError
from platform.trust.contract_schemas import ComplianceRateQuery
from platform.trust.exceptions import ContractConflictError
from uuid import uuid4

import pytest

from tests.trust_support import (
    build_contract_create,
    build_trust_app,
    build_trust_bundle,
    workspace_member_user,
)


@pytest.mark.asyncio
async def test_contract_service_validates_payload_and_attachment_lifecycle() -> None:
    bundle = build_trust_bundle()
    service = bundle.contract_service
    workspace_id = uuid4()
    actor_id = uuid4()

    created = await service.create_contract(
        build_contract_create(),
        workspace_id,
        actor_id,
    )
    stored = await service.get_contract(created.id, workspace_id=workspace_id)
    assert stored.id == created.id
    assert stored.workspace_id == workspace_id

    invalid_policy = build_contract_create().model_copy(update={"enforcement_policy": "explode"})
    with pytest.raises(ValidationError):
        await service.create_contract(invalid_policy, workspace_id, actor_id)

    conflicting_terms = build_contract_create().model_copy(
        update={"cost_limit_tokens": 0, "expected_outputs": {"records": 1}}
    )
    with pytest.raises(ValidationError):
        await service.create_contract(conflicting_terms, workspace_id, actor_id)

    interaction_id = uuid4()
    execution_id = uuid4()
    await service.attach_to_interaction(interaction_id, created.id, workspace_id=workspace_id)
    await service.attach_to_interaction(interaction_id, created.id, workspace_id=workspace_id)
    await service.attach_to_execution(execution_id, created.id, workspace_id=workspace_id)
    await service.attach_to_execution(execution_id, created.id, workspace_id=workspace_id)

    interaction_snapshot = await service.get_attached_interaction_snapshot(interaction_id)
    execution_snapshot = await service.get_attached_execution_snapshot(execution_id)
    assert interaction_snapshot is not None
    assert execution_snapshot is not None
    assert interaction_snapshot["id"] == str(created.id)
    assert execution_snapshot["cost_limit_tokens"] == 1000

    other = await service.create_contract(
        build_contract_create().model_copy(update={"task_scope": "Alternative scope"}),
        workspace_id,
        actor_id,
    )
    with pytest.raises(ContractConflictError):
        await service.attach_to_interaction(interaction_id, other.id, workspace_id=workspace_id)
    with pytest.raises(ContractConflictError):
        await service.attach_to_execution(execution_id, other.id, workspace_id=workspace_id)

    bundle.repository.execution_states[execution_id] = "running"
    with pytest.raises(ContractConflictError):
        await service.archive_contract(created.id, actor_id, workspace_id=workspace_id)

    bundle.repository.execution_states[execution_id] = "completed"
    await service.archive_contract(created.id, actor_id, workspace_id=workspace_id)
    archived = await service.get_contract(created.id, workspace_id=workspace_id)
    assert archived.is_archived is True


@pytest.mark.asyncio
async def test_contract_service_compliance_rates_and_authorization() -> None:
    bundle = build_trust_bundle()
    service = bundle.contract_service
    workspace_id = uuid4()
    actor_id = uuid4()
    created = await service.create_contract(build_contract_create(), workspace_id, actor_id)
    stored_contract = await bundle.repository.get_contract(created.id)
    assert stored_contract is not None
    snapshot = service._snapshot(stored_contract)
    start = datetime.now(UTC) - timedelta(days=2)
    end = datetime.now(UTC) + timedelta(days=1)

    zero = await service.get_compliance_rates(
        ComplianceRateQuery(
            scope="agent",
            scope_id=created.agent_id,
            start=start,
            end=end,
        ),
        workspace_id,
    )
    assert zero.compliance_rate is None
    assert zero.trend == []

    execution_id = uuid4()
    interaction_id = uuid4()
    bundle.repository.seed_execution_attachment(
        execution_id=execution_id,
        contract_id=stored_contract.id,
        snapshot=snapshot,
        created_at=datetime.now(UTC) - timedelta(hours=4),
        workspace_id=workspace_id,
    )
    bundle.repository.seed_interaction_attachment(
        interaction_id=interaction_id,
        contract_id=stored_contract.id,
        snapshot=snapshot,
        created_at=datetime.now(UTC) - timedelta(hours=2),
        workspace_id=workspace_id,
    )
    await service.record_breach(
        contract=stored_contract,
        target_type="execution",
        target_id=execution_id,
        breached_term="cost_limit",
        observed_value={"token_count": 1500},
        threshold_value={"cost_limit_tokens": 1000},
        enforcement_action="warn",
        enforcement_outcome="success",
    )

    stats = await service.get_compliance_rates(
        ComplianceRateQuery(
            scope="workspace",
            scope_id=str(workspace_id),
            start=start,
            end=end,
        ),
        workspace_id,
    )
    assert stats.total_contract_attached == 2
    assert stats.compliant == 1
    assert stats.warned == 1
    assert stats.compliance_rate == pytest.approx(0.5)
    assert stats.breach_by_term == {"cost_limit": 1}
    assert len(stats.trend) == 1

    app, _bundle = build_trust_app(current_user=workspace_member_user(), bundle=bundle)
    app.state.settings = bundle.settings
    app.state.clients["kafka"] = bundle.producer
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/trust/compliance/rates",
            params={
                "scope": "workspace",
                "scope_id": str(workspace_id),
                "start": start.isoformat(),
                "end": end.isoformat(),
                "bucket": "daily",
            },
        )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_contract_service_workspace_guard_rejects_cross_workspace_access() -> None:
    bundle = build_trust_bundle()
    service = bundle.contract_service
    contract = await service.create_contract(build_contract_create(), uuid4(), uuid4())

    with pytest.raises(AuthorizationError):
        await service.get_contract(contract.id, workspace_id=uuid4())
