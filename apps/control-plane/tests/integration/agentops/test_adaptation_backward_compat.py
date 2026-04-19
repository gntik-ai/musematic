from __future__ import annotations

from datetime import UTC, datetime
from platform.agentops.dependencies import get_agentops_service
from platform.agentops.router import router
from platform.agentops.schemas import AdaptationProposalListResponse, AdaptationProposalResponse
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI


class _LegacyAdaptationServiceStub:
    def __init__(self, proposal: AdaptationProposalResponse) -> None:
        self.proposal = proposal

    async def list_adaptations(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        *,
        cursor: str | None = None,
        limit: int = 20,
        status: str | None = None,
    ) -> AdaptationProposalListResponse:
        del cursor, limit, status
        assert agent_fqn == self.proposal.agent_fqn
        assert workspace_id == self.proposal.workspace_id
        return AdaptationProposalListResponse(items=[self.proposal], next_cursor=None)


def _build_app(
    service: _LegacyAdaptationServiceStub, workspace_id: UUID, actor_id: UUID
) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": str(actor_id),
        "workspace_id": str(workspace_id),
    }
    app.dependency_overrides[get_agentops_service] = lambda: service
    return app


@pytest.mark.asyncio
async def test_legacy_adaptation_history_response_preserves_existing_shape() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    now = datetime.now(UTC)
    legacy = AdaptationProposalResponse(
        id=uuid4(),
        workspace_id=workspace_id,
        agent_fqn="finance:agent",
        revision_id=uuid4(),
        status="promoted",
        proposal_details={"adjustments": [{"target": "context_profile"}]},
        signals=[{"rule_type": "quality_trend", "severity": "high"}],
        review_reason="approved before rollout",
        reviewed_by=actor_id,
        reviewed_at=now,
        candidate_revision_id=uuid4(),
        evaluation_run_id=uuid4(),
        completed_at=now,
        completion_note="Legacy promoted proposal",
        created_at=now,
        updated_at=now,
    )
    app = _build_app(_LegacyAdaptationServiceStub(legacy), workspace_id, actor_id)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/agentops/finance:agent/adaptation-history")

    assert response.status_code == 200
    item = response.json()["items"][0]
    legacy_dump = legacy.model_dump(mode="json")
    existing_fields = {
        "id": legacy_dump["id"],
        "workspace_id": legacy_dump["workspace_id"],
        "agent_fqn": legacy_dump["agent_fqn"],
        "revision_id": legacy_dump["revision_id"],
        "status": legacy_dump["status"],
        "proposal_details": legacy_dump["proposal_details"],
        "signals": legacy_dump["signals"],
        "review_reason": legacy_dump["review_reason"],
        "reviewed_by": legacy_dump["reviewed_by"],
        "reviewed_at": legacy_dump["reviewed_at"],
        "candidate_revision_id": legacy_dump["candidate_revision_id"],
        "evaluation_run_id": legacy_dump["evaluation_run_id"],
        "completed_at": legacy_dump["completed_at"],
        "completion_note": legacy_dump["completion_note"],
        "created_at": legacy_dump["created_at"],
        "updated_at": legacy_dump["updated_at"],
    }

    assert {key: item[key] for key in existing_fields} == existing_fields
    for new_key in (
        "expected_improvement",
        "pre_apply_snapshot_key",
        "applied_at",
        "applied_by",
        "rolled_back_at",
        "rolled_back_by",
        "rollback_reason",
        "expires_at",
        "revoked_at",
        "revoked_by",
        "revoke_reason",
        "signal_source",
    ):
        assert item[new_key] is None
