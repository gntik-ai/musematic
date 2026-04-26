from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from platform.common.config import PlatformSettings
from platform.cost_governance.exceptions import InvalidBudgetConfigError
from platform.cost_governance.services.budget_service import BudgetService, period_bounds
from typing import Any
from uuid import UUID, uuid4

import pytest


@dataclass
class BudgetRow:
    workspace_id: UUID
    period_type: str
    budget_cents: int
    soft_alert_thresholds: list[int] = field(default_factory=lambda: [50, 80, 100])
    hard_cap_enabled: bool = False
    admin_override_enabled: bool = True
    currency: str = "USD"
    id: UUID = field(default_factory=uuid4)


@dataclass
class AlertRow:
    budget_id: UUID
    workspace_id: UUID
    threshold_percentage: int
    period_start: datetime
    period_end: datetime
    spend_cents: Decimal
    id: UUID = field(default_factory=uuid4)
    triggered_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class FakeBudgetRepository:
    def __init__(self, budget: BudgetRow | None = None) -> None:
        self.budgets: list[BudgetRow] = [] if budget is None else [budget]
        self.spend = Decimal("0")
        self.alerts: dict[tuple[UUID, int, datetime], AlertRow] = {}
        self.redeemed_tokens: list[tuple[str, UUID | None]] = []

    async def list_budgets(self, workspace_id: UUID) -> list[BudgetRow]:
        return [budget for budget in self.budgets if budget.workspace_id == workspace_id]

    async def period_spend(
        self,
        workspace_id: UUID,
        period_start: datetime,
        period_end: datetime,
    ) -> Decimal:
        del workspace_id, period_start, period_end
        return self.spend

    async def record_alert(
        self,
        budget_id: UUID,
        workspace_id: UUID,
        threshold: int,
        period_start: datetime,
        period_end: datetime,
        spend_cents: Decimal,
    ) -> AlertRow | None:
        key = (budget_id, threshold, period_start)
        if key in self.alerts:
            return None
        alert = AlertRow(
            budget_id=budget_id,
            workspace_id=workspace_id,
            threshold_percentage=threshold,
            period_start=period_start,
            period_end=period_end,
            spend_cents=spend_cents,
        )
        self.alerts[key] = alert
        return alert

    async def get_active_budget(self, workspace_id: UUID, period_type: str) -> BudgetRow | None:
        return next(
            (
                budget
                for budget in self.budgets
                if budget.workspace_id == workspace_id and budget.period_type == period_type
            ),
            None,
        )

    async def upsert_budget(self, **kwargs: Any) -> BudgetRow:
        kwargs.pop("actor_id", None)
        existing = await self.get_active_budget(kwargs["workspace_id"], kwargs["period_type"])
        if existing is None:
            budget = BudgetRow(**kwargs)
            self.budgets.append(budget)
            return budget
        for key, value in kwargs.items():
            setattr(existing, key, value)
        return existing

    async def create_override_record(self, **kwargs: Any) -> object:
        del kwargs
        return object()

    async def mark_override_redeemed(self, token_hash: str, redeemed_by: UUID | None) -> object:
        self.redeemed_tokens.append((token_hash, redeemed_by))
        return object()


class RecordingAlertService:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, UUID]] = []

    async def process_state_change(self, payload: Any, workspace_id: UUID) -> list[Any]:
        self.calls.append((payload, workspace_id))
        return []


class AuditRecorder:
    def __init__(self) -> None:
        self.events: list[tuple[Any, ...]] = []

    async def append(self, *payload: Any) -> None:
        self.events.append(payload)


def _settings(*, hard_caps: bool = False) -> PlatformSettings:
    return PlatformSettings(feature_cost_hard_caps=hard_caps)


@pytest.mark.asyncio
async def test_configure_validates_thresholds_and_audits() -> None:
    workspace_id = uuid4()
    repository = FakeBudgetRepository()
    audit = AuditRecorder()
    service = BudgetService(
        repository=repository,  # type: ignore[arg-type]
        redis_client=None,
        settings=_settings(),
        audit_chain_service=audit,
    )

    with pytest.raises(InvalidBudgetConfigError):
        await service.configure(
            workspace_id=workspace_id,
            period_type="monthly",
            budget_cents=100,
            soft_alert_thresholds=[80, 50],
        )

    budget = await service.configure(
        workspace_id=workspace_id,
        period_type="monthly",
        budget_cents=250,
        hard_cap_enabled=True,
        actor_id=uuid4(),
    )

    assert budget.budget_cents == 250
    assert budget.currency == "USD"
    assert len(audit.events) == 1


@pytest.mark.asyncio
async def test_evaluate_thresholds_fires_each_soft_alert_once_per_period() -> None:
    workspace_id = uuid4()
    budget = BudgetRow(workspace_id=workspace_id, period_type="monthly", budget_cents=100)
    repo = FakeBudgetRepository(budget)
    repo.spend = Decimal("100")
    alerts = RecordingAlertService()
    service = BudgetService(
        repository=repo,  # type: ignore[arg-type]
        redis_client=None,
        settings=_settings(),
        alert_service=alerts,
    )

    first = await service.evaluate_thresholds(workspace_id)
    second = await service.evaluate_thresholds(workspace_id)

    assert len(first) == 3
    assert second == []
    assert [call[0].to_state for call in alerts.calls] == [
        "budget_threshold_50_reached",
        "budget_threshold_80_reached",
        "budget_threshold_100_reached",
    ]


@pytest.mark.asyncio
async def test_period_rollover_allows_thresholds_to_fire_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid4()
    budget = BudgetRow(workspace_id=workspace_id, period_type="daily", budget_cents=100)
    repo = FakeBudgetRepository(budget)
    repo.spend = Decimal("90")
    service = BudgetService(
        repository=repo,  # type: ignore[arg-type]
        redis_client=None,
        settings=_settings(),
    )
    first_day = datetime(2026, 4, 1, 12, tzinfo=UTC)
    second_day = datetime(2026, 4, 2, 12, tzinfo=UTC)

    monkeypatch.setattr(
        "platform.cost_governance.services.budget_service.period_bounds",
        lambda period_type: period_bounds(period_type, first_day),
    )
    assert len(await service.evaluate_thresholds(workspace_id)) == 2

    monkeypatch.setattr(
        "platform.cost_governance.services.budget_service.period_bounds",
        lambda period_type: period_bounds(period_type, second_day),
    )
    assert len(await service.evaluate_thresholds(workspace_id)) == 2


@pytest.mark.asyncio
async def test_budget_change_mid_period_preserves_fired_thresholds() -> None:
    workspace_id = uuid4()
    budget = BudgetRow(workspace_id=workspace_id, period_type="monthly", budget_cents=100)
    repo = FakeBudgetRepository(budget)
    repo.spend = Decimal("80")
    service = BudgetService(
        repository=repo,  # type: ignore[arg-type]
        redis_client=None,
        settings=_settings(),
    )

    assert len(await service.evaluate_thresholds(workspace_id)) == 2
    budget.budget_cents = 200
    assert await service.evaluate_thresholds(workspace_id) == []
    budget.budget_cents = 50
    assert len(await service.evaluate_thresholds(workspace_id)) == 1


@pytest.mark.asyncio
async def test_budget_check_allows_without_budget_or_disabled_hard_cap() -> None:
    workspace_id = uuid4()
    empty_service = BudgetService(
        repository=FakeBudgetRepository(),  # type: ignore[arg-type]
        redis_client=None,
        settings=_settings(hard_caps=True),
    )
    assert (await empty_service.check_budget_for_start(workspace_id, Decimal("1"))).allowed

    budget = BudgetRow(
        workspace_id=workspace_id,
        period_type="monthly",
        budget_cents=100,
        hard_cap_enabled=True,
    )
    repository = FakeBudgetRepository(budget)
    repository.spend = Decimal("99")
    disabled_service = BudgetService(
        repository=repository,  # type: ignore[arg-type]
        redis_client=None,
        settings=_settings(hard_caps=False),
    )

    result = await disabled_service.check_budget_for_start(workspace_id, Decimal("5"))

    assert result.allowed is True
    assert result.projected_spend_cents == Decimal("104")


@pytest.mark.asyncio
async def test_budget_no_redis_paths_and_period_helpers() -> None:
    workspace_id = uuid4()
    budget = BudgetRow(
        workspace_id=workspace_id,
        period_type="monthly",
        budget_cents=100,
        hard_cap_enabled=True,
    )
    repository = FakeBudgetRepository(budget)
    repository.spend = Decimal("90")
    service = BudgetService(
        repository=repository,  # type: ignore[arg-type]
        redis_client=None,
        settings=_settings(hard_caps=True),
    )
    period_start, period_end = period_bounds("monthly")

    await service.redeem_override("manual", redeemed_by=uuid4())
    await service.invalidate_hot_counter(workspace_id, "monthly")
    admitted, projected = await service._atomic_admit(
        budget, period_start, period_end, Decimal("5")
    )

    assert admitted is True
    assert projected == Decimal("90")
    assert await service._mark_exceeded_event_once(budget, period_start, period_end) is True
    assert period_bounds("weekly", datetime(2026, 4, 29, 12, tzinfo=UTC))[0].day == 27
    assert period_bounds("monthly", datetime(2026, 12, 15, 12, tzinfo=UTC))[1].year == 2027
    assert repository.redeemed_tokens


class NoneClientRedis:
    client: None = None

    async def initialize(self) -> None:
        return None


class FallbackRedis:
    def __init__(self, result: Any) -> None:
        self.client = self
        self.result = result
        self.values: dict[str, bytes] = {}

    async def initialize(self) -> None:
        return None

    async def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
        del ttl
        self.values[key] = value

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)

    async def script_load(self, source: str) -> str:
        del source
        return "sha"

    async def evalsha(self, sha: str, key_count: int, *args: str) -> Any:
        del sha, key_count, args
        raise RuntimeError("missing script")

    async def eval(self, source: str, key_count: int, *args: str) -> Any:
        del source, key_count, args
        return self.result


@pytest.mark.asyncio
async def test_budget_lua_fallback_paths() -> None:
    workspace_id = uuid4()
    budget = BudgetRow(
        workspace_id=workspace_id,
        period_type="monthly",
        budget_cents=100,
        hard_cap_enabled=True,
    )
    repository = FakeBudgetRepository(budget)
    repository.spend = Decimal("10")
    service = BudgetService(
        repository=repository,  # type: ignore[arg-type]
        redis_client=NoneClientRedis(),  # type: ignore[arg-type]
        settings=_settings(hard_caps=True),
    )
    assert await service._eval_lua("return 1", "_budget_script_sha", [], []) is None

    redis = FallbackRedis("not-a-list")
    service = BudgetService(
        repository=repository,  # type: ignore[arg-type]
        redis_client=redis,  # type: ignore[arg-type]
        settings=_settings(hard_caps=True),
    )
    period_start, period_end = period_bounds("monthly")
    admitted, projected = await service._atomic_admit(
        budget, period_start, period_end, Decimal("5")
    )
    redeemed = await service._redeem_override_atomic("token", "redeemed")

    assert admitted is True
    assert projected == Decimal("15")
    assert redeemed == b"not-a-list"
