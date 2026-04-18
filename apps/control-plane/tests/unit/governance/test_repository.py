from __future__ import annotations

from datetime import UTC, datetime
from platform.common.pagination import encode_cursor
from platform.governance.models import ActionType, EnforcementAction, GovernanceVerdict, VerdictType
from platform.governance.repository import GovernanceRepository
from platform.governance.schemas import EnforcementActionListQuery, VerdictListQuery
from uuid import uuid4

import pytest


class ScalarResultStub:
    def __init__(self, items: list[object] | None = None) -> None:
        self._items = list(items or [])

    def unique(self) -> ScalarResultStub:
        return self

    def all(self) -> list[object]:
        return list(self._items)


class ExecuteResultStub:
    def __init__(
        self,
        *,
        scalar_one: object | None = None,
        scalars_all: list[object] | None = None,
    ) -> None:
        self._scalar_one = scalar_one
        self._scalars_all = list(scalars_all or [])

    def scalar_one_or_none(self) -> object | None:
        return self._scalar_one

    def scalars(self) -> ScalarResultStub:
        return ScalarResultStub(self._scalars_all)


class RowCountResultStub:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


class SessionStub:
    def __init__(
        self,
        *,
        execute_results: list[object] | None = None,
        scalar_results: list[object] | None = None,
    ) -> None:
        self.execute_results = list(execute_results or [])
        self.scalar_results = list(scalar_results or [])
        self.added: list[object] = []
        self.executed: list[object] = []
        self.scalar_calls: list[object] = []
        self.flush_count = 0

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flush_count += 1

    async def execute(self, statement: object) -> object:
        self.executed.append(statement)
        assert self.execute_results, f"unexpected execute call: {statement}"
        return self.execute_results.pop(0)

    async def scalar(self, statement: object) -> object:
        self.scalar_calls.append(statement)
        assert self.scalar_results, f"unexpected scalar call: {statement}"
        return self.scalar_results.pop(0)


def _verdict(
    *,
    verdict_type: VerdictType = VerdictType.VIOLATION,
    created_at: datetime | None = None,
) -> GovernanceVerdict:
    verdict = GovernanceVerdict(
        id=uuid4(),
        judge_agent_fqn="platform:judge",
        verdict_type=verdict_type,
        policy_id=uuid4(),
        evidence={"target_agent_fqn": "agent:target", "agent_fqn": "agent:target"},
        rationale="matched",
        recommended_action="block",
        source_event_id=uuid4(),
        fleet_id=uuid4(),
        workspace_id=uuid4(),
    )
    verdict.created_at = created_at or datetime.now(UTC)
    verdict.updated_at = verdict.created_at
    verdict.enforcement_actions = []
    return verdict


def _action(
    verdict_id,
    *,
    created_at: datetime | None = None,
    action_type: ActionType = ActionType.block,
) -> EnforcementAction:
    action = EnforcementAction(
        id=uuid4(),
        enforcer_agent_fqn="platform:enforcer",
        verdict_id=verdict_id,
        action_type=action_type,
        target_agent_fqn="agent:target",
        outcome={"blocked": True},
        workspace_id=uuid4(),
    )
    action.created_at = created_at or datetime.now(UTC)
    action.updated_at = action.created_at
    return action


@pytest.mark.asyncio
async def test_create_and_get_verdict_and_action_accessors() -> None:
    verdict = _verdict()
    action = _action(verdict.id)
    session = SessionStub(
        execute_results=[
            ExecuteResultStub(scalar_one=verdict),
            ExecuteResultStub(scalar_one=action),
        ]
    )
    repo = GovernanceRepository(session)  # type: ignore[arg-type]

    created_verdict = await repo.create_verdict(verdict)
    created_action = await repo.create_enforcement_action(action)
    resolved_verdict = await repo.get_verdict(verdict.id)
    resolved_action = await repo.get_enforcement_action_for_verdict(verdict.id)

    assert created_verdict is verdict
    assert created_action is action
    assert resolved_verdict is verdict
    assert resolved_action is action
    assert session.added == [verdict, action]
    assert session.flush_count == 2


@pytest.mark.asyncio
async def test_list_queries_apply_filters_cursor_and_delete_expired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    older = _verdict(created_at=datetime(2026, 4, 1, tzinfo=UTC))
    middle = _verdict(created_at=datetime(2026, 4, 2, tzinfo=UTC))
    newer = _verdict(created_at=datetime(2026, 4, 3, tzinfo=UTC))
    first_action = _action(newer.id, created_at=datetime(2026, 4, 4, tzinfo=UTC))
    second_action = _action(middle.id, created_at=datetime(2026, 4, 3, tzinfo=UTC))
    session = SessionStub(
        execute_results=[
            ExecuteResultStub(scalars_all=[newer, middle, older]),
            ExecuteResultStub(scalars_all=[first_action, second_action]),
            RowCountResultStub(4),
        ],
        scalar_results=[3, 2],
    )
    repo = GovernanceRepository(session)  # type: ignore[arg-type]
    monkeypatch.setattr("platform.governance.repository.CursorResult", RowCountResultStub)

    verdict_query = VerdictListQuery(
        target_agent_fqn=" agent:target ",
        judge_agent_fqn=" platform:judge ",
        policy_id=newer.policy_id,
        verdict_type=VerdictType.VIOLATION,
        fleet_id=newer.fleet_id,
        workspace_id=newer.workspace_id,
        from_time=datetime(2026, 4, 1, tzinfo=UTC),
        to_time=datetime(2026, 4, 5, tzinfo=UTC),
        limit=2,
        cursor=encode_cursor(uuid4(), datetime(2026, 4, 5, tzinfo=UTC)),
    )
    action_query = EnforcementActionListQuery(
        action_type=ActionType.block,
        verdict_id=newer.id,
        target_agent_fqn=" agent:target ",
        workspace_id=first_action.workspace_id,
        from_time=datetime(2026, 4, 1, tzinfo=UTC),
        to_time=datetime(2026, 4, 5, tzinfo=UTC),
        limit=1,
        cursor=encode_cursor(uuid4(), datetime(2026, 4, 5, tzinfo=UTC)),
    )

    verdicts, verdict_total, verdict_cursor = await repo.list_verdicts(verdict_query)
    actions, action_total, action_cursor = await repo.list_enforcement_actions(action_query)
    deleted = await repo.delete_expired_verdicts(30)

    assert [item.id for item in verdicts] == [newer.id, middle.id]
    assert verdict_total == 3
    assert verdict_cursor is not None
    assert [item.id for item in actions] == [first_action.id]
    assert action_total == 2
    assert action_cursor is not None
    assert deleted == 4
    assert len(session.scalar_calls) == 2
    assert len(session.executed) == 3


@pytest.mark.asyncio
async def test_list_queries_without_cursor_or_extra_page_return_no_next_cursor() -> None:
    verdict = _verdict()
    action = _action(verdict.id)
    session = SessionStub(
        execute_results=[
            ExecuteResultStub(scalars_all=[verdict]),
            ExecuteResultStub(scalars_all=[action]),
        ],
        scalar_results=[1, 1],
    )
    repo = GovernanceRepository(session)  # type: ignore[arg-type]

    verdicts, verdict_total, verdict_cursor = await repo.list_verdicts(VerdictListQuery(limit=5))
    actions, action_total, action_cursor = await repo.list_enforcement_actions(
        EnforcementActionListQuery(limit=5)
    )

    assert verdicts == [verdict]
    assert verdict_total == 1
    assert verdict_cursor is None
    assert actions == [action]
    assert action_total == 1
    assert action_cursor is None
