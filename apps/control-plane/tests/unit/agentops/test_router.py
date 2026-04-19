from __future__ import annotations

from platform.agentops import router
from platform.agentops.schemas import (
    AgentHealthConfigUpdateRequest,
    CanaryDecisionRequest,
    CanaryDeploymentCreateRequest,
    GateCheckRequest,
    RegressionAlertResolveRequest,
    RetirementInitiateRequest,
)
from platform.common.exceptions import ValidationError
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_router_direct_handlers_delegate_to_service_methods() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service = SimpleNamespace(
        get_health_config=AsyncMock(return_value="health-config"),
        update_health_config=AsyncMock(return_value="updated-health-config"),
        get_health_score=AsyncMock(return_value="health-score"),
        list_health_history=AsyncMock(return_value="health-history"),
        get_canary=AsyncMock(return_value="canary"),
        promote_canary=AsyncMock(return_value="promoted"),
        list_canaries=AsyncMock(return_value="canaries"),
        get_retirement=AsyncMock(return_value="retirement"),
        get_regression_alert=AsyncMock(return_value="alert"),
        get_proficiency=AsyncMock(return_value="proficiency"),
        list_proficiency_history=AsyncMock(return_value="proficiency-history"),
        query_proficiency_fleet=AsyncMock(return_value="proficiency-fleet"),
        revoke_adaptation_approval=AsyncMock(return_value="revoked"),
        apply_adaptation=AsyncMock(return_value="applied"),
        rollback_adaptation=AsyncMock(return_value="rolled-back"),
        get_adaptation_outcome=AsyncMock(return_value="outcome"),
        get_adaptation_lineage=AsyncMock(return_value="lineage"),
    )

    assert await router.get_health_config(service, workspace_id=workspace_id) == "health-config"
    assert (
        await router.update_health_config(
            AgentHealthConfigUpdateRequest(),
            service,
            workspace_id=workspace_id,
        )
        == "updated-health-config"
    )
    assert await router.get_agent_health("finance:agent", service, workspace_id=workspace_id) == (
        "health-score"
    )
    assert (
        await router.get_agent_health_history(
            "finance:agent",
            service,
            cursor=None,
            limit=20,
            start_time=None,
            end_time=None,
            workspace_id=workspace_id,
        )
        == "health-history"
    )
    assert (
        await router.get_proficiency_fleet(
            service, level_at_or_below=None, level=None, workspace_id=workspace_id
        )
        == "proficiency-fleet"
    )
    assert (
        await router.get_agent_proficiency("finance:agent", service, workspace_id=workspace_id)
        == "proficiency"
    )
    assert (
        await router.get_agent_proficiency_history(
            "finance:agent", service, cursor=None, limit=20, workspace_id=workspace_id
        )
        == "proficiency-history"
    )
    assert await router.get_canary(uuid4(), service) == "canary"
    assert (
        await router.promote_canary(
            uuid4(),
            CanaryDecisionRequest(reason="promote"),
            service,
            current_user={"sub": str(actor_id)},
        )
        == "promoted"
    )
    assert (
        await router.list_canaries(
            "finance:agent",
            service,
            cursor=None,
            limit=20,
            workspace_id=workspace_id,
        )
        == "canaries"
    )
    assert (
        await router.revoke_adaptation_approval(
            uuid4(),
            router.AdaptationRevokeRequest(reason="hold"),
            service,
            current_user={"sub": str(actor_id)},
        )
        == "revoked"
    )
    assert (
        await router.apply_adaptation(
            uuid4(),
            router.AdaptationApplyRequest(reason="ship"),
            service,
            current_user={"sub": str(actor_id)},
        )
        == "applied"
    )
    assert (
        await router.rollback_adaptation(
            uuid4(),
            router.AdaptationRollbackRequest(reason="undo"),
            service,
            current_user={"sub": str(actor_id)},
        )
        == "rolled-back"
    )
    assert await router.get_adaptation_outcome(uuid4(), service) == "outcome"
    assert await router.get_adaptation_lineage(uuid4(), service) == "lineage"
    assert await router.get_retirement(uuid4(), service) == "retirement"
    assert await router.get_regression_alert(uuid4(), service) == "alert"


@pytest.mark.asyncio
async def test_router_scope_and_actor_helpers_cover_validation_paths() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service = SimpleNamespace(
        evaluate_gate_check=AsyncMock(return_value="gate"),
        start_canary=AsyncMock(return_value="started"),
        initiate_retirement=AsyncMock(return_value="initiated"),
        review_adaptation=AsyncMock(return_value="reviewed"),
        resolve_regression_alert=AsyncMock(return_value="resolved"),
    )

    gate_payload = GateCheckRequest(workspace_id=workspace_id, revision_id=uuid4())
    canary_payload = CanaryDeploymentCreateRequest(
        workspace_id=workspace_id,
        production_revision_id=uuid4(),
        canary_revision_id=uuid4(),
        traffic_percentage=10,
        observation_window_hours=1.0,
    )
    retirement_payload = RetirementInitiateRequest(
        workspace_id=workspace_id,
        revision_id=uuid4(),
        reason="manual",
        operator_confirmed=False,
    )

    assert (
        await router.run_gate_check(
            "finance:agent",
            gate_payload,
            service,
            current_user={"sub": str(actor_id)},
            workspace_id=workspace_id,
        )
        == "gate"
    )
    assert (
        await router.start_canary(
            "finance:agent",
            canary_payload,
            service,
            current_user={"sub": str(actor_id)},
            workspace_id=workspace_id,
        )
        == "started"
    )
    assert (
        await router.initiate_retirement(
            "finance:agent",
            retirement_payload,
            service,
            current_user={"sub": str(actor_id)},
            workspace_id=workspace_id,
        )
        == "initiated"
    )
    assert (
        await router.resolve_regression_alert(
            uuid4(),
            RegressionAlertResolveRequest(resolution="resolved", reason="ok"),
            service,
            current_user={"sub": str(actor_id)},
        )
        == "resolved"
    )

    assert router._actor_id({"sub": str(actor_id)}) == actor_id
    assert router._actor_id({"sub": "bad-uuid"}) is None
    assert router._required_actor_id({"sub": str(actor_id)}) == actor_id
    with pytest.raises(ValidationError):
        router._required_actor_id({})
    with pytest.raises(ValidationError):
        router._validate_workspace_scope(uuid4(), uuid4())
    assert router._validate_workspace_scope(workspace_id, workspace_id) == workspace_id
