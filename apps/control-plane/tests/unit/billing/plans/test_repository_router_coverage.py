from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from platform.billing.exceptions import (
    PlanNotFoundError,
    PlanVersionImmutableError,
    PlanVersionInProgressError,
)
from platform.billing.plans import admin_router, public_router
from platform.billing.plans.models import Plan, PlanVersion
from platform.billing.plans.repository import PlansRepository, _coerce_version_values
from platform.billing.plans.schemas import PlanCreate, PlanUpdate, PlanVersionPublish
from platform.billing.plans.service import PlansService, _jsonable
from platform.common.config import PlatformSettings
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException, Response
from sqlalchemy.exc import IntegrityError

from tests.unit.billing.quotas.test_runtime_coverage import _Result, _Session, _plan, _version


class _Audit:
    def __init__(self) -> None:
        self.events: list[tuple[object, ...]] = []

    async def append(self, *args: object, **kwargs: object) -> None:
        self.events.append((*args, kwargs))


class _Producer:
    def __init__(self) -> None:
        self.events: list[tuple[object, ...]] = []

    async def publish(self, *args: object) -> None:
        self.events.append(args)


class _RouterRepo:
    plan = _plan(slug="pro", tier="pro")
    prior = _version(plan, executions_per_month=100)
    prior.version = 1
    prior.deprecated_at = datetime(2026, 5, 1, tzinfo=UTC)
    current = _version(plan, executions_per_month=200)
    current.version = 2

    def __init__(self, session: object) -> None:
        del session
        self.created: list[Plan] = []

    async def list_filtered(
        self,
        *,
        tier: str | None = None,
        is_active: bool | None = None,
        is_public: bool | None = None,
    ) -> list[Plan]:
        assert tier == "pro"
        assert is_active is True
        assert is_public is True
        return [self.plan]

    async def list_public(self) -> list[Plan]:
        return [self.plan, _plan(slug="draft", tier="free")]

    async def create_plan(self, **kwargs: object) -> Plan:
        plan = Plan(id=uuid4(), created_at=datetime(2026, 5, 1, tzinfo=UTC), **kwargs)
        self.created.append(plan)
        return plan

    async def get_by_slug(self, slug: str) -> Plan | None:
        return self.plan if slug == self.plan.slug else None

    async def list_versions(self, plan_id: object) -> list[PlanVersion]:
        del plan_id
        return [self.current, self.prior]

    async def get_published_version(self, plan_id: object) -> PlanVersion | None:
        del plan_id
        return self.current

    async def count_subscriptions_for_plan(self, plan_id: object) -> int:
        del plan_id
        return 3

    async def count_subscriptions_on_version(self, plan_id: object, version: int) -> int:
        del plan_id
        return version

    async def publish_new_version(
        self,
        plan: Plan,
        parameters: dict[str, object],
        *,
        created_by: object = None,
    ) -> tuple[PlanVersion | None, PlanVersion]:
        del parameters, created_by
        new_version = _version(plan, executions_per_month=300)
        new_version.version = 3
        return self.current, new_version

    async def deprecate_version(self, plan_id: object, version: int) -> PlanVersion | None:
        del plan_id, version
        return self.current

    async def update_plan(self, plan: Plan, **kwargs: object) -> Plan:
        for key, value in kwargs.items():
            if value is not None:
                setattr(plan, key, value)
        return plan


@pytest.mark.asyncio
async def test_plans_repository_methods_cover_query_and_mutation_paths() -> None:
    plan = _plan(slug="free", tier="free")
    current = _version(plan)
    existing = _version(plan)
    session = _Session(
        execute_results=[
            _Result(scalar=plan),
            _Result(rows=[plan]),
            _Result(rows=[plan]),
            _Result(rows=[plan]),
            _Result(rows=[plan]),
            _Result(scalar=current),
            _Result(rows=[current, existing]),
            _Result(scalar=True),
            _Result(scalar=current),
            _Result(scalar=existing),
            _Result(scalar=7),
            _Result(scalar=8),
        ]
    )
    repository = PlansRepository(session)  # type: ignore[arg-type]

    assert await repository.get_by_slug("free") is plan
    assert await repository.list_all() == [plan]
    assert await repository.list_filtered(tier="free", is_active=True, is_public=True) == [plan]
    assert await repository.list_filtered() == [plan]
    assert await repository.list_public() == [plan]
    created = await repository.create_plan(
        slug="team",
        display_name="Team",
        description=None,
        tier="pro",
        is_public=True,
        is_active=True,
        allowed_model_tier="standard",
    )
    updated = await repository.update_plan(
        created,
        display_name="Team Plus",
        description="desc",
        is_public=False,
        is_active=False,
        allowed_model_tier="all",
    )
    assert updated.display_name == "Team Plus"
    assert await repository.update_plan(updated) is updated
    assert await repository.get_published_version(plan.id) is current
    assert await repository.list_versions(plan.id) == [current, existing]
    prior, new_version = await repository.publish_new_version(
        plan,
        {"price_monthly": "1.25", "extras_json": {"x": 1}},
        created_by=uuid4(),
    )
    assert prior is current
    assert new_version.version == current.version + 1
    assert await repository.deprecate_version(plan.id, existing.version) is existing
    assert await repository.count_subscriptions_on_version(plan.id, existing.version) == 7
    assert await repository.count_subscriptions_for_plan(plan.id) == 8
    assert session.flushed >= 3
    with pytest.raises(PlanVersionInProgressError):
        await PlansRepository(_Session(execute_results=[_Result(scalar=False)])).publish_new_version(  # type: ignore[arg-type]
            plan,
            {},
        )
    fallback = _version(plan)
    assert (
        await PlansRepository(
            _Session(execute_results=[_Result(scalar=None), _Result(scalar=fallback)])
        ).deprecate_version(plan.id, fallback.version)  # type: ignore[arg-type]
        is fallback
    )
    assert _coerce_version_values({"price_monthly": "2.50", "extras_json": None}) == {
        "price_monthly": Decimal("2.50"),
        "extras_json": {},
    }


@pytest.mark.asyncio
async def test_plans_service_audit_event_and_guard_paths() -> None:
    audit = _Audit()
    producer = _Producer()
    service = PlansService(_RouterRepo(None), audit_chain=audit, producer=producer)  # type: ignore[arg-type]

    new_version = await service.publish_new_version(
        "pro",
        PlanVersionPublish(price_monthly=Decimal("39.00"), executions_per_month=500),
        actor_id=uuid4(),
        tenant_id=uuid4(),
    )
    deprecated = await service.deprecate_version(_RouterRepo.plan.id, 2, tenant_id=uuid4())
    updated = await service.update_plan_metadata("pro", PlanUpdate(display_name="Pro Plus"))
    draft = _version(_RouterRepo.plan)
    draft.published_at = None
    service.guard_published_version_update(draft, {"price_monthly": Decimal("1.00")})

    assert new_version.version == 3
    assert deprecated is _RouterRepo.current
    assert updated.display_name == "Pro Plus"
    assert audit.events
    assert producer.events
    with pytest.raises(PlanVersionImmutableError):
        service.guard_published_version_update(
            _RouterRepo.current,
            {"price_monthly": Decimal("1.00")},
        )
    with pytest.raises(PlanNotFoundError):
        await PlansService(_RouterRepo(None)).publish_new_version(  # type: ignore[arg-type]
            "missing",
            PlanVersionPublish(),
        )
    with pytest.raises(PlanNotFoundError):
        await PlansService(_RouterRepo(None)).update_plan_metadata(  # type: ignore[arg-type]
            "missing",
            PlanUpdate(display_name="Missing"),
        )
    await PlansService(_RouterRepo(None)).publish_new_version(  # type: ignore[arg-type]
        "pro",
        PlanVersionPublish(price_monthly=Decimal("59.00")),
    )
    assert _jsonable(date(2026, 5, 1)) == "2026-05-01"


@pytest.mark.asyncio
async def test_plan_admin_and_public_router_functions(monkeypatch: pytest.MonkeyPatch) -> None:
    producer = _Producer()
    original_event_producer = admin_router._event_producer
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(clients={"kafka": producer}, settings=PlatformSettings())
        )
    )
    monkeypatch.setattr(admin_router, "PlansRepository", _RouterRepo)
    monkeypatch.setattr(public_router, "PlansRepository", _RouterRepo)
    monkeypatch.setattr(admin_router, "_audit_chain_service", lambda *args: _Audit())
    monkeypatch.setattr(admin_router, "_event_producer", lambda request: producer)

    listed = await admin_router.list_plans("pro", True, True, object())  # type: ignore[arg-type]
    created = await admin_router.create_plan(
        PlanCreate(slug="team", display_name="Team", tier="pro"),
        object(),  # type: ignore[arg-type]
    )
    detail = await admin_router.get_plan("pro", object())  # type: ignore[arg-type]
    versions = await admin_router.list_plan_versions("pro", object())  # type: ignore[arg-type]
    published = await admin_router.publish_plan_version(
        "pro",
        PlanVersionPublish(price_monthly=Decimal("49.00")),
        request,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        {"sub": str(uuid4())},
    )
    deprecated = await admin_router.deprecate_plan_version(
        "pro",
        2,
        request,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
    )
    patched = await admin_router.update_plan_metadata(
        "pro",
        PlanUpdate(display_name="Pro Patched"),
        object(),  # type: ignore[arg-type]
    )
    response = Response()
    public = await public_router.list_public_plans(response, object())  # type: ignore[arg-type]

    class _PublicRepoNoVersion(_RouterRepo):
        async def get_published_version(self, plan_id: object) -> PlanVersion | None:
            del plan_id
            return None

    monkeypatch.setattr(public_router, "PlansRepository", _PublicRepoNoVersion)
    empty_public = await public_router.list_public_plans(Response(), object())  # type: ignore[arg-type]

    assert listed["items"][0]["active_subscription_count"] == 3
    assert created["slug"] == "team"
    assert detail["version_count"] == 2
    assert versions["items"][0]["subscription_count"] == 2
    assert published["version"] == 3
    assert deprecated["subscription_count"] == 2
    assert patched["display_name"] == "Pro Patched"
    assert public["plans"][0]["slug"] == "pro"
    assert empty_public["plans"] == []
    assert response.headers["Cache-Control"] == "public, max-age=60"
    with pytest.raises(PlanNotFoundError):
        await admin_router.get_plan("missing", object())  # type: ignore[arg-type]
    with pytest.raises(PlanNotFoundError):
        await admin_router.list_plan_versions("missing", object())  # type: ignore[arg-type]
    with pytest.raises(PlanNotFoundError):
        await admin_router.deprecate_plan_version(
            "missing",
            1,
            request,  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
        )

    class _MissingStoredRepo(_RouterRepo):
        async def deprecate_version(self, plan_id: object, version: int) -> PlanVersion | None:
            del plan_id, version
            return None

    monkeypatch.setattr(admin_router, "PlansRepository", _MissingStoredRepo)
    with pytest.raises(PlanNotFoundError):
        await admin_router.deprecate_plan_version(
            "pro",
            99,
            request,  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
        )

    class _ConflictRepo(_RouterRepo):
        async def create_plan(self, **kwargs: object) -> Plan:
            del kwargs
            raise IntegrityError("insert", {}, RuntimeError("duplicate"))

    monkeypatch.setattr(admin_router, "PlansRepository", _ConflictRepo)
    with pytest.raises(HTTPException) as conflict:
        await admin_router.create_plan(
            PlanCreate(slug="taken", display_name="Taken", tier="pro"),
            object(),  # type: ignore[arg-type]
        )
    assert conflict.value.status_code == 409

    assert admin_router._principal_id({"sub": "not-a-uuid"}) is None
    assert admin_router._principal_id({}) is None
    assert original_event_producer(
        SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(clients=object())))
    ) is None
    assert isinstance(
        admin_router._settings(SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))),
        PlatformSettings,
    )
