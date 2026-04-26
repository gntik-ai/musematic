from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.exceptions import AuthorizationError
from platform.trust.models import ContentModerationEvent
from platform.trust.routers import moderation_events_router as router
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest


class FakeSession:
    async def execute(self, *_args: object, **_kwargs: object) -> None:
        return None


class FakeRepo:
    def __init__(self, _session: object) -> None:
        self.workspace_id = uuid4()
        self.other_workspace_id = uuid4()
        self.agent_id = uuid4()
        self.events = [
            self._event("block", ["toxicity"], self.workspace_id),
            self._event("flag", ["hate_speech"], self.workspace_id),
            self._event("block", ["toxicity"], self.other_workspace_id),
        ]

    def _event(
        self,
        action: str,
        categories: list[str],
        workspace_id: UUID,
    ) -> ContentModerationEvent:
        event = ContentModerationEvent(
            workspace_id=workspace_id,
            execution_id=uuid4(),
            agent_id=self.agent_id,
            policy_id=uuid4(),
            provider="openai",
            triggered_categories=categories,
            scores={categories[0]: 0.95},
            action_taken=action,
            language_detected="en",
            latency_ms=12,
            audit_chain_ref="audit-ref",
        )
        event.id = uuid4()
        event.created_at = datetime.now(UTC)
        return event

    async def list_moderation_events(
        self,
        filters: dict[str, Any],
    ) -> tuple[list[ContentModerationEvent], int]:
        items = list(self.events)
        if filters.get("workspace_id") is not None:
            items = [item for item in items if item.workspace_id == filters["workspace_id"]]
        if filters.get("agent_id") is not None:
            items = [item for item in items if item.agent_id == filters["agent_id"]]
        if filters.get("action") is not None:
            items = [item for item in items if item.action_taken == filters["action"]]
        if filters.get("since") is not None:
            items = [item for item in items if item.created_at >= filters["since"]]
        if filters.get("until") is not None:
            items = [item for item in items if item.created_at <= filters["until"]]
        return items[: int(filters.get("limit") or 100)], len(items)

    async def aggregate_moderation_events(
        self,
        filters: dict[str, Any],
        group_by: list[str],
    ) -> list[dict[str, Any]]:
        items, _total = await self.list_moderation_events(filters)
        counts: dict[tuple[str | None, ...], int] = {}
        for event in items:
            for category in event.triggered_categories:
                values: list[str | None] = []
                for dimension in group_by:
                    if dimension == "category":
                        values.append(category)
                    if dimension == "action":
                        values.append(event.action_taken)
                key = tuple(values)
                counts[key] = counts.get(key, 0) + 1
        return [
            {**{dimension: key[index] for index, dimension in enumerate(group_by)}, "count": count}
            for key, count in counts.items()
        ]

    async def get_moderation_event(self, event_id: UUID) -> ContentModerationEvent | None:
        return next((item for item in self.events if item.id == event_id), None)


def _request(workspace_id: UUID, *, audit: bool = False) -> Any:
    settings = SimpleNamespace(audit=SimpleNamespace()) if audit else None
    return SimpleNamespace(
        headers={"X-Workspace-ID": str(workspace_id)},
        app=SimpleNamespace(state=SimpleNamespace(clients={}, settings=settings)),
    )


def _user(*roles: str, workspace_id: UUID | None = None) -> dict[str, Any]:
    return {
        "sub": str(uuid4()),
        "workspace_id": str(workspace_id) if workspace_id else None,
        "roles": [{"role": role} for role in roles],
    }


@pytest.mark.asyncio
async def test_event_router_filters_and_cross_workspace_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FakeRepo(FakeSession())
    monkeypatch.setattr(router, "TrustRepository", lambda _session: repo)

    response = await router.list_events(
        _request(repo.workspace_id),
        workspace_id=None,
        agent_id=None,
        category="toxicity",
        action="block",
        since=datetime.now(UTC) - timedelta(minutes=1),
        until=None,
        limit=100,
        current_user=_user("workspace_admin", workspace_id=repo.workspace_id),
        session=FakeSession(),  # type: ignore[arg-type]
    )

    assert response["total"] == 1

    with pytest.raises(AuthorizationError):
        await router.list_events(
            _request(repo.workspace_id),
            workspace_id=repo.other_workspace_id,
            agent_id=None,
            category=None,
            action=None,
            since=None,
            until=None,
            limit=100,
            current_user=_user("workspace_admin", workspace_id=repo.workspace_id),
            session=FakeSession(),  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_event_router_auditor_aggregate_and_detail_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FakeRepo(FakeSession())
    audits: list[dict[str, Any]] = []
    monkeypatch.setattr(router, "TrustRepository", lambda _session: repo)
    monkeypatch.setattr(router, "build_audit_chain_service", lambda **_kwargs: object())

    async def fake_audit_hook(
        _service: object,
        _audit_event_id: object,
        _source: str,
        payload: dict[str, Any],
    ) -> None:
        audits.append(payload)

    monkeypatch.setattr(router, "audit_chain_hook", fake_audit_hook)

    aggregate = await router.aggregate_events(
        _request(repo.workspace_id),
        workspace_id=repo.other_workspace_id,
        action=None,
        since=None,
        until=None,
        group_by="category,action",
        current_user=_user("auditor"),
        session=FakeSession(),  # type: ignore[arg-type]
    )
    detail = await router.get_event(
        repo.events[0].id,
        _request(repo.workspace_id, audit=True),
        current_user=_user("workspace_admin", workspace_id=repo.workspace_id),
        session=FakeSession(),  # type: ignore[arg-type]
    )

    assert aggregate == [{"category": "toxicity", "action": "block", "count": 1}]
    assert detail.audit_chain_ref == "audit-ref"
    assert audits[0]["event_id"] == repo.events[0].id
