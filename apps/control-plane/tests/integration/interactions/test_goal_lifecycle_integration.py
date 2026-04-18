from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.accounts.models import SignupSource, User, UserStatus
from platform.common.config import PlatformSettings
from platform.common.models.user import User as PlatformUser
from platform.interactions.goal_lifecycle import GoalAutoCompletionScanner
from platform.interactions.models import WorkspaceGoalDecisionRationale, WorkspaceGoalMessage
from platform.interactions.response_decision import ResponseDecisionEngine
from platform.main import create_app
from platform.workspaces.models import (
    Membership,
    Workspace,
    WorkspaceAgentDecisionConfig,
    WorkspaceGoal,
    WorkspaceGoalState,
    WorkspaceRole,
)
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.accounts_support import build_test_clients, build_test_settings, issue_access_token
from tests.auth_support import RecordingProducer, role_claim


async def _seed_user(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: UUID,
    email: str,
    display_name: str,
) -> None:
    now = datetime.now(UTC)
    async with session_factory() as session:
        session.add(
            User(
                id=user_id,
                email=email,
                display_name=display_name,
                status=UserStatus.active,
                signup_source=SignupSource.self_registration,
                email_verified_at=now,
                activated_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            PlatformUser(
                id=user_id,
                email=email,
                display_name=display_name,
                status="active",
            )
        )
        await session.commit()


async def _seed_goal_bundle(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    owner_id: UUID,
    subscribed_agents: list[str] | None = None,
    auto_complete_timeout_seconds: int | None = None,
    last_message_at: datetime | None = None,
    state: WorkspaceGoalState = WorkspaceGoalState.ready,
) -> tuple[UUID, UUID]:
    async with session_factory() as session:
        workspace = Workspace(
            id=uuid4(),
            name=f"Workspace-{uuid4()}",
            description="Integration workspace",
            owner_id=owner_id,
            status="active",
            is_default=False,
        )
        membership = Membership(
            workspace_id=workspace.id,
            user_id=owner_id,
            role=WorkspaceRole.admin,
        )
        goal = WorkspaceGoal(
            workspace_id=workspace.id,
            created_by=owner_id,
            title="Ship Q4 goals",
            description="Deploy and validate",
            status="open",
            state=state,
            auto_complete_timeout_seconds=auto_complete_timeout_seconds,
            last_message_at=last_message_at,
        )
        session.add(workspace)
        session.add(membership)
        session.add(goal)
        if subscribed_agents is not None:
            from platform.workspaces.models import WorkspaceSettings

            session.add(
                WorkspaceSettings(
                    workspace_id=workspace.id,
                    subscribed_agents=subscribed_agents,
                    subscribed_fleets=[],
                    subscribed_policies=[],
                    subscribed_connectors=[],
                )
            )
        await session.commit()
        return workspace.id, goal.id


def _redis_url(redis_client) -> str:
    return redis_client._url or "redis://localhost:6379"


def _build_app_settings(
    auth_settings: PlatformSettings,
    *,
    database_url: str,
    redis_client,
    feature_goal_auto_complete: bool = False,
) -> PlatformSettings:
    settings = build_test_settings(
        auth_settings,
        database_url=database_url,
        redis_url=_redis_url(redis_client),
    )
    return settings.model_copy(update={"FEATURE_GOAL_AUTO_COMPLETE": feature_goal_auto_complete})


@pytest.mark.integration
@pytest.mark.asyncio
async def test_goal_message_post_transitions_goal_and_persists_rationale(
    monkeypatch: pytest.MonkeyPatch,
    auth_settings: PlatformSettings,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client,
    migrated_database_url: str,
) -> None:
    producer = RecordingProducer()
    settings = _build_app_settings(
        auth_settings,
        database_url=migrated_database_url,
        redis_client=redis_client,
    )
    owner_id = uuid4()
    await _seed_user(
        session_factory,
        user_id=owner_id,
        email="owner-lifecycle@example.com",
        display_name="Owner Lifecycle",
    )
    token = issue_access_token(settings, owner_id, [role_claim("workspace_admin")])

    monkeypatch.setattr(
        "platform.main._build_clients",
        lambda resolved: build_test_clients(redis_client, producer),
    )
    app = create_app(settings=settings)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            created_workspace = await client.post(
                "/api/v1/workspaces",
                headers={"Authorization": f"Bearer {token}"},
                json={"name": "Goal Lifecycle"},
            )
            workspace_id = created_workspace.json()["id"]
            updated_settings = await client.patch(
                f"/api/v1/workspaces/{workspace_id}/settings",
                headers={"Authorization": f"Bearer {token}"},
                json={"subscribed_agents": ["ops:*"]},
            )
            created_goal = await client.post(
                f"/api/v1/workspaces/{workspace_id}/goals",
                headers={"Authorization": f"Bearer {token}"},
                json={"title": "Ship safely", "description": "deploy and rollback if needed"},
            )
            goal_id = created_goal.json()["id"]
            created_config = await client.put(
                f"/api/v1/workspaces/{workspace_id}/agent-decision-configs/ops%3Aagent",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "response_decision_strategy": "keyword",
                    "response_decision_config": {"keywords": ["deploy"], "mode": "any_of"},
                },
            )
            posted = await client.post(
                f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Agent-FQN": "ops:agent",
                },
                json={"content": "please deploy this release"},
            )
            message_id = posted.json()["id"]
            fetched_goal = await client.get(
                f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            rationale = await client.get(
                f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages/{message_id}/rationale",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert updated_settings.status_code == 200
    assert created_config.status_code == 201
    assert posted.status_code == 201
    assert fetched_goal.json()["state"] == "working"
    assert rationale.status_code == 200
    assert rationale.json()["total"] == 1
    assert rationale.json()["items"][0]["agent_fqn"] == "ops:agent"
    assert rationale.json()["items"][0]["decision"] == "respond"
    assert rationale.json()["items"][0]["matched_terms"] == ["deploy"]
    assert {event["event_type"] for event in producer.events} >= {
        "workspace.goal.state_changed",
        "goal.message.posted",
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_completed_goal_blocks_messages_and_preserves_history(
    monkeypatch: pytest.MonkeyPatch,
    auth_settings: PlatformSettings,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client,
    migrated_database_url: str,
) -> None:
    producer = RecordingProducer()
    settings = _build_app_settings(
        auth_settings,
        database_url=migrated_database_url,
        redis_client=redis_client,
    )
    owner_id = uuid4()
    await _seed_user(
        session_factory,
        user_id=owner_id,
        email="owner-complete@example.com",
        display_name="Owner Complete",
    )
    token = issue_access_token(settings, owner_id, [role_claim("workspace_admin")])

    monkeypatch.setattr(
        "platform.main._build_clients",
        lambda resolved: build_test_clients(redis_client, producer),
    )
    app = create_app(settings=settings)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            created_workspace = await client.post(
                "/api/v1/workspaces",
                headers={"Authorization": f"Bearer {token}"},
                json={"name": "Goal Completion"},
            )
            workspace_id = created_workspace.json()["id"]
            created_goal = await client.post(
                f"/api/v1/workspaces/{workspace_id}/goals",
                headers={"Authorization": f"Bearer {token}"},
                json={"title": "Close me", "description": "manual completion"},
            )
            goal_id = created_goal.json()["id"]
            first_message = await client.post(
                f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages",
                headers={"Authorization": f"Bearer {token}"},
                json={"content": "hello"},
            )
            completed = await client.post(
                f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}/transition",
                headers={"Authorization": f"Bearer {token}"},
                json={"target_state": "complete", "reason": "done"},
            )
            repeated = await client.post(
                f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}/transition",
                headers={"Authorization": f"Bearer {token}"},
                json={"target_state": "complete", "reason": "done again"},
            )
            blocked = await client.post(
                f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages",
                headers={"Authorization": f"Bearer {token}"},
                json={"content": "blocked"},
            )
            listed = await client.get(
                f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert first_message.status_code == 201
    assert completed.status_code == 200
    assert completed.json()["new_state"] == "complete"
    assert repeated.status_code == 409
    assert blocked.status_code == 409
    assert listed.status_code == 200
    assert listed.json()["total"] == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_goal_auto_completion_scanner_transitions_elapsed_goals(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    owner_id = uuid4()
    workspace_id, goal_id = await _seed_goal_bundle(
        session_factory,
        owner_id=owner_id,
        auto_complete_timeout_seconds=60,
        last_message_at=datetime.now(UTC) - timedelta(seconds=120),
        state=WorkspaceGoalState.working,
    )
    producer = RecordingProducer()

    async with session_factory() as session:
        scanner = GoalAutoCompletionScanner(producer)
        transitioned = await scanner.scan_and_complete_idle_goals(session)
        await session.commit()

    async with session_factory() as session:
        goal = await session.get(WorkspaceGoal, goal_id)

    assert workspace_id is not None
    assert transitioned == 1
    assert goal is not None
    assert goal.state == WorkspaceGoalState.complete
    assert producer.events[-1]["event_type"] == "workspace.goal.state_changed"
    assert producer.events[-1]["payload"]["automatic"] is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_goal_auto_completion_scanner_is_idempotent(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    owner_id = uuid4()
    _, goal_id = await _seed_goal_bundle(
        session_factory,
        owner_id=owner_id,
        auto_complete_timeout_seconds=30,
        last_message_at=datetime.now(UTC) - timedelta(seconds=90),
        state=WorkspaceGoalState.working,
    )
    producer = RecordingProducer()

    async with session_factory() as session:
        scanner = GoalAutoCompletionScanner(producer)
        first = await scanner.scan_and_complete_idle_goals(session)
        await session.commit()

    async with session_factory() as session:
        scanner = GoalAutoCompletionScanner(producer)
        second = await scanner.scan_and_complete_idle_goals(session)
        await session.commit()
        goal = await session.get(WorkspaceGoal, goal_id)

    state_events = [
        event for event in producer.events if event["event_type"] == "workspace.goal.state_changed"
    ]

    assert first == 1
    assert second == 0
    assert goal is not None
    assert goal.state == WorkspaceGoalState.complete
    assert len(state_events) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_decision_rationale_unique_constraint_is_idempotent(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    owner_id = uuid4()
    workspace_id, goal_id = await _seed_goal_bundle(
        session_factory,
        owner_id=owner_id,
        subscribed_agents=["ops:agent"],
    )

    async with session_factory() as session:
        goal = await session.get(WorkspaceGoal, goal_id)
        assert goal is not None
        message = WorkspaceGoalMessage(
            workspace_id=workspace_id,
            goal_id=goal_id,
            participant_identity="ops:agent",
            content="deploy now",
            interaction_id=None,
            metadata_json={},
        )
        config = WorkspaceAgentDecisionConfig(
            workspace_id=workspace_id,
            agent_fqn="ops:agent",
            response_decision_strategy="keyword",
            response_decision_config={"keywords": ["deploy"], "mode": "any_of"},
        )
        session.add(message)
        session.add(config)
        await session.commit()

        engine = ResponseDecisionEngine(settings=PlatformSettings())
        await engine.evaluate_for_message(
            message_id=message.id,
            goal_id=goal_id,
            workspace_id=workspace_id,
            message_content=message.content,
            goal_context=f"{goal.title}\n{goal.description or ''}",
            subscriptions=[config],
            session=session,
        )
        await engine.evaluate_for_message(
            message_id=message.id,
            goal_id=goal_id,
            workspace_id=workspace_id,
            message_content=message.content,
            goal_context=f"{goal.title}\n{goal.description or ''}",
            subscriptions=[config],
            session=session,
        )
        await session.commit()
        total = await session.scalar(
            select(func.count())
            .select_from(WorkspaceGoalDecisionRationale)
            .where(WorkspaceGoalDecisionRationale.message_id == message.id)
        )

    assert int(total or 0) == 1
