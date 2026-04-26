from __future__ import annotations

import hashlib
import secrets
from collections.abc import Awaitable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from platform.common.audit_hook import audit_chain_hook
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.cost_governance.constants import BLOCK_REASON_COST_BUDGET
from platform.cost_governance.events import (
    CostBudgetExceededPayload,
    CostBudgetThresholdReachedPayload,
    CostGovernanceEventType,
    publish_cost_governance_event,
)
from platform.cost_governance.exceptions import (
    InvalidBudgetConfigError,
    OverrideAlreadyRedeemedError,
    OverrideExpiredError,
)
from platform.cost_governance.models import WorkspaceBudget
from platform.cost_governance.repository import CostGovernanceRepository
from platform.cost_governance.schemas import BudgetCheckResult, OverrideIssueResponse
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

SCRIPT_DIR = Path(__file__).resolve().parent
BUDGET_ATOMIC_SCRIPT = SCRIPT_DIR / "_budget_atomic.lua"
OVERRIDE_REDEEM_SCRIPT = SCRIPT_DIR / "_override_redeem.lua"
BUDGET_ATOMIC_SOURCE = BUDGET_ATOMIC_SCRIPT.read_text(encoding="utf-8")
OVERRIDE_REDEEM_SOURCE = OVERRIDE_REDEEM_SCRIPT.read_text(encoding="utf-8")


class BudgetService:
    def __init__(
        self,
        *,
        repository: CostGovernanceRepository,
        redis_client: AsyncRedisClient | None,
        settings: PlatformSettings,
        kafka_producer: EventProducer | None = None,
        audit_chain_service: Any | None = None,
        alert_service: Any | None = None,
        workspaces_service: Any | None = None,
    ) -> None:
        self.repository = repository
        self.redis_client = redis_client
        self.settings = settings
        self.cost_settings = settings.cost_governance
        self.kafka_producer = kafka_producer
        self.audit_chain_service = audit_chain_service
        self.alert_service = alert_service
        self.workspaces_service = workspaces_service
        self._budget_script_sha: str | None = None
        self._override_script_sha: str | None = None

    async def configure(
        self,
        *,
        workspace_id: UUID,
        period_type: str,
        budget_cents: int,
        soft_alert_thresholds: list[int] | None = None,
        hard_cap_enabled: bool = False,
        admin_override_enabled: bool = True,
        actor_id: UUID | None = None,
        currency: str | None = None,
    ) -> WorkspaceBudget:
        thresholds = soft_alert_thresholds or list(self.cost_settings.default_alert_thresholds)
        if sorted(thresholds) != thresholds or any(item <= 0 or item > 100 for item in thresholds):
            raise InvalidBudgetConfigError("Soft alert thresholds must be sorted and <= 100")
        budget = await self.repository.upsert_budget(
            workspace_id=workspace_id,
            period_type=period_type,
            budget_cents=budget_cents,
            soft_alert_thresholds=thresholds,
            hard_cap_enabled=hard_cap_enabled,
            admin_override_enabled=admin_override_enabled,
            currency=currency or self.cost_settings.default_currency,
            actor_id=actor_id,
        )
        await self._audit(
            "cost.budget.configured",
            budget.id,
            {
                "workspace_id": workspace_id,
                "period_type": period_type,
                "budget_cents": budget_cents,
                "hard_cap_enabled": hard_cap_enabled,
                "actor_id": actor_id,
            },
        )
        return budget

    async def evaluate_thresholds(self, workspace_id: UUID) -> list[UUID]:
        fired: list[UUID] = []
        for budget in await self.repository.list_budgets(workspace_id):
            period_start, period_end = period_bounds(budget.period_type)
            spend = await self.repository.period_spend(workspace_id, period_start, period_end)
            await self._prime_hot_counter(budget, period_start, period_end, spend)
            for threshold in list(budget.soft_alert_thresholds):
                if spend < Decimal(budget.budget_cents) * Decimal(threshold) / Decimal(100):
                    continue
                alert = await self.repository.record_alert(
                    budget.id,
                    workspace_id,
                    int(threshold),
                    period_start,
                    period_end,
                    spend,
                )
                if alert is None:
                    continue
                fired.append(alert.id)
                await self._route_budget_alert(workspace_id, alert.id, int(threshold))
                await publish_cost_governance_event(
                    self.kafka_producer,
                    CostGovernanceEventType.budget_threshold_reached,
                    CostBudgetThresholdReachedPayload(
                        budget_id=budget.id,
                        workspace_id=workspace_id,
                        threshold_percentage=int(threshold),
                        period_start=period_start,
                        period_end=period_end,
                        spend_cents=spend,
                        budget_cents=budget.budget_cents,
                    ),
                    CorrelationContext(workspace_id=workspace_id, correlation_id=uuid4()),
                )
        return fired

    async def check_budget_for_start(
        self,
        workspace_id: UUID,
        estimated_cost_cents: Decimal | int | float | str,
        override_token: str | None = None,
        *,
        period_type: str = "monthly",
    ) -> BudgetCheckResult:
        budget = await self.repository.get_active_budget(workspace_id, period_type)
        if budget is None:
            return BudgetCheckResult(allowed=True)
        period_start, period_end = period_bounds(budget.period_type)
        estimate = Decimal(str(estimated_cost_cents or 0))

        if override_token:
            await self.redeem_override(override_token, redeemed_by=None)
            return BudgetCheckResult(allowed=True)

        spend = await self._current_spend(budget, period_start, period_end)
        projected = spend + estimate
        if not self.settings.feature_cost_hard_caps or not budget.hard_cap_enabled:
            return BudgetCheckResult(
                allowed=True,
                budget_cents=budget.budget_cents,
                projected_spend_cents=projected,
                period_type=budget.period_type,
                period_start=period_start,
                period_end=period_end,
            )
        if projected <= Decimal(budget.budget_cents):
            admitted, atomic_projected = await self._atomic_admit(
                budget,
                period_start,
                period_end,
                estimate,
            )
            if admitted:
                return BudgetCheckResult(
                    allowed=True,
                    budget_cents=budget.budget_cents,
                    projected_spend_cents=atomic_projected,
                    period_type=budget.period_type,
                    period_start=period_start,
                    period_end=period_end,
                )
            spend = atomic_projected
            projected = spend + estimate

        if projected <= Decimal(budget.budget_cents):
            return BudgetCheckResult(
                allowed=True,
                budget_cents=budget.budget_cents,
                projected_spend_cents=projected,
                period_type=budget.period_type,
                period_start=period_start,
                period_end=period_end,
            )
        override_endpoint = f"/api/v1/costs/workspaces/{workspace_id}/budget/override"
        if await self._mark_exceeded_event_once(budget, period_start, period_end):
            await publish_cost_governance_event(
                self.kafka_producer,
                CostGovernanceEventType.budget_exceeded,
                CostBudgetExceededPayload(
                    budget_id=budget.id,
                    workspace_id=workspace_id,
                    period_start=period_start,
                    period_end=period_end,
                    spend_cents=spend,
                    budget_cents=budget.budget_cents,
                    override_endpoint=override_endpoint,
                ),
                CorrelationContext(workspace_id=workspace_id, correlation_id=uuid4()),
            )
        return BudgetCheckResult(
            allowed=False,
            block_reason=BLOCK_REASON_COST_BUDGET,
            override_endpoint=override_endpoint,
            budget_cents=budget.budget_cents,
            projected_spend_cents=projected,
            period_type=budget.period_type,
            period_start=period_start,
            period_end=period_end,
        )

    async def issue_override(
        self,
        workspace_id: UUID,
        requested_by: UUID,
        reason: str,
    ) -> OverrideIssueResponse:
        token = secrets.token_urlsafe(32)
        token_hash = _hash_token(token)
        expires_at = datetime.now(UTC) + timedelta(
            seconds=self.cost_settings.override_token_ttl_seconds
        )
        if self.redis_client is not None:
            await self.redis_client.set(
                self._override_key(token),
                str(workspace_id).encode("utf-8"),
                ttl=self.cost_settings.override_token_ttl_seconds,
            )
        await self.repository.create_override_record(
            workspace_id=workspace_id,
            issued_by=requested_by,
            reason=reason,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        await self._audit(
            "cost.budget.override.issued",
            workspace_id,
            {"workspace_id": workspace_id, "requested_by": requested_by, "reason": reason},
        )
        return OverrideIssueResponse(token=token, expires_at=expires_at)

    async def redeem_override(
        self,
        token: str,
        *,
        redeemed_by: UUID | None = None,
    ) -> None:
        if self.redis_client is None:
            await self.repository.mark_override_redeemed(_hash_token(token), redeemed_by)
            return
        redeemed_key = self._override_redeemed_key(token)
        if await self.redis_client.get(redeemed_key) is not None:
            raise OverrideAlreadyRedeemedError()
        key = self._override_key(token)
        value = await self._redeem_override_atomic(key, redeemed_key)
        if value == b"already_redeemed":
            raise OverrideAlreadyRedeemedError()
        if value is None:
            raise OverrideExpiredError()
        await self.repository.mark_override_redeemed(_hash_token(token), redeemed_by)
        await self._audit(
            "cost.budget.override.redeemed",
            uuid4(),
            {"redeemed_by": redeemed_by},
        )

    async def invalidate_hot_counter(self, workspace_id: UUID, period_type: str) -> None:
        if self.redis_client is None:
            return
        period_start, _period_end = period_bounds(period_type)
        await self.redis_client.delete(self._counter_key(workspace_id, period_type, period_start))

    async def _current_spend(
        self,
        budget: WorkspaceBudget,
        period_start: datetime,
        period_end: datetime,
    ) -> Decimal:
        if self.redis_client is not None:
            cached = await self.redis_client.get(
                self._counter_key(budget.workspace_id, budget.period_type, period_start)
            )
            if cached is not None:
                return Decimal(cached.decode("utf-8"))
        spend = await self.repository.period_spend(budget.workspace_id, period_start, period_end)
        await self._prime_hot_counter(budget, period_start, period_end, spend)
        return spend

    async def _increment_hot_counter(
        self,
        budget: WorkspaceBudget,
        period_start: datetime,
        period_end: datetime,
        amount: Decimal,
    ) -> None:
        if self.redis_client is None:
            return
        spend = await self._current_spend(budget, period_start, period_end)
        await self._prime_hot_counter(budget, period_start, period_end, spend + amount)

    async def _atomic_admit(
        self,
        budget: WorkspaceBudget,
        period_start: datetime,
        period_end: datetime,
        amount: Decimal,
    ) -> tuple[bool, Decimal]:
        if self.redis_client is None:
            await self._increment_hot_counter(budget, period_start, period_end, amount)
            spend = await self._current_spend(budget, period_start, period_end)
            return spend <= Decimal(budget.budget_cents), spend

        spend = await self._current_spend(budget, period_start, period_end)
        key = self._counter_key(budget.workspace_id, budget.period_type, period_start)
        result = await self._eval_lua(
            BUDGET_ATOMIC_SOURCE,
            "_budget_script_sha",
            [key],
            [str(amount), str(budget.budget_cents), str(self._counter_ttl(period_end))],
        )
        if isinstance(result, (list, tuple)) and len(result) >= 2:
            return bool(int(result[0])), Decimal(str(result[1]))

        projected = spend + amount
        if projected <= Decimal(budget.budget_cents):
            await self._prime_hot_counter(budget, period_start, period_end, projected)
            return True, projected
        return False, spend

    async def _prime_hot_counter(
        self,
        budget: WorkspaceBudget,
        period_start: datetime,
        period_end: datetime,
        spend: Decimal,
    ) -> None:
        if self.redis_client is None:
            return
        await self.redis_client.set(
            self._counter_key(budget.workspace_id, budget.period_type, period_start),
            str(spend).encode("utf-8"),
            ttl=self._counter_ttl(period_end),
        )

    async def _mark_exceeded_event_once(
        self,
        budget: WorkspaceBudget,
        period_start: datetime,
        period_end: datetime,
    ) -> bool:
        if self.redis_client is None:
            return True
        key = self._exceeded_event_key(budget.workspace_id, budget.period_type, period_start)
        if await self.redis_client.get(key) is not None:
            return False
        await self.redis_client.set(key, b"1", ttl=self._counter_ttl(period_end))
        return True

    async def _route_budget_alert(
        self,
        workspace_id: UUID,
        alert_id: UUID,
        threshold: int,
    ) -> None:
        if self.alert_service is None:
            return
        processor = getattr(self.alert_service, "process_state_change", None)
        if not callable(processor):
            return
        payload = SimpleNamespace(
            interaction_id=alert_id,
            from_state="budget_below_threshold",
            to_state=f"budget_threshold_{threshold}_reached",
        )
        await processor(payload, workspace_id)

    def _counter_ttl(self, period_end: datetime) -> int:
        return max(int((period_end - datetime.now(UTC)).total_seconds()) + 86_400, 60)

    async def _redeem_override_atomic(self, key: str, redeemed_key: str) -> bytes | None:
        result = await self._eval_lua(
            OVERRIDE_REDEEM_SOURCE,
            "_override_script_sha",
            [key, redeemed_key],
            ["86400"],
        )
        if result is None:
            return None
        if isinstance(result, bytes):
            return result
        if isinstance(result, str):
            return result.encode("utf-8")
        return str(result).encode("utf-8")

    async def _eval_lua(
        self,
        source: str,
        sha_attr: str,
        keys: list[str],
        args: list[str],
    ) -> Any:
        assert self.redis_client is not None
        await self.redis_client.initialize()
        client = self.redis_client.client
        if client is None:
            return None
        sha = getattr(self, sha_attr)
        if sha is None:
            sha = str(await _maybe_await(client.script_load(source)))
            setattr(self, sha_attr, sha)
        try:
            return await _maybe_await(client.evalsha(sha, len(keys), *keys, *args))
        except Exception:
            setattr(self, sha_attr, None)
            return await _maybe_await(client.eval(source, len(keys), *keys, *args))

    async def _audit(self, event: str, event_id: UUID, payload: dict[str, Any]) -> None:
        if self.audit_chain_service is None:
            return
        await audit_chain_hook(
            self.audit_chain_service,
            event_id,
            "cost_governance",
            {"event": event, **payload},
        )

    @staticmethod
    def _counter_key(workspace_id: UUID, period_type: str, period_start: datetime) -> str:
        return f"cost:budget:{workspace_id}:{period_type}:{period_start.date().isoformat()}"

    @staticmethod
    def _override_key(token: str) -> str:
        return f"cost:override:{_hash_token(token)}"

    @staticmethod
    def _override_redeemed_key(token: str) -> str:
        return f"cost:override-redeemed:{_hash_token(token)}"

    @staticmethod
    def _exceeded_event_key(workspace_id: UUID, period_type: str, period_start: datetime) -> str:
        return (
            "cost:budget-exceeded-event:"
            f"{workspace_id}:{period_type}:{period_start.date().isoformat()}"
        )


def period_bounds(period_type: str, now: datetime | None = None) -> tuple[datetime, datetime]:
    current = (now or datetime.now(UTC)).astimezone(UTC)
    if period_type == "daily":
        start = current.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1)
    if period_type == "weekly":
        start = (current - timedelta(days=current.weekday())).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        return start, start + timedelta(days=7)
    start = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        return start, start.replace(year=start.year + 1, month=1)
    return start, start.replace(month=start.month + 1)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def _maybe_await(value: Awaitable[Any] | Any) -> Any:
    if hasattr(value, "__await__"):
        return await cast(Awaitable[Any], value)
    return value
