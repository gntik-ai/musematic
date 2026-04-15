from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.agentops.governance.grace_period import GracePeriodScanner
from types import SimpleNamespace
from uuid import uuid4

import pytest


class _RepositoryStub:
    def __init__(self, workflows) -> None:
        self.workflows = workflows

    async def list_due_retirements(self, now, *, workspace_id=None):
        del workspace_id
        return [
            workflow
            for workflow in self.workflows
            if workflow.status == "grace_period" and workflow.grace_period_ends_at <= now
        ]


class _RetirementManagerStub:
    def __init__(self) -> None:
        self.calls = []

    async def retire_agent(self, workflow_id):
        self.calls.append(workflow_id)


class _TrustServiceStub:
    def __init__(self) -> None:
        self.calls = 0

    async def expire_stale_certifications(self) -> int:
        self.calls += 1
        return 1


@pytest.mark.asyncio
async def test_grace_period_scanner_skips_workflows_not_yet_due() -> None:
    now = datetime(2026, 4, 14, 12, 0, tzinfo=UTC)
    workflow = SimpleNamespace(
        id=uuid4(),
        status="grace_period",
        high_impact_flag=False,
        operator_confirmed=False,
        grace_period_ends_at=now + timedelta(hours=1),
    )
    manager = _RetirementManagerStub()
    scanner = GracePeriodScanner(
        repository=_RepositoryStub([workflow]),  # type: ignore[arg-type]
        retirement_manager=manager,  # type: ignore[arg-type]
        trust_service=_TrustServiceStub(),
        now_factory=lambda: now,
    )

    await scanner.retirement_grace_period_scanner_task()

    assert manager.calls == []


@pytest.mark.asyncio
async def test_grace_period_scanner_retires_due_workflows() -> None:
    now = datetime(2026, 4, 14, 12, 0, tzinfo=UTC)
    workflow = SimpleNamespace(
        id=uuid4(),
        status="grace_period",
        high_impact_flag=False,
        operator_confirmed=False,
        grace_period_ends_at=now - timedelta(minutes=1),
    )
    manager = _RetirementManagerStub()
    scanner = GracePeriodScanner(
        repository=_RepositoryStub([workflow]),  # type: ignore[arg-type]
        retirement_manager=manager,  # type: ignore[arg-type]
        trust_service=_TrustServiceStub(),
        now_factory=lambda: now,
    )

    await scanner.retirement_grace_period_scanner_task()

    assert manager.calls == [workflow.id]


@pytest.mark.asyncio
async def test_grace_period_scanner_skips_unconfirmed_high_impact_and_expires_recertifications(
) -> None:
    now = datetime(2026, 4, 14, 12, 0, tzinfo=UTC)
    workflow = SimpleNamespace(
        id=uuid4(),
        status="grace_period",
        high_impact_flag=True,
        operator_confirmed=False,
        grace_period_ends_at=now - timedelta(minutes=1),
    )
    manager = _RetirementManagerStub()
    trust_service = _TrustServiceStub()
    scanner = GracePeriodScanner(
        repository=_RepositoryStub([workflow]),  # type: ignore[arg-type]
        retirement_manager=manager,  # type: ignore[arg-type]
        trust_service=trust_service,
        now_factory=lambda: now,
    )

    await scanner.retirement_grace_period_scanner_task()
    await scanner.recertification_grace_period_scanner_task()
    await GracePeriodScanner(
        repository=_RepositoryStub([]),  # type: ignore[arg-type]
        retirement_manager=manager,  # type: ignore[arg-type]
        trust_service=None,
        now_factory=lambda: now,
    ).recertification_grace_period_scanner_task()

    assert manager.calls == []
    assert trust_service.calls == 1
    assert scanner._now() == now
