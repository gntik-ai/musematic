from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from platform.billing.subscriptions.models import Subscription
from platform.common.config import PlatformSettings
from platform.cost_governance.services.attribution_service import AttributionService
from platform.tenants.models import Tenant
from platform.workspaces.models import Workspace
from typing import Any
from uuid import UUID, uuid4

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@dataclass
class _AttributionRow:
    execution_id: UUID
    step_id: str | None
    workspace_id: UUID
    agent_id: UUID | None
    user_id: UUID | None
    subscription_id: UUID | None
    origin: str
    model_id: str | None
    currency: str
    model_cost_cents: Decimal
    compute_cost_cents: Decimal
    storage_cost_cents: Decimal
    overhead_cost_cents: Decimal
    token_counts: dict[str, Any]
    attribution_metadata: dict[str, Any] = field(default_factory=dict)
    correction_of: UUID | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def total_cost_cents(self) -> Decimal:
        return (
            self.model_cost_cents
            + self.compute_cost_cents
            + self.storage_cost_cents
            + self.overhead_cost_cents
        )


class _Result:
    def __init__(self, value: Subscription | None) -> None:
        self.value = value

    def scalar_one_or_none(self) -> Subscription | None:
        return self.value


class _Session:
    def __init__(
        self,
        *,
        workspace: Workspace,
        tenant: Tenant,
        subscription: Subscription,
    ) -> None:
        self.workspace = workspace
        self.tenant = tenant
        self.subscription = subscription
        self.flush_count = 0

    async def get(self, model: type[Any], identifier: UUID) -> Any | None:
        if model is Workspace and identifier == self.workspace.id:
            return self.workspace
        if model is Tenant and identifier == self.tenant.id:
            return self.tenant
        return None

    async def execute(self, statement: Any) -> _Result:
        params = statement.compile().params
        scope_type = _param_with_prefix(params, "scope_type")
        scope_id = _param_with_prefix(params, "scope_id")
        if self.subscription.scope_type == scope_type and self.subscription.scope_id == scope_id:
            return _Result(self.subscription)
        return _Result(None)

    async def flush(self) -> None:
        self.flush_count += 1


class _Repository:
    def __init__(self, session: _Session) -> None:
        self.session = session
        self.rows: list[_AttributionRow] = []

    async def get_attribution_by_execution(self, execution_id: UUID) -> _AttributionRow | None:
        return next(
            (
                row
                for row in self.rows
                if row.execution_id == execution_id and row.correction_of is None
            ),
            None,
        )

    async def insert_attribution(self, **kwargs: Any) -> _AttributionRow:
        kwargs["attribution_metadata"] = kwargs.pop("metadata", {})
        row = _AttributionRow(**kwargs)
        self.rows.append(row)
        return row

    async def insert_attribution_correction(
        self,
        original_id: UUID,
        **kwargs: Any,
    ) -> _AttributionRow:
        original = next(row for row in self.rows if row.id == original_id)
        row = _AttributionRow(
            execution_id=original.execution_id,
            step_id=original.step_id,
            workspace_id=original.workspace_id,
            agent_id=original.agent_id,
            user_id=original.user_id,
            subscription_id=original.subscription_id,
            origin=original.origin,
            model_id=original.model_id,
            currency=original.currency,
            model_cost_cents=kwargs.get("model_cost_cents", Decimal("0")),
            compute_cost_cents=kwargs.get("compute_cost_cents", Decimal("0")),
            storage_cost_cents=kwargs.get("storage_cost_cents", Decimal("0")),
            overhead_cost_cents=kwargs.get("overhead_cost_cents", Decimal("0")),
            token_counts={},
            attribution_metadata=kwargs.get("metadata") or {},
            correction_of=original.id,
        )
        self.rows.append(row)
        return row

    async def list_execution_attributions(self, execution_id: UUID) -> list[_AttributionRow]:
        return [row for row in self.rows if row.execution_id == execution_id]


def _param_with_prefix(params: dict[str, Any], prefix: str) -> Any:
    for key, value in params.items():
        if key.startswith(prefix):
            return value
    raise AssertionError(f"missing SQL parameter prefix: {prefix}")


def _billing_fixture() -> tuple[Workspace, Tenant, Subscription]:
    tenant_id = uuid4()
    workspace_id = uuid4()
    now = datetime(2026, 5, 1, tzinfo=UTC)
    workspace = Workspace(
        id=workspace_id,
        name="Billing Attribution",
        owner_id=uuid4(),
        tenant_id=tenant_id,
    )
    tenant = Tenant(
        id=tenant_id,
        slug="default-test",
        kind="default",
        subdomain="app",
        display_name="Default",
        region="eu-west",
    )
    subscription = Subscription(
        id=uuid4(),
        tenant_id=tenant_id,
        scope_type="workspace",
        scope_id=workspace_id,
        plan_id=uuid4(),
        plan_version=1,
        status="active",
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
    )
    return workspace, tenant, subscription


async def test_cost_attribution_write_and_legacy_read_are_subscription_tagged() -> None:
    workspace, tenant, subscription = _billing_fixture()
    session = _Session(workspace=workspace, tenant=tenant, subscription=subscription)
    repository = _Repository(session)
    service = AttributionService(
        repository=repository,  # type: ignore[arg-type]
        settings=PlatformSettings(),
        fail_open=False,
    )

    row = await service.record_step_cost(
        execution_id=uuid4(),
        step_id="model-call",
        workspace_id=workspace.id,
        agent_id=None,
        user_id=uuid4(),
        payload={"model_cost_cents": "1.25"},
    )

    assert row is not None
    assert row.subscription_id == subscription.id

    legacy_execution_id = uuid4()
    legacy_row = _AttributionRow(
        execution_id=legacy_execution_id,
        step_id=None,
        workspace_id=workspace.id,
        agent_id=None,
        user_id=uuid4(),
        subscription_id=None,
        origin="user_trigger",
        model_id=None,
        currency="USD",
        model_cost_cents=Decimal("1.0000"),
        compute_cost_cents=Decimal("0.0000"),
        storage_cost_cents=Decimal("0.0000"),
        overhead_cost_cents=Decimal("0.0000"),
        token_counts={},
    )
    repository.rows.append(legacy_row)

    result = await service.get_execution_cost(legacy_execution_id)
    assert result is not None
    assert result["attribution"].subscription_id == subscription.id
    assert session.flush_count == 1

    await service.get_execution_cost(legacy_execution_id)
    assert session.flush_count == 1
