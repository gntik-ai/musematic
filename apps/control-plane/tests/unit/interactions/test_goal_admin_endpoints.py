from __future__ import annotations

from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from platform.interactions.dependencies import get_interactions_service
from platform.interactions.router import router
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from tests.auth_support import role_claim
from tests.interactions_support import build_decision_rationale, build_service


def _build_app(
    service, workspace_id: UUID, user_id: UUID, *, roles: list[dict[str, str | None]]
) -> FastAPI:
    app = FastAPI()
    app.state.settings = service.settings
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.include_router(router)

    async def _current_user() -> dict[str, object]:
        return {
            "sub": str(user_id),
            "workspace_id": str(workspace_id),
            "roles": roles,
        }

    async def _service():
        return service

    app.dependency_overrides[get_current_user] = _current_user
    app.dependency_overrides[get_interactions_service] = _service
    return app


@pytest.mark.asyncio
async def test_goal_admin_routes_manage_configs_transitions_and_rationale() -> None:
    service, repo, workspaces, _producer = build_service()
    workspace_id = uuid4()
    admin_id = uuid4()
    goal_id = uuid4()
    workspaces.add_member(workspace_id, admin_id)
    workspaces.set_subscribed_agents(workspace_id, ["ops:*"])
    workspaces.add_goal(workspace_id, goal_id)
    app = _build_app(
        service,
        workspace_id,
        admin_id,
        roles=[role_claim("workspace_admin", workspace_id)],
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        created = await client.put(
            f"/api/v1/workspaces/{workspace_id}/agent-decision-configs/ops%3Aagent",
            json={
                "response_decision_strategy": "keyword",
                "response_decision_config": {"keywords": ["deploy"]},
            },
        )
        updated = await client.put(
            f"/api/v1/workspaces/{workspace_id}/agent-decision-configs/ops%3Aagent",
            json={
                "response_decision_strategy": "keyword",
                "response_decision_config": {"keywords": ["deploy", "rollback"]},
            },
        )
        listed = await client.get(f"/api/v1/workspaces/{workspace_id}/agent-decision-configs")
        message = await client.post(
            f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages",
            headers={"X-Agent-FQN": "ops:agent"},
            json={"content": "deploy now"},
        )
        message_id = UUID(message.json()["id"])
        rationale = build_decision_rationale(
            workspace_id=workspace_id,
            goal_id=goal_id,
            message_id=message_id,
            agent_fqn="ops:agent",
            matched_terms=["deploy"],
            decision="respond",
        )
        repo.decision_rationales[rationale.id] = rationale
        by_message = await client.get(
            f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages/{message_id}/rationale"
        )
        by_goal = await client.get(
            f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}/rationale"
            "?page=1&page_size=10&decision=respond"
        )
        transition = await client.post(
            f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}/transition",
            json={"target_state": "complete", "reason": "done"},
        )
        blocked = await client.post(
            f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages",
            json={"content": "blocked"},
        )

    assert created.status_code == 201
    assert updated.status_code == 200
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert message.status_code == 201
    assert by_message.status_code == 200
    assert by_message.json()["total"] == 1
    assert by_goal.status_code == 200
    assert by_goal.json()["total"] == 1
    assert transition.status_code == 200
    assert transition.json()["new_state"] == "complete"
    assert blocked.status_code == 409


@pytest.mark.asyncio
async def test_goal_admin_routes_require_admin_role() -> None:
    service, _repo, workspaces, _producer = build_service()
    workspace_id = uuid4()
    user_id = uuid4()
    goal_id = uuid4()
    workspaces.add_member(workspace_id, user_id)
    workspaces.add_goal(workspace_id, goal_id)
    app = _build_app(
        service,
        workspace_id,
        user_id,
        roles=[role_claim("viewer", workspace_id)],
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}/transition",
            json={"target_state": "complete"},
        )

    assert response.status_code == 403
