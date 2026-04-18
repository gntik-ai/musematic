from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.pagination import decode_cursor, encode_cursor
from platform.governance.models import EnforcementAction, GovernanceVerdict
from platform.governance.schemas import EnforcementActionListQuery, VerdictListQuery
from uuid import UUID

from sqlalchemy import ColumnElement, CursorResult, and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


class GovernanceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_verdict(self, verdict: GovernanceVerdict) -> GovernanceVerdict:
        self.session.add(verdict)
        await self.session.flush()
        return verdict

    async def get_verdict(self, verdict_id: UUID) -> GovernanceVerdict | None:
        result = await self.session.execute(
            select(GovernanceVerdict)
            .options(selectinload(GovernanceVerdict.enforcement_actions))
            .where(GovernanceVerdict.id == verdict_id)
        )
        return result.scalar_one_or_none()

    async def list_verdicts(
        self, query: VerdictListQuery
    ) -> tuple[list[GovernanceVerdict], int, str | None]:
        filters = self._verdict_filters(query)
        total = await self.session.scalar(
            select(func.count())
            .select_from(GovernanceVerdict)
            .outerjoin(EnforcementAction, EnforcementAction.verdict_id == GovernanceVerdict.id)
            .where(*filters)
        )
        stmt = (
            select(GovernanceVerdict)
            .outerjoin(EnforcementAction, EnforcementAction.verdict_id == GovernanceVerdict.id)
            .where(*filters)
            .order_by(GovernanceVerdict.created_at.desc(), GovernanceVerdict.id.desc())
        )
        if query.cursor:
            cursor_id, cursor_created_at = decode_cursor(query.cursor)
            stmt = stmt.where(
                or_(
                    GovernanceVerdict.created_at < cursor_created_at,
                    and_(
                        GovernanceVerdict.created_at == cursor_created_at,
                        GovernanceVerdict.id < cursor_id,
                    ),
                )
            )
        result = await self.session.execute(stmt.limit(query.limit + 1))
        items = list(result.scalars().unique().all())
        next_cursor = None
        if len(items) > query.limit:
            last = items[query.limit - 1]
            next_cursor = encode_cursor(last.id, last.created_at)
            items = items[: query.limit]
        return items, int(total or 0), next_cursor

    async def create_enforcement_action(self, action: EnforcementAction) -> EnforcementAction:
        self.session.add(action)
        await self.session.flush()
        return action

    async def list_enforcement_actions(
        self, query: EnforcementActionListQuery
    ) -> tuple[list[EnforcementAction], int, str | None]:
        filters = self._enforcement_filters(query)
        total = await self.session.scalar(
            select(func.count()).select_from(EnforcementAction).where(*filters)
        )
        stmt = (
            select(EnforcementAction)
            .where(*filters)
            .order_by(EnforcementAction.created_at.desc(), EnforcementAction.id.desc())
        )
        if query.cursor:
            cursor_id, cursor_created_at = decode_cursor(query.cursor)
            stmt = stmt.where(
                or_(
                    EnforcementAction.created_at < cursor_created_at,
                    and_(
                        EnforcementAction.created_at == cursor_created_at,
                        EnforcementAction.id < cursor_id,
                    ),
                )
            )
        result = await self.session.execute(stmt.limit(query.limit + 1))
        items = list(result.scalars().all())
        next_cursor = None
        if len(items) > query.limit:
            last = items[query.limit - 1]
            next_cursor = encode_cursor(last.id, last.created_at)
            items = items[: query.limit]
        return items, int(total or 0), next_cursor

    async def get_enforcement_action_for_verdict(
        self, verdict_id: UUID
    ) -> EnforcementAction | None:
        result = await self.session.execute(
            select(EnforcementAction).where(EnforcementAction.verdict_id == verdict_id)
        )
        return result.scalar_one_or_none()

    async def delete_expired_verdicts(self, retention_days: int) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        result = await self.session.execute(
            delete(GovernanceVerdict).where(GovernanceVerdict.created_at < cutoff)
        )
        cursor_result = result if isinstance(result, CursorResult) else None
        return int((cursor_result.rowcount if cursor_result is not None else 0) or 0)

    def _verdict_filters(self, query: VerdictListQuery) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = []
        if query.judge_agent_fqn is not None:
            filters.append(GovernanceVerdict.judge_agent_fqn == query.judge_agent_fqn)
        if query.policy_id is not None:
            filters.append(GovernanceVerdict.policy_id == query.policy_id)
        if query.verdict_type is not None:
            filters.append(GovernanceVerdict.verdict_type == query.verdict_type)
        if query.fleet_id is not None:
            filters.append(GovernanceVerdict.fleet_id == query.fleet_id)
        if query.workspace_id is not None:
            filters.append(GovernanceVerdict.workspace_id == query.workspace_id)
        if query.from_time is not None:
            filters.append(GovernanceVerdict.created_at >= query.from_time)
        if query.to_time is not None:
            filters.append(GovernanceVerdict.created_at <= query.to_time)
        if query.target_agent_fqn is not None:
            filters.append(
                or_(
                    EnforcementAction.target_agent_fqn == query.target_agent_fqn,
                    GovernanceVerdict.evidence["target_agent_fqn"].astext == query.target_agent_fqn,
                    GovernanceVerdict.evidence["agent_fqn"].astext == query.target_agent_fqn,
                )
            )
        return filters

    def _enforcement_filters(self, query: EnforcementActionListQuery) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = []
        if query.action_type is not None:
            filters.append(EnforcementAction.action_type == query.action_type)
        if query.verdict_id is not None:
            filters.append(EnforcementAction.verdict_id == query.verdict_id)
        if query.target_agent_fqn is not None:
            filters.append(EnforcementAction.target_agent_fqn == query.target_agent_fqn)
        if query.workspace_id is not None:
            filters.append(EnforcementAction.workspace_id == query.workspace_id)
        if query.from_time is not None:
            filters.append(EnforcementAction.created_at >= query.from_time)
        if query.to_time is not None:
            filters.append(EnforcementAction.created_at <= query.to_time)
        return filters
