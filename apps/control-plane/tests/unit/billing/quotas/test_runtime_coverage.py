from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from platform.billing.exceptions import (
    ModelTierNotAllowedError,
    NoActiveSubscriptionError,
    OverageCapExceededError,
    OverageRequiredError,
    QuotaExceededError,
    SubscriptionSuspendedError,
)
from platform.billing.plans.models import Plan, PlanVersion
from platform.billing.quotas import metering, reconciliation, usage_repository as usage_module
from platform.billing.quotas.enforcer import (
    QuotaEnforcer,
    _TTLCache,
    _PlanContext,
    _is_unlimited,
    _limit_failure,
    _model_allowed,
    _result,
    _usage_key,
)
from platform.billing.quotas.dependencies import build_quota_enforcer, get_quota_enforcer
from platform.billing.quotas.http import (
    quota_error_body,
    quota_result_to_http,
    raise_for_quota_result,
)
from platform.billing.quotas.models import OverageAuthorization, UsageRecord
from platform.billing.quotas.overage import OverageService
from platform.billing.quotas.schemas import QuotaCheckResult
from platform.billing.quotas.usage_repository import UsageRepository
from platform.billing.subscriptions.models import Subscription
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext, EventEnvelope
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

NOW = datetime(2026, 5, 1, tzinfo=UTC)


class _ScalarRows:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows


class _Result:
    def __init__(self, rows: list[Any] | None = None, scalar: Any = None) -> None:
        self._rows = rows or []
        self._scalar = scalar

    def one_or_none(self) -> Any | None:
        return self._rows[0] if self._rows else None

    def one(self) -> Any:
        return self._rows[0]

    def all(self) -> list[Any]:
        return self._rows

    def scalar_one(self) -> Any:
        return self._scalar

    def scalar_one_or_none(self) -> Any:
        return self._scalar

    def scalars(self) -> _ScalarRows:
        return _ScalarRows(self._rows)


class _Session:
    def __init__(
        self,
        *,
        execute_results: list[_Result] | None = None,
        scalar_results: list[Any] | None = None,
        get_values: dict[tuple[type[Any], UUID], Any] | None = None,
    ) -> None:
        self.execute_results = execute_results or []
        self.scalar_results = scalar_results or []
        self.get_values = get_values or {}
        self.added: list[Any] = []
        self.flushed = 0
        self.committed = False
        self.rolled_back = False

    async def execute(self, *args: Any, **kwargs: Any) -> _Result:
        del args, kwargs
        if self.execute_results:
            return self.execute_results.pop(0)
        return _Result()

    async def scalar(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        if self.scalar_results:
            return self.scalar_results.pop(0)
        return None

    async def get(self, model: type[Any], identifier: UUID) -> Any | None:
        return self.get_values.get((model, identifier))

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flushed += 1

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class _SessionContext(_Session):
    async def __aenter__(self) -> _SessionContext:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


class _Resolver:
    def __init__(self, subscription: Subscription | None) -> None:
        self.subscription = subscription

    async def resolve_active_subscription(self, workspace_id: UUID) -> Subscription:
        if self.subscription is None:
            raise NoActiveSubscriptionError(workspace_id)
        return self.subscription


class _Usage:
    def __init__(self, current: dict[str, Decimal] | None = None) -> None:
        self.current = current or {"executions": Decimal("0"), "minutes": Decimal("0")}
        self.increment_results: list[Decimal] = []
        self.invalidated: list[tuple[UUID, datetime]] = []

    async def get_current_usage(self, *args: Any) -> dict[str, Decimal]:
        del args
        return dict(self.current)

    async def increment(self, *args: Any, **kwargs: Any) -> Decimal:
        del args, kwargs
        return self.increment_results.pop(0)

    async def invalidate(self, subscription_id: UUID, period_start: datetime) -> None:
        self.invalidated.append((subscription_id, period_start))


class _Redis:
    def __init__(self, value: bytes | None = None) -> None:
        self.value = value
        self.deleted: list[str] = []
        self.sets: list[tuple[str, bytes, int | None]] = []
        self.client = SimpleNamespace(published=[])

        async def publish(channel: str, payload: str) -> None:
            self.client.published.append((channel, payload))

        self.client.publish = publish

    async def get(self, key: str) -> bytes | None:
        del key
        return self.value

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
        self.sets.append((key, value, ttl))

    async def delete(self, key: str) -> None:
        self.deleted.append(key)


class _Producer:
    def __init__(self) -> None:
        self.events: list[tuple[Any, ...]] = []

    async def publish(self, *args: Any) -> None:
        self.events.append(args)


class _PaymentProvider:
    def __init__(self) -> None:
        self.usage_reports: list[tuple[str, Decimal, str]] = []

    async def report_usage(self, subscription_id: str, quantity: Decimal, idempotency_key: str) -> None:
        self.usage_reports.append((subscription_id, quantity, idempotency_key))


class _ResumeService:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, datetime]] = []

    async def resume_paused_quota_exceeded(
        self,
        workspace_id: UUID,
        billing_period_start: datetime,
    ) -> None:
        self.calls.append((workspace_id, billing_period_start))


def _plan(
    *,
    slug: str = "pro",
    tier: str = "pro",
    allowed_model_tier: str = "standard",
) -> Plan:
    return Plan(
        id=uuid4(),
        slug=slug,
        display_name=slug.title(),
        description=None,
        tier=tier,
        is_public=True,
        is_active=True,
        allowed_model_tier=allowed_model_tier,
        created_at=NOW,
    )


def _version(
    plan: Plan,
    *,
    executions_per_month: int = 5,
    minutes_per_month: int = 10,
    max_workspaces: int = 2,
    max_agents_per_workspace: int = 5,
    max_users_per_workspace: int = 3,
    overage_price_per_minute: Decimal = Decimal("0.0000"),
) -> PlanVersion:
    return PlanVersion(
        id=uuid4(),
        plan_id=plan.id,
        version=1,
        price_monthly=Decimal("19.00"),
        executions_per_day=executions_per_month,
        executions_per_month=executions_per_month,
        minutes_per_day=minutes_per_month,
        minutes_per_month=minutes_per_month,
        max_workspaces=max_workspaces,
        max_agents_per_workspace=max_agents_per_workspace,
        max_users_per_workspace=max_users_per_workspace,
        overage_price_per_minute=overage_price_per_minute,
        trial_days=0,
        quota_period_anchor="calendar_month",
        extras_json={},
        published_at=NOW,
        created_at=NOW,
    )


def _subscription(plan: Plan, *, status: str = "active") -> Subscription:
    return Subscription(
        id=uuid4(),
        tenant_id=uuid4(),
        scope_type="workspace",
        scope_id=uuid4(),
        plan_id=plan.id,
        plan_version=1,
        status=status,
        current_period_start=NOW,
        current_period_end=NOW + timedelta(days=30),
        cancel_at_period_end=False,
    )


def _authorization(
    subscription: Subscription,
    *,
    workspace_id: UUID | None = None,
    max_overage_eur: Decimal | None = Decimal("5.00"),
) -> OverageAuthorization:
    return OverageAuthorization(
        id=uuid4(),
        tenant_id=subscription.tenant_id,
        workspace_id=workspace_id or subscription.scope_id,
        subscription_id=subscription.id,
        billing_period_start=subscription.current_period_start,
        billing_period_end=subscription.current_period_end,
        authorized_at=NOW,
        authorized_by_user_id=uuid4(),
        max_overage_eur=max_overage_eur,
    )


def _enforcer(
    *,
    plan: Plan,
    version: PlanVersion,
    subscription: Subscription | None,
    usage: dict[str, Decimal] | None = None,
    execute_results: list[_Result] | None = None,
    scalar_results: list[Any] | None = None,
    redis_client: Any | None = None,
) -> QuotaEnforcer:
    session = _Session(
        execute_results=[_Result(rows=[(plan, version)]), *(execute_results or [])],
        scalar_results=scalar_results,
    )
    return QuotaEnforcer(
        session=session,  # type: ignore[arg-type]
        settings=PlatformSettings(BILLING_QUOTA_CACHE_TTL_SECONDS=60),
        resolver=_Resolver(subscription),  # type: ignore[arg-type]
        usage_repository=_Usage(usage),  # type: ignore[arg-type]
        redis_client=redis_client,
    )


@pytest.mark.asyncio
async def test_quota_enforcer_execution_decisions_cover_limits_and_overage() -> None:
    plan = _plan()
    subscription = _subscription(plan)

    ok = await _enforcer(
        plan=plan,
        version=_version(plan, executions_per_month=2),
        subscription=subscription,
        usage={"executions": Decimal("0"), "minutes": Decimal("1")},
    ).check_execution(subscription.scope_id)
    assert ok.decision == "OK"

    hard_cap = await _enforcer(
        plan=plan,
        version=_version(plan, executions_per_month=1, minutes_per_month=1),
        subscription=subscription,
        usage={"executions": Decimal("1"), "minutes": Decimal("1")},
    ).check_execution(subscription.scope_id)
    assert hard_cap.decision == "HARD_CAP_EXCEEDED"

    suspended = await _enforcer(
        plan=plan,
        version=_version(plan),
        subscription=_subscription(plan, status="suspended"),
    ).check_execution(subscription.scope_id)
    assert suspended.decision == "SUSPENDED"

    missing = await _enforcer(
        plan=plan,
        version=_version(plan),
        subscription=None,
    ).check_execution(subscription.scope_id)
    assert missing.decision == "NO_ACTIVE_SUBSCRIPTION"

    unlimited = await _enforcer(
        plan=plan,
        version=_version(
            plan,
            executions_per_month=0,
            minutes_per_month=0,
            max_workspaces=0,
            max_agents_per_workspace=0,
            max_users_per_workspace=0,
        ),
        subscription=subscription,
    ).check_execution(subscription.scope_id)
    assert unlimited.decision == "OK"

    overage_required = await _enforcer(
        plan=plan,
        version=_version(
            plan,
            executions_per_month=1,
            minutes_per_month=1,
            overage_price_per_minute=Decimal("0.50"),
        ),
        subscription=subscription,
        usage={"executions": Decimal("1"), "minutes": Decimal("2")},
        execute_results=[_Result()],
    ).check_execution(subscription.scope_id)
    assert overage_required.decision == "OVERAGE_REQUIRED"

    overage_authorized = await _enforcer(
        plan=plan,
        version=_version(
            plan,
            executions_per_month=10,
            minutes_per_month=1,
            overage_price_per_minute=Decimal("0.50"),
        ),
        subscription=subscription,
        usage={"executions": Decimal("1"), "minutes": Decimal("2")},
        execute_results=[_Result(rows=[(None,)])],
    ).check_execution(subscription.scope_id)
    assert overage_authorized.decision == "OVERAGE_AUTHORIZED"

    overage_cap = await _enforcer(
        plan=plan,
        version=_version(
            plan,
            executions_per_month=10,
            minutes_per_month=1,
            overage_price_per_minute=Decimal("0.50"),
        ),
        subscription=subscription,
        usage={"executions": Decimal("1"), "minutes": Decimal("4")},
        execute_results=[_Result(rows=[(Decimal("0.50"),)])],
        scalar_results=[Decimal("0")],
    ).check_execution(subscription.scope_id)
    assert overage_cap.decision == "OVERAGE_CAP_EXCEEDED"


@pytest.mark.asyncio
async def test_quota_enforcer_workspace_agent_user_model_and_cache_paths() -> None:
    plan = _plan(allowed_model_tier="standard")
    version = _version(plan, max_workspaces=1, max_agents_per_workspace=5, max_users_per_workspace=2)
    subscription = _subscription(plan)
    redis = _Redis(json.dumps({"executions": "1", "minutes": "2.5"}).encode())
    enforcer = _enforcer(
        plan=plan,
        version=version,
        subscription=subscription,
        scalar_results=[subscription.scope_id, 1, 4, 2],
        redis_client=redis,
    )

    workspace_create = await enforcer.check_workspace_create(uuid4())
    agent_publish = await enforcer.check_agent_publish(subscription.scope_id)
    user_invite = await enforcer.check_user_invite(subscription.scope_id)
    model_tier = await enforcer.check_model_tier(subscription.scope_id, "expensive", "tier1")
    cached_usage = await enforcer._usage(subscription, subscription.scope_id)
    await enforcer.invalidate_workspace(subscription.scope_id)

    assert workspace_create.decision == "HARD_CAP_EXCEEDED"
    assert agent_publish.decision == "OK"
    assert user_invite.decision == "HARD_CAP_EXCEEDED"
    assert model_tier.decision == "MODEL_TIER_NOT_ALLOWED"
    assert cached_usage == {"executions": Decimal("1"), "minutes": Decimal("2.5")}
    assert redis.deleted == [f"quota:plan_version:{subscription.scope_id}"]


@pytest.mark.asyncio
async def test_quota_private_helpers_cover_cache_limits_and_model_lookup() -> None:
    cache = _TTLCache(maxsize=1, ttl_seconds=60)
    cache.set("a", 1)
    cache.set("b", 2)
    assert cache.get("a") is None
    assert cache.get("b") == 2
    cache.delete_prefix("b")
    assert cache.get("b") is None
    expired = _TTLCache(maxsize=1, ttl_seconds=0)
    expired.set("old", object())
    assert expired.get("old") is None

    plan = _plan()
    version = _version(plan)
    subscription = _subscription(plan)
    context = _PlanContext(subscription=subscription, plan=plan, version=version)
    enforcer = _enforcer(plan=plan, version=version, subscription=subscription)
    enforcer.local_cache.set(f"{subscription.scope_id}:plan_context", context)
    assert await enforcer._plan_context(subscription.scope_id) == context

    no_row = _enforcer(
        plan=plan,
        version=version,
        subscription=subscription,
        execute_results=[],
    )
    no_row.session.execute_results = [_Result()]
    assert await no_row._plan_context(uuid4()) is None

    model_session = _Session(execute_results=[_Result(scalar="tier2"), _Result(scalar=None)])
    model_enforcer = QuotaEnforcer(
        session=model_session,  # type: ignore[arg-type]
        settings=PlatformSettings(),
        resolver=_Resolver(subscription),  # type: ignore[arg-type]
    )
    assert await model_enforcer._model_quality_tier("openai:gpt") == "tier2"
    assert await model_enforcer._model_quality_tier("unknown") == "tier1"
    assert _is_unlimited(
        _version(
            plan,
            executions_per_month=0,
            minutes_per_month=0,
            max_workspaces=0,
            max_agents_per_workspace=0,
            max_users_per_workspace=0,
        )
    )
    assert _limit_failure("minutes", Decimal("2"), Decimal("1")) == (
        "minutes",
        Decimal("2"),
        Decimal("1"),
    )
    assert _limit_failure("minutes", Decimal("1"), Decimal("1")) is None
    assert _model_allowed("all", "tier1")
    assert _model_allowed("standard", "tier2")
    assert not _model_allowed("cheap_only", "tier1")
    assert _usage_key(subscription).startswith(f"quota:usage:{subscription.id}:")


@pytest.mark.asyncio
async def test_metering_process_event_helpers_and_overage_reporting(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _plan()
    version = _version(plan, minutes_per_month=1, overage_price_per_minute=Decimal("0.25"))
    subscription = _subscription(plan)
    event_id = uuid4()
    payment = _PaymentProvider()

    class _MeteringResolver:
        def __init__(self, session: Any) -> None:
            del session

        async def resolve_active_subscription(self, workspace_id: UUID) -> Subscription:
            assert workspace_id == subscription.scope_id
            return subscription

    monkeypatch.setattr(metering, "SubscriptionResolver", _MeteringResolver)
    session = _Session(
        execute_results=[
            _Result(scalar=event_id),
            _Result(),
            _Result(rows=[(plan, version)]),
        ],
    )
    job = metering.MeteringJob(
        session=session,  # type: ignore[arg-type]
        settings=PlatformSettings(),
        payment_provider=payment,  # type: ignore[arg-type]
    )
    usage = _Usage()
    usage.increment_results = [Decimal("1"), Decimal("2.0000"), Decimal("1.0000")]
    job.usage = usage  # type: ignore[assignment]
    envelope = EventEnvelope(
        event_type="execution.compute.end",
        source="pytest",
        correlation_context=CorrelationContext(
            correlation_id=uuid4(),
            tenant_id=subscription.tenant_id,
            workspace_id=subscription.scope_id,
            execution_id=event_id,
        ),
        occurred_at=NOW,
        payload={
            "active_started_at": "2026-05-01T00:00:00Z",
            "active_ended_at": "2026-05-01T00:02:00Z",
        },
    )

    result = await job.process_event(envelope)
    duplicate = metering.MeteringJob(
        session=_Session(execute_results=[_Result(scalar=None)]),  # type: ignore[arg-type]
        settings=PlatformSettings(),
    )
    duplicate.usage = usage  # type: ignore[assignment]
    ignored = await metering.MeteringJob(settings=PlatformSettings()).process_event(
        envelope.model_copy(update={"event_type": "other.event"})
    )

    assert result.processed is True
    assert result.minutes == Decimal("2.0000")
    assert result.overage_minutes == Decimal("1.0000")
    assert payment.usage_reports == [
        (f"stub_sub_{subscription.id.hex[:24]}", Decimal("1.0000"), str(event_id))
    ]
    assert (await duplicate.process_event(envelope)).processed is False
    assert ignored.processed is False
    with pytest.raises(RuntimeError):
        await metering.MeteringJob(settings=PlatformSettings()).process_event(envelope)
    with pytest.raises(ValueError):
        metering._workspace_id(
            envelope.model_copy(
                update={"correlation_context": CorrelationContext(correlation_id=uuid4())}
            )
        )
    assert metering._event_id(envelope.model_copy(update={"payload": {"event_id": "not-a-uuid"}}))
    assert metering._timestamp("2026-05-01T00:00:00").tzinfo is UTC
    assert metering._minutes_between(NOW, NOW - timedelta(minutes=1)) == Decimal("0.0000")
    assert (
        metering._new_overage_minutes(
            previous=Decimal("1"),
            current=Decimal("3"),
            included_limit=Decimal("2"),
            overage_price=Decimal("0.1"),
        )
        == Decimal("1.0000")
    )


@pytest.mark.asyncio
async def test_overage_service_authorize_revoke_and_current_amount() -> None:
    plan = _plan()
    subscription = _subscription(plan)
    authorization = _authorization(subscription, max_overage_eur=Decimal("2.50"))
    producer = _Producer()
    resume_service = _ResumeService()
    session = _Session(
        execute_results=[
            _Result(scalar=authorization),
            _Result(scalar=authorization),
            _Result(scalar=authorization),
        ],
        get_values={(Subscription, subscription.id): subscription},
        scalar_results=[_version(plan, overage_price_per_minute=Decimal("0.50")), Decimal("3")],
    )
    service = OverageService(
        session=session,  # type: ignore[arg-type]
        resolver=_Resolver(subscription),  # type: ignore[arg-type]
        execution_service=resume_service,
        producer=producer,  # type: ignore[arg-type]
    )

    created = await service.authorize(
        subscription.scope_id,
        None,
        Decimal("2.50"),
        authorization.authorized_by_user_id,
    )
    assert await service.is_authorized_for_period(
        subscription.scope_id,
        subscription.current_period_start,
    )
    revoked = await service.revoke(authorization.id, uuid4())
    amount = await service.current_overage_eur(subscription.id, subscription.current_period_start)

    assert created is authorization
    assert revoked is authorization
    assert amount == Decimal("1.50")
    assert resume_service.calls == [(subscription.scope_id, subscription.current_period_start)]
    assert [event[2] for event in producer.events] == [
        "billing.overage.authorized",
        "billing.overage.revoked",
    ]


@pytest.mark.asyncio
async def test_usage_repository_increment_history_and_redis_invalidation() -> None:
    plan = _plan()
    subscription = _subscription(plan)
    redis = _Redis()
    usage_row = UsageRecord(
        id=uuid4(),
        tenant_id=subscription.tenant_id,
        workspace_id=subscription.scope_id,
        subscription_id=subscription.id,
        metric="minutes",
        period_start=subscription.current_period_start,
        period_end=subscription.current_period_end,
        quantity=Decimal("3.5"),
        is_overage=False,
    )
    session = _Session(
        execute_results=[
            _Result(scalar=Decimal("2.5")),
            _Result(rows=[("executions", Decimal("2")), ("minutes", Decimal("3.5"))]),
            _Result(rows=[usage_row]),
        ],
        get_values={(Subscription, subscription.id): subscription},
    )
    repository = UsageRepository(session, redis)  # type: ignore[arg-type]

    total = await repository.increment(
        subscription.id,
        subscription.current_period_start,
        "minutes",
        Decimal("2.5"),
        False,
        tenant_id=subscription.tenant_id,
    )
    current = await repository.get_current_usage(
        subscription.id,
        subscription.current_period_start,
    )
    history = await repository.get_period_history(subscription.id)

    assert total == Decimal("2.5")
    assert current == {"executions": Decimal("2"), "minutes": Decimal("3.5")}
    assert history == [usage_row]
    assert redis.deleted == [
        f"quota:usage:{subscription.id}:{subscription.current_period_start.isoformat()}"
    ]
    assert redis.client.published
    with pytest.raises(ValueError):
        await UsageRepository(_Session()).increment(  # type: ignore[arg-type]
            subscription.id,
            subscription.current_period_start,
            "minutes",
            Decimal("1"),
            False,
        )
    await UsageRepository(_Session()).invalidate(subscription.id, subscription.current_period_start)  # type: ignore[arg-type]
    await UsageRepository(_Session(), SimpleNamespace()).invalidate(  # type: ignore[arg-type]
        subscription.id,
        subscription.current_period_start,
    )
    tenant_id = uuid4()
    token = usage_module.current_tenant.set(SimpleNamespace(id=tenant_id))
    try:
        assert usage_module._tenant_id() == tenant_id
    finally:
        usage_module.current_tenant.reset(token)
    with pytest.raises(RuntimeError):
        usage_module._tenant_id()


@pytest.mark.asyncio
async def test_reconciliation_job_counts_missing_events_and_scheduler_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    processed = uuid4()
    missing = uuid4()
    session = _Session(execute_results=[_Result(rows=[processed])])
    result = await reconciliation.BillingReconciliationJob(session=session).run_once(
        [processed, missing]
    )
    empty = await reconciliation.BillingReconciliationJob(session=session).run_once([])

    assert result.expected_count == 2
    assert result.missing_count == 1
    assert result.mismatch_rate == 0.5
    assert empty.expected_count == 0

    context = _SessionContext()
    monkeypatch.setattr(
        reconciliation.database,
        "PlatformStaffAsyncSessionLocal",
        lambda: context,
    )
    assert await reconciliation.run_billing_reconciliation(SimpleNamespace()) == empty
    assert reconciliation.build_billing_reconciliation_scheduler(
        SimpleNamespace(state=SimpleNamespace(settings=object()))
    ) is None
    monkeypatch.setattr(
        reconciliation,
        "__import__",
        lambda *args, **kwargs: (_ for _ in ()).throw(ImportError("missing")),
        raising=False,
    )
    assert reconciliation.build_billing_reconciliation_scheduler(
        SimpleNamespace(state=SimpleNamespace(settings=PlatformSettings()))
    ) is None

    class _Scheduler:
        def __init__(self, timezone: str) -> None:
            self.timezone = timezone
            self.jobs: list[tuple[object, str, dict[str, object]]] = []

        def add_job(self, func: object, trigger: str, **kwargs: object) -> None:
            self.jobs.append((func, trigger, kwargs))

    monkeypatch.setattr(
        reconciliation,
        "__import__",
        lambda *args, **kwargs: SimpleNamespace(AsyncIOScheduler=_Scheduler),
        raising=False,
    )
    scheduler = reconciliation.build_billing_reconciliation_scheduler(
        SimpleNamespace(state=SimpleNamespace(settings=PlatformSettings()))
    )
    assert scheduler.timezone == "UTC"
    assert scheduler.jobs[0][1] == "cron"
    assert scheduler.jobs[0][2]["id"] == "billing.reconciliation"

    async def _empty_run(app: object) -> reconciliation.ReconciliationResult:
        del app
        return empty

    monkeypatch.setattr(reconciliation, "run_billing_reconciliation", _empty_run)
    assert await scheduler.jobs[0][0]() is None


@pytest.mark.asyncio
async def test_quota_enforcer_additional_resource_and_cache_branches() -> None:
    plan = _plan(allowed_model_tier="all")
    version = _version(plan, max_agents_per_workspace=1, max_users_per_workspace=3)
    subscription = _subscription(plan)

    no_workspace = _enforcer(
        plan=plan,
        version=version,
        subscription=subscription,
        scalar_results=[None],
    )
    assert (await no_workspace.check_workspace_create(uuid4())).decision == "OK"
    workspace_ok = _enforcer(
        plan=plan,
        version=version,
        subscription=subscription,
        scalar_results=[subscription.scope_id, 0],
    )
    assert (await workspace_ok.check_workspace_create(uuid4())).decision == "OK"

    no_agent_subscription = _enforcer(plan=plan, version=version, subscription=None)
    assert (
        await no_agent_subscription.check_agent_publish(subscription.scope_id)
    ).decision == "NO_ACTIVE_SUBSCRIPTION"
    unlimited = _version(
        plan,
        executions_per_month=0,
        minutes_per_month=0,
        max_workspaces=0,
        max_agents_per_workspace=0,
        max_users_per_workspace=0,
    )
    assert (
        await _enforcer(plan=plan, version=unlimited, subscription=subscription).check_agent_publish(
            subscription.scope_id
        )
    ).decision == "OK"

    agent_cap = _enforcer(
        plan=plan,
        version=version,
        subscription=subscription,
        scalar_results=[1],
    )
    assert (await agent_cap.check_agent_publish(subscription.scope_id)).decision == (
        "HARD_CAP_EXCEEDED"
    )

    user_ok = _enforcer(
        plan=plan,
        version=version,
        subscription=subscription,
        scalar_results=[1],
    )
    assert (await user_ok.check_user_invite(subscription.scope_id)).decision == "OK"
    assert (
        await _enforcer(plan=plan, version=unlimited, subscription=subscription).check_user_invite(
            subscription.scope_id
        )
    ).decision == "OK"
    assert (await _enforcer(plan=plan, version=version, subscription=None).check_user_invite(
        subscription.scope_id
    )).decision == "NO_ACTIVE_SUBSCRIPTION"
    assert (
        await _enforcer(plan=plan, version=version, subscription=None).check_model_tier(
            subscription.scope_id,
            "any-model",
        )
    ).decision == "NO_ACTIVE_SUBSCRIPTION"
    assert (
        await _enforcer(plan=plan, version=version, subscription=subscription).check_model_tier(
            subscription.scope_id,
            "any-model",
        )
    ).decision == "OK"

    redis_without_methods = SimpleNamespace()
    cache_enforcer = _enforcer(
        plan=plan,
        version=version,
        subscription=subscription,
        redis_client=redis_without_methods,
    )
    assert await cache_enforcer._redis_usage(subscription) is None
    await cache_enforcer._set_redis_usage(
        subscription,
        {"executions": Decimal("1"), "minutes": Decimal("1")},
    )
    await _enforcer(plan=plan, version=version, subscription=subscription).invalidate_workspace(
        subscription.scope_id
    )
    cache_enforcer.redis_client = _Redis()
    assert await cache_enforcer._redis_usage(subscription) is None
    await cache_enforcer._set_redis_usage(
        subscription,
        {"executions": Decimal("1"), "minutes": Decimal("1")},
    )
    assert cache_enforcer.redis_client.sets


@pytest.mark.asyncio
async def test_quota_dependency_builders() -> None:
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(settings=PlatformSettings(), clients={"redis": _Redis()})
        )
    )
    built = build_quota_enforcer(
        session=_Session(),  # type: ignore[arg-type]
        settings=PlatformSettings(),
        redis_client=_Redis(),  # type: ignore[arg-type]
    )
    depended = await get_quota_enforcer(request, _Session())  # type: ignore[arg-type]

    assert isinstance(built, QuotaEnforcer)
    assert isinstance(depended, QuotaEnforcer)


@pytest.mark.asyncio
async def test_overage_conflict_reactivation_and_empty_paths() -> None:
    plan = _plan()
    subscription = _subscription(plan)
    revoked = _authorization(subscription)
    revoked.revoked_at = NOW
    revoked.revoked_by_user_id = uuid4()
    session = _Session(
        execute_results=[_Result(scalar=None), _Result(scalar=revoked), _Result(scalar=None)],
        get_values={(Subscription, subscription.id): subscription},
        scalar_results=[None],
    )
    service = OverageService(
        session=session,  # type: ignore[arg-type]
        resolver=_Resolver(subscription),  # type: ignore[arg-type]
    )

    restored = await service.authorize(
        subscription.scope_id,
        subscription.current_period_start,
        Decimal("9.00"),
        uuid4(),
    )
    assert restored.revoked_at is None
    assert restored.max_overage_eur == Decimal("9.00")
    with pytest.raises(NoActiveSubscriptionError):
        await service.revoke(uuid4(), uuid4())
    assert await service.current_overage_eur(uuid4(), NOW) == Decimal("0")

    missing_conflict = OverageService(
        session=_Session(execute_results=[_Result(scalar=None), _Result(scalar=None)]),  # type: ignore[arg-type]
        resolver=_Resolver(subscription),  # type: ignore[arg-type]
    )
    with pytest.raises(NoActiveSubscriptionError):
        await missing_conflict.authorize(
            subscription.scope_id,
            subscription.current_period_start,
            None,
            uuid4(),
        )


@pytest.mark.asyncio
async def test_metering_handle_event_commit_and_rollback_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    envelope = EventEnvelope(
        event_type="execution.compute.end",
        source="pytest",
        correlation_context=CorrelationContext(correlation_id=uuid4(), workspace_id=uuid4()),
        payload={},
    )
    context = _SessionContext()
    original_job_class = metering.MeteringJob

    class _SuccessfulJob:
        def __init__(self, **kwargs: object) -> None:
            del kwargs

        async def process_event(self, envelope_arg: EventEnvelope) -> None:
            assert envelope_arg is envelope

    monkeypatch.setattr(metering.database, "AsyncSessionLocal", lambda: context)
    monkeypatch.setattr(metering, "MeteringJob", _SuccessfulJob)
    await original_job_class(settings=PlatformSettings()).handle_event(envelope)
    assert context.committed is True

    class _FailingJob:
        def __init__(self, **kwargs: object) -> None:
            del kwargs

        async def process_event(self, envelope_arg: EventEnvelope) -> None:
            del envelope_arg
            raise RuntimeError("boom")

    failing_context = _SessionContext()
    monkeypatch.setattr(metering.database, "AsyncSessionLocal", lambda: failing_context)
    monkeypatch.setattr(metering, "MeteringJob", _FailingJob)
    with pytest.raises(RuntimeError):
        await original_job_class(settings=PlatformSettings()).handle_event(envelope)
    assert failing_context.rolled_back is True

    class _Manager:
        def __init__(self) -> None:
            self.subscriptions: list[tuple[object, ...]] = []

        def subscribe(self, *args: object) -> None:
            self.subscriptions.append(args)

    manager = _Manager()
    original_job_class(settings=PlatformSettings()).register(manager)  # type: ignore[arg-type]
    assert manager.subscriptions[0][0] == "execution.compute.end"
    assert metering._uuid(envelope.correlation_context.workspace_id) == (
        envelope.correlation_context.workspace_id
    )
    assert metering._uuid(str(envelope.correlation_context.workspace_id)) == (
        envelope.correlation_context.workspace_id
    )
    assert metering._uuid(None) is None
    with pytest.raises(RuntimeError):
        await original_job_class(settings=PlatformSettings())._mark_processed(uuid4())
    with pytest.raises(RuntimeError):
        await original_job_class(settings=PlatformSettings())._plan_context(_subscription(_plan()))
    with pytest.raises(ValueError):
        metering._timestamp(None)
    assert (
        metering._new_overage_minutes(
            previous=Decimal("0"),
            current=Decimal("10"),
            included_limit=Decimal("0"),
            overage_price=Decimal("0.25"),
        )
        == Decimal("0")
    )


def test_quota_http_error_mapping_and_exception_types() -> None:
    workspace_id = uuid4()
    hard_cap = _result(
        "HARD_CAP_EXCEEDED",
        quota_name="minutes",
        current=Decimal("3"),
        limit=Decimal("2"),
        workspace_id=workspace_id,
        overage_available=True,
    )
    overage_required = _result(
        "OVERAGE_REQUIRED",
        quota_name="minutes",
        current=Decimal("3.5"),
        limit=Decimal("2"),
        workspace_id=workspace_id,
        overage_available=True,
    )

    assert quota_result_to_http(_result("OK")) is None
    assert raise_for_quota_result(_result("OK")) is None
    assert quota_result_to_http(overage_required).status_code == 202
    assert quota_result_to_http(hard_cap).detail["details"]["current"] == 3
    assert quota_error_body(overage_required)["status"] == "paused_quota_exceeded"
    assert quota_error_body(hard_cap)["code"] == "quota_exceeded"
    fractional = _result(
        "HARD_CAP_EXCEEDED",
        quota_name="minutes",
        current=Decimal("3.5"),
        limit=2,
        workspace_id=workspace_id,
        message="custom",
    )
    assert quota_error_body(fractional)["details"]["current"] == 3.5
    unknown = QuotaCheckResult.model_construct(decision="UNKNOWN", message=None)
    assert quota_result_to_http(unknown).detail["code"] == "unknown"
    with pytest.raises(QuotaExceededError):
        raise_for_quota_result(hard_cap, workspace_id=workspace_id)
    with pytest.raises(ModelTierNotAllowedError):
        raise_for_quota_result(_result("MODEL_TIER_NOT_ALLOWED"), workspace_id=workspace_id)
    with pytest.raises(OverageCapExceededError):
        raise_for_quota_result(_result("OVERAGE_CAP_EXCEEDED"), workspace_id=workspace_id)
    with pytest.raises(OverageRequiredError):
        raise_for_quota_result(overage_required, workspace_id=workspace_id)
    with pytest.raises(NoActiveSubscriptionError):
        raise_for_quota_result(_result("NO_ACTIVE_SUBSCRIPTION"), workspace_id=workspace_id)
    with pytest.raises(SubscriptionSuspendedError):
        raise_for_quota_result(_result("SUSPENDED"), workspace_id=workspace_id)
    with pytest.raises(Exception):
        raise_for_quota_result(unknown, workspace_id=workspace_id)
