from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from platform.cost_governance.models import (
    BudgetAlert,
    CostAnomaly,
    CostAttribution,
    CostForecast,
    OverrideRecord,
    WorkspaceBudget,
)
from typing import Any
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession


class CostGovernanceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert_attribution(
        self,
        *,
        execution_id: UUID,
        step_id: str | None,
        workspace_id: UUID,
        agent_id: UUID | None,
        user_id: UUID | None,
        origin: str,
        model_id: str | None,
        currency: str,
        model_cost_cents: Decimal,
        compute_cost_cents: Decimal,
        storage_cost_cents: Decimal,
        overhead_cost_cents: Decimal,
        token_counts: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> CostAttribution:
        attribution = CostAttribution(
            execution_id=execution_id,
            step_id=step_id,
            workspace_id=workspace_id,
            agent_id=agent_id,
            user_id=user_id,
            origin=origin,
            model_id=model_id,
            currency=currency,
            model_cost_cents=model_cost_cents,
            compute_cost_cents=compute_cost_cents,
            storage_cost_cents=storage_cost_cents,
            overhead_cost_cents=overhead_cost_cents,
            token_counts=token_counts,
            attribution_metadata=dict(metadata or {}),
        )
        self.session.add(attribution)
        await self.session.flush()
        return attribution

    async def insert_attribution_correction(
        self,
        original_id: UUID,
        *,
        model_cost_cents: Decimal = Decimal("0"),
        compute_cost_cents: Decimal = Decimal("0"),
        storage_cost_cents: Decimal = Decimal("0"),
        overhead_cost_cents: Decimal = Decimal("0"),
        metadata: dict[str, Any] | None = None,
    ) -> CostAttribution:
        original = await self.session.get(CostAttribution, original_id)
        if original is None:
            raise LookupError(f"cost attribution {original_id} not found")
        correction = CostAttribution(
            execution_id=original.execution_id,
            step_id=original.step_id,
            workspace_id=original.workspace_id,
            agent_id=original.agent_id,
            user_id=original.user_id,
            origin=original.origin,
            model_id=original.model_id,
            currency=original.currency,
            model_cost_cents=model_cost_cents,
            compute_cost_cents=compute_cost_cents,
            storage_cost_cents=storage_cost_cents,
            overhead_cost_cents=overhead_cost_cents,
            token_counts={},
            attribution_metadata=dict(metadata or {}),
            correction_of=original.id,
        )
        self.session.add(correction)
        await self.session.flush()
        return correction

    async def get_attribution_by_execution(self, execution_id: UUID) -> CostAttribution | None:
        result = await self.session.execute(
            select(CostAttribution)
            .where(
                CostAttribution.execution_id == execution_id,
                CostAttribution.correction_of.is_(None),
            )
            .order_by(CostAttribution.created_at.asc(), CostAttribution.id.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_execution_attributions(self, execution_id: UUID) -> list[CostAttribution]:
        result = await self.session.execute(
            select(CostAttribution)
            .where(CostAttribution.execution_id == execution_id)
            .order_by(CostAttribution.created_at.asc(), CostAttribution.id.asc())
        )
        return list(result.scalars().all())

    async def get_workspace_attributions(
        self,
        workspace_id: UUID,
        since: datetime | None,
        until: datetime | None,
        cursor: datetime | None,
        limit: int,
        *,
        agent_id: UUID | None = None,
        user_id: UUID | None = None,
    ) -> list[CostAttribution]:
        statement = select(CostAttribution).where(CostAttribution.workspace_id == workspace_id)
        if since is not None:
            statement = statement.where(CostAttribution.created_at >= since)
        if until is not None:
            statement = statement.where(CostAttribution.created_at <= until)
        if cursor is not None:
            statement = statement.where(CostAttribution.created_at < cursor)
        if agent_id is not None:
            statement = statement.where(CostAttribution.agent_id == agent_id)
        if user_id is not None:
            statement = statement.where(CostAttribution.user_id == user_id)
        result = await self.session.execute(
            statement.order_by(CostAttribution.created_at.desc(), CostAttribution.id.desc()).limit(
                limit
            )
        )
        return list(result.scalars().all())

    async def aggregate_attributions(
        self,
        workspace_id: UUID,
        group_by: Sequence[str],
        since: datetime,
        until: datetime,
    ) -> list[dict[str, Any]]:
        group_columns = _group_columns(group_by)
        statement = (
            select(
                *group_columns,
                func.coalesce(func.sum(CostAttribution.model_cost_cents), 0).label(
                    "model_cost_cents"
                ),
                func.coalesce(func.sum(CostAttribution.compute_cost_cents), 0).label(
                    "compute_cost_cents"
                ),
                func.coalesce(func.sum(CostAttribution.storage_cost_cents), 0).label(
                    "storage_cost_cents"
                ),
                func.coalesce(func.sum(CostAttribution.overhead_cost_cents), 0).label(
                    "overhead_cost_cents"
                ),
                func.coalesce(func.sum(CostAttribution.total_cost_cents), 0).label(
                    "total_cost_cents"
                ),
            )
            .where(
                CostAttribution.workspace_id == workspace_id,
                CostAttribution.created_at >= since,
                CostAttribution.created_at <= until,
            )
            .group_by(*group_columns)
        )
        result = await self.session.execute(statement)
        return [dict(row._mapping) for row in result.all()]

    async def get_active_budget(
        self,
        workspace_id: UUID,
        period_type: str,
    ) -> WorkspaceBudget | None:
        result = await self.session.execute(
            select(WorkspaceBudget)
            .where(
                WorkspaceBudget.workspace_id == workspace_id,
                WorkspaceBudget.period_type == period_type,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_budgets(self, workspace_id: UUID) -> list[WorkspaceBudget]:
        result = await self.session.execute(
            select(WorkspaceBudget)
            .where(WorkspaceBudget.workspace_id == workspace_id)
            .order_by(WorkspaceBudget.period_type.asc())
        )
        return list(result.scalars().all())

    async def upsert_budget(
        self,
        *,
        workspace_id: UUID,
        period_type: str,
        budget_cents: int,
        soft_alert_thresholds: list[int],
        hard_cap_enabled: bool,
        admin_override_enabled: bool,
        currency: str,
        actor_id: UUID | None,
    ) -> WorkspaceBudget:
        statement = (
            insert(WorkspaceBudget)
            .values(
                workspace_id=workspace_id,
                period_type=period_type,
                budget_cents=budget_cents,
                soft_alert_thresholds=soft_alert_thresholds,
                hard_cap_enabled=hard_cap_enabled,
                admin_override_enabled=admin_override_enabled,
                currency=currency,
                created_by=actor_id,
                updated_by=actor_id,
            )
            .on_conflict_do_update(
                constraint="uq_workspace_budget_period",
                set_={
                    "budget_cents": budget_cents,
                    "soft_alert_thresholds": soft_alert_thresholds,
                    "hard_cap_enabled": hard_cap_enabled,
                    "admin_override_enabled": admin_override_enabled,
                    "currency": currency,
                    "updated_by": actor_id,
                    "updated_at": datetime.now(UTC),
                },
            )
            .returning(WorkspaceBudget)
        )
        result = await self.session.execute(statement)
        return result.scalar_one()

    async def delete_budget(self, budget_id: UUID) -> bool:
        budget = await self.session.get(WorkspaceBudget, budget_id)
        if budget is None:
            return False
        await self.session.delete(budget)
        await self.session.flush()
        return True

    async def record_alert(
        self,
        budget_id: UUID,
        workspace_id: UUID,
        threshold: int,
        period_start: datetime,
        period_end: datetime,
        spend_cents: Decimal,
    ) -> BudgetAlert | None:
        statement = (
            insert(BudgetAlert)
            .values(
                budget_id=budget_id,
                workspace_id=workspace_id,
                threshold_percentage=threshold,
                period_start=period_start,
                period_end=period_end,
                spend_cents=spend_cents,
            )
            .on_conflict_do_nothing(
                constraint="uq_budget_alert_threshold_period",
            )
            .returning(BudgetAlert)
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_alerts(
        self,
        workspace_id: UUID,
        *,
        cursor: datetime | None = None,
        limit: int = 100,
    ) -> list[BudgetAlert]:
        statement = select(BudgetAlert).where(BudgetAlert.workspace_id == workspace_id)
        if cursor is not None:
            statement = statement.where(BudgetAlert.triggered_at < cursor)
        result = await self.session.execute(
            statement.order_by(BudgetAlert.triggered_at.desc(), BudgetAlert.id.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def insert_forecast(
        self,
        *,
        workspace_id: UUID,
        period_start: datetime,
        period_end: datetime,
        forecast_cents: Decimal | None,
        confidence_interval: dict[str, Any],
        currency: str,
    ) -> CostForecast:
        forecast = CostForecast(
            workspace_id=workspace_id,
            period_start=period_start,
            period_end=period_end,
            forecast_cents=forecast_cents,
            confidence_interval=confidence_interval,
            currency=currency,
        )
        self.session.add(forecast)
        await self.session.flush()
        return forecast

    async def get_latest_forecast(self, workspace_id: UUID) -> CostForecast | None:
        result = await self.session.execute(
            select(CostForecast)
            .where(CostForecast.workspace_id == workspace_id)
            .order_by(desc(CostForecast.computed_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def insert_anomaly(
        self,
        *,
        workspace_id: UUID,
        anomaly_type: str,
        severity: str,
        baseline_cents: Decimal,
        observed_cents: Decimal,
        period_start: datetime,
        period_end: datetime,
        summary: str,
        correlation_fingerprint: str,
    ) -> CostAnomaly:
        anomaly = CostAnomaly(
            workspace_id=workspace_id,
            anomaly_type=anomaly_type,
            severity=severity,
            state="open",
            baseline_cents=baseline_cents,
            observed_cents=observed_cents,
            period_start=period_start,
            period_end=period_end,
            summary=summary,
            correlation_fingerprint=correlation_fingerprint,
        )
        self.session.add(anomaly)
        await self.session.flush()
        return anomaly

    async def find_open_anomaly_by_fingerprint(
        self,
        workspace_id: UUID,
        fingerprint: str,
    ) -> CostAnomaly | None:
        result = await self.session.execute(
            select(CostAnomaly)
            .where(
                CostAnomaly.workspace_id == workspace_id,
                CostAnomaly.correlation_fingerprint == fingerprint,
                CostAnomaly.state == "open",
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_anomaly(self, anomaly_id: UUID) -> CostAnomaly | None:
        return await self.session.get(CostAnomaly, anomaly_id)

    async def acknowledge_anomaly(self, anomaly_id: UUID, by_user_id: UUID) -> CostAnomaly | None:
        anomaly = await self.get_anomaly(anomaly_id)
        if anomaly is None:
            return None
        anomaly.state = "acknowledged"
        anomaly.acknowledged_at = datetime.now(UTC)
        anomaly.acknowledged_by = by_user_id
        await self.session.flush()
        return anomaly

    async def resolve_anomaly(self, anomaly_id: UUID) -> CostAnomaly | None:
        anomaly = await self.get_anomaly(anomaly_id)
        if anomaly is None:
            return None
        anomaly.state = "resolved"
        anomaly.resolved_at = datetime.now(UTC)
        await self.session.flush()
        return anomaly

    async def list_anomalies(
        self,
        workspace_id: UUID,
        state: str | None,
        limit: int,
        cursor: datetime | None,
    ) -> list[CostAnomaly]:
        statement = select(CostAnomaly).where(CostAnomaly.workspace_id == workspace_id)
        if state is not None:
            statement = statement.where(CostAnomaly.state == state)
        if cursor is not None:
            statement = statement.where(CostAnomaly.detected_at < cursor)
        result = await self.session.execute(
            statement.order_by(CostAnomaly.detected_at.desc(), CostAnomaly.id.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def create_override_record(
        self,
        *,
        workspace_id: UUID,
        issued_by: UUID,
        reason: str,
        token_hash: str,
        expires_at: datetime,
    ) -> OverrideRecord:
        record = OverrideRecord(
            workspace_id=workspace_id,
            issued_by=issued_by,
            reason=reason,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def mark_override_redeemed(
        self,
        token_hash: str,
        redeemed_by: UUID | None,
    ) -> OverrideRecord | None:
        result = await self.session.execute(
            select(OverrideRecord).where(OverrideRecord.token_hash == token_hash)
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None
        record.redeemed_at = datetime.now(UTC)
        record.redeemed_by = redeemed_by
        await self.session.flush()
        return record

    async def period_spend(
        self,
        workspace_id: UUID,
        period_start: datetime,
        period_end: datetime,
    ) -> Decimal:
        value = await self.session.scalar(
            select(func.coalesce(func.sum(CostAttribution.total_cost_cents), 0)).where(
                CostAttribution.workspace_id == workspace_id,
                CostAttribution.created_at >= period_start,
                CostAttribution.created_at < period_end,
            )
        )
        return Decimal(str(value or 0))

    async def list_workspace_ids_with_costs(self) -> list[UUID]:
        result = await self.session.execute(
            select(CostAttribution.workspace_id).distinct().order_by(CostAttribution.workspace_id)
        )
        return list(result.scalars().all())


def _group_columns(group_by: Sequence[str]) -> list[Any]:
    mapping: dict[str, Any] = {
        "workspace": CostAttribution.workspace_id.label("workspace_id"),
        "workspace_id": CostAttribution.workspace_id.label("workspace_id"),
        "agent": CostAttribution.agent_id.label("agent_id"),
        "agent_id": CostAttribution.agent_id.label("agent_id"),
        "user": CostAttribution.user_id.label("user_id"),
        "user_id": CostAttribution.user_id.label("user_id"),
        "cost_type": CostAttribution.model_id.label("cost_type"),
        "day": func.date_trunc("day", CostAttribution.created_at).label("day"),
        "week": func.date_trunc("week", CostAttribution.created_at).label("week"),
        "month": func.date_trunc("month", CostAttribution.created_at).label("month"),
    }
    columns = [mapping[item] for item in group_by if item in mapping]
    return columns or [CostAttribution.workspace_id.label("workspace_id")]

