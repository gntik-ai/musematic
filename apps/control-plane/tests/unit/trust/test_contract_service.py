from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.exceptions import AuthorizationError, ValidationError
from platform.execution.exceptions import ExecutionNotFoundError
from platform.interactions.exceptions import InteractionNotFoundError
from platform.trust.contract_schemas import AgentContractUpdate, ComplianceRateQuery
from platform.trust.exceptions import ContractConflictError, ContractNotFoundError
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


@pytest.mark.asyncio
async def test_contract_service_update_listing_and_breach_queries() -> None:
    bundle = build_trust_bundle()
    service = bundle.contract_service
    workspace_id = uuid4()
    actor_id = uuid4()

    first = await service.create_contract(build_contract_create(), workspace_id, actor_id)
    second = await service.create_contract(
        build_contract_create().model_copy(
            update={"agent_id": "agent-2", "task_scope": "Review reconciliation outputs"}
        ),
        workspace_id,
        actor_id,
    )
    await service.archive_contract(second.id, actor_id, workspace_id=workspace_id)

    updated = await service.update_contract(
        first.id,
        AgentContractUpdate(
            enforcement_policy="throttle",
            task_scope="Process escalated reconciliation tasks",
        ),
        actor_id,
        workspace_id=workspace_id,
    )
    active_only = await service.list_contracts(workspace_id, agent_id="agent-1")
    include_archived = await service.list_contracts(workspace_id, include_archived=True)

    stored_contract = await bundle.repository.get_contract(first.id)
    assert stored_contract is not None
    breach = await service.record_breach(
        contract=stored_contract,
        target_type="execution",
        target_id=uuid4(),
        breached_term="cost_limit",
        observed_value={"token_count": 1501},
        threshold_value={"cost_limit_tokens": 1000},
        enforcement_action="throttle",
        enforcement_outcome="success",
    )
    duplicate = await service.record_breach(
        contract=stored_contract,
        target_type="execution",
        target_id=breach.target_id,
        breached_term="cost_limit",
        observed_value={"token_count": 1700},
        threshold_value={"cost_limit_tokens": 1000},
        enforcement_action="throttle",
        enforcement_outcome="success",
    )
    await service.publish_enforcement(
        contract=stored_contract,
        breach_event_id=breach.id,
        target_type="execution",
        target_id=breach.target_id,
        action="throttle",
        outcome="success",
    )
    listed_breaches = await service.list_breach_events(
        first.id,
        workspace_id=workspace_id,
        target_type="execution",
    )

    assert updated.enforcement_policy == "throttle"
    assert active_only.total == 1
    assert include_archived.total == 2
    assert duplicate.id == breach.id
    assert listed_breaches.total == 1
    assert listed_breaches.items[0].id == breach.id
    assert [event["event_type"] for event in bundle.producer.events[-2:]] == [
        "trust.contract.breach",
        "trust.contract.enforcement",
    ]
    assert service._to_uuid_or_none("invalid-uuid") is None

    with pytest.raises(ContractNotFoundError):
        await service.list_breach_events(uuid4(), workspace_id=workspace_id)


@pytest.mark.asyncio
async def test_contract_service_rejects_archived_and_missing_attachment_targets(
    monkeypatch,
) -> None:
    bundle = build_trust_bundle()
    service = bundle.contract_service
    workspace_id = uuid4()
    actor_id = uuid4()

    archived = await service.create_contract(build_contract_create(), workspace_id, actor_id)
    await service.archive_contract(archived.id, actor_id, workspace_id=workspace_id)
    with pytest.raises(ValidationError):
        await service.attach_to_interaction(uuid4(), archived.id, workspace_id=workspace_id)
    with pytest.raises(ValidationError):
        await service.attach_to_execution(uuid4(), archived.id, workspace_id=workspace_id)

    active = await service.create_contract(
        build_contract_create().model_copy(update={"task_scope": "Attachable"}),
        workspace_id,
        actor_id,
    )

    async def _missing_interaction(*args, **kwargs):
        del args, kwargs
        return None

    async def _missing_execution(*args, **kwargs):
        del args, kwargs
        return None

    monkeypatch.setattr(bundle.repository, "attach_contract_to_interaction", _missing_interaction)
    with pytest.raises(InteractionNotFoundError):
        await service.attach_to_interaction(uuid4(), active.id, workspace_id=workspace_id)

    monkeypatch.setattr(bundle.repository, "attach_contract_to_execution", _missing_execution)
    with pytest.raises(ExecutionNotFoundError):
        await service.attach_to_execution(uuid4(), active.id, workspace_id=workspace_id)


@pytest.mark.asyncio
async def test_contract_service_handles_update_race_and_numeric_limit_strings(monkeypatch) -> None:
    bundle = build_trust_bundle()
    service = bundle.contract_service
    workspace_id = uuid4()
    actor_id = uuid4()
    created = await service.create_contract(build_contract_create(), workspace_id, actor_id)
    stored = await bundle.repository.get_contract(created.id)
    assert stored is not None

    async def _missing_update(contract_id, data):
        del contract_id, data
        return None

    monkeypatch.setattr(bundle.repository, "update_contract", _missing_update)

    assert service._to_uuid_or_none(None) is None
    service._validate_contract_payload(
        {
            "enforcement_policy": "warn",
            "cost_limit_tokens": "2",
            "expected_outputs": None,
        }
    )

    with pytest.raises(ContractNotFoundError):
        await service.update_contract(
            created.id,
            AgentContractUpdate(task_scope="updated"),
            actor_id,
            workspace_id=workspace_id,
        )
