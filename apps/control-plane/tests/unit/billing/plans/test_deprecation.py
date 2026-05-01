from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from platform.billing.plans.models import PlanVersion
from platform.billing.plans.service import PlansService
from typing import Any
from uuid import UUID, uuid4

import pytest


class _Repository:
    def __init__(self) -> None:
        self.plan_id = uuid4()
        self.version = PlanVersion(
            id=uuid4(),
            plan_id=self.plan_id,
            version=1,
            price_monthly=Decimal("49.00"),
            executions_per_day=500,
            executions_per_month=5000,
            minutes_per_day=240,
            minutes_per_month=2400,
            max_workspaces=5,
            max_agents_per_workspace=50,
            max_users_per_workspace=25,
            overage_price_per_minute=Decimal("0.1000"),
            trial_days=14,
            quota_period_anchor="subscription_anniversary",
            extras_json={},
            published_at=datetime(2026, 5, 1, tzinfo=UTC),
            deprecated_at=None,
        )

    async def deprecate_version(self, plan_id: UUID, version: int) -> PlanVersion | None:
        if plan_id != self.plan_id or version != self.version.version:
            return None
        if self.version.deprecated_at is None:
            self.version.deprecated_at = datetime(2026, 5, 2, tzinfo=UTC)
        return self.version

    async def count_subscriptions_on_version(self, plan_id: UUID, version: int) -> int:
        assert plan_id == self.plan_id
        assert version == self.version.version
        return 3


class _AuditChain:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def append(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append({"args": args, "kwargs": kwargs})


@pytest.mark.asyncio
async def test_deprecate_version_sets_deprecated_at_once_and_is_idempotent() -> None:
    repository = _Repository()
    audit_chain = _AuditChain()
    service = PlansService(repository, audit_chain=audit_chain)  # type: ignore[arg-type]

    first = await service.deprecate_version(repository.plan_id, 1)
    second = await service.deprecate_version(repository.plan_id, 1)

    assert first is repository.version
    assert second is repository.version
    assert first.deprecated_at == datetime(2026, 5, 2, tzinfo=UTC)
    assert second.deprecated_at == first.deprecated_at
    assert audit_chain.calls[0]["kwargs"]["canonical_payload_json"][
        "subscriptions_pinned_count"
    ] == 3
