"""Unit tests for the tenant-deletion path on DeletionService.

Covers:
* T058 — happy path emits 2PA consume + final export + audit + Kafka.
* Missing 2PA -> TwoPATokenRequired (FR-754.1).
* Active subscription -> SubscriptionActiveCancelFirst (FR-754.2).
* Default tenant refusal (FR-754.3) — surfaces via the mutator.
* Typed-confirmation must equal "delete tenant {slug}".
* Recovery via abort_in_grace flips tenant back to active (FR-754.4).
* Phase-2 cascade dispatch to ``tenant_cascade_dispatcher``.
* extend_grace bounded by ``grace_max_days``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from platform.common.config import DataLifecycleSettings
from platform.data_lifecycle.exceptions import (
    DefaultTenantCannotBeDeleted,
    DeletionJobAlreadyActive,
    GracePeriodOutOfRange,
    SubscriptionActiveCancelFirst,
    TwoPATokenInvalid,
    TwoPATokenRequired,
    TypedConfirmationMismatch,
)
from platform.data_lifecycle.models import DeletionJob, DeletionPhase, ScopeType
from platform.data_lifecycle.services.deletion_service import (
    DeletionService,
    TenantDeletionRequestResult,
)


# ---------- Stubs ----------


class _StubRepo:
    def __init__(self) -> None:
        self.created: list[DeletionJob] = []
        self._active: DeletionJob | None = None
        self._jobs_by_id: dict[UUID, DeletionJob] = {}
        self._jobs_by_token_hash: dict[bytes, DeletionJob] = {}
        self.phase_updates: list[dict[str, Any]] = []
        self.grace_updates: list[dict[str, Any]] = []

    async def find_active_deletion_for_scope(self, **kwargs: Any) -> DeletionJob | None:
        return self._active

    async def create_deletion_job(self, **kwargs: Any) -> DeletionJob:
        job = DeletionJob(
            tenant_id=kwargs["tenant_id"],
            scope_type=kwargs["scope_type"],
            scope_id=kwargs["scope_id"],
            phase=DeletionPhase.phase_1.value,
            requested_by_user_id=kwargs["requested_by_user_id"],
            two_pa_token_id=kwargs.get("two_pa_token_id"),
            grace_period_days=kwargs["grace_period_days"],
            grace_ends_at=kwargs["grace_ends_at"],
            cancel_token_hash=kwargs["cancel_token_hash"],
            cancel_token_expires_at=kwargs["cancel_token_expires_at"],
            final_export_job_id=kwargs.get("final_export_job_id"),
            correlation_id=kwargs.get("correlation_id"),
        )
        object.__setattr__(job, "id", uuid4())
        object.__setattr__(job, "created_at", datetime.now(UTC))
        self.created.append(job)
        self._jobs_by_id[job.id] = job
        return job

    async def get_deletion_job(self, job_id: UUID) -> DeletionJob | None:
        return self._jobs_by_id.get(job_id)

    async def find_deletion_by_cancel_token_hash(self, *, token_hash: bytes) -> DeletionJob | None:
        return self._jobs_by_token_hash.get(bytes(token_hash))

    async def list_grace_expired_phase_1_jobs(
        self, *, now: datetime, limit: int = 100
    ) -> list[DeletionJob]:
        return []

    async def update_deletion_phase(self, **kwargs: Any) -> None:
        self.phase_updates.append(kwargs)
        job = self._jobs_by_id.get(kwargs["job_id"])
        if job is not None and "phase" in kwargs:
            object.__setattr__(job, "phase", kwargs["phase"])
            for f in ("cascade_started_at", "cascade_completed_at", "abort_reason"):
                if f in kwargs:
                    object.__setattr__(job, f, kwargs[f])

    async def extend_grace(self, *, job_id: UUID, new_grace_ends_at: datetime) -> None:
        self.grace_updates.append({"job_id": job_id, "new_grace_ends_at": new_grace_ends_at})
        job = self._jobs_by_id.get(job_id)
        if job is not None:
            object.__setattr__(job, "grace_ends_at", new_grace_ends_at)
            object.__setattr__(job, "cancel_token_expires_at", new_grace_ends_at)


class _StubWorkspaceMutator:
    async def get_workspace_for_deletion(self, **kwargs: Any) -> tuple[str, str]:
        return ("not-used", "active")

    async def set_workspace_status(self, **kwargs: Any) -> None:
        pass


class _StubTenantMutator:
    def __init__(
        self,
        *,
        slug: str = "acme",
        kind: str = "enterprise",
        status: str = "active",
        contract_metadata: dict | None = None,
    ) -> None:
        self.slug = slug
        self.kind = kind
        self._status = status
        self._contract_metadata = contract_metadata or {}
        self.statuses: list[tuple[UUID, str]] = []

    async def get_tenant_for_deletion(
        self, *, tenant_id: UUID
    ) -> tuple[str, str, dict]:
        if self.kind == "default":
            raise DefaultTenantCannotBeDeleted(
                "the platform default tenant cannot be deleted"
            )
        if self._status in {"pending_deletion", "deleted"}:
            raise DeletionJobAlreadyActive(
                f"tenant already {self._status}"
            )
        return self.slug, self._status, self._contract_metadata

    async def set_tenant_status(self, *, tenant_id: UUID, status: str) -> None:
        self.statuses.append((tenant_id, status))


class _StubSubscriptionGate:
    def __init__(self, *, has_active: bool = False) -> None:
        self._has_active = has_active

    async def has_active_subscription(self, *, tenant_id: UUID) -> bool:
        return self._has_active


class _StubTwoPAGate:
    def __init__(self, *, raises: Exception | None = None) -> None:
        self._raises = raises
        self.consumed: list[UUID] = []

    async def consume_or_raise(
        self, *, challenge_id: UUID, requester_id: UUID
    ) -> dict:
        if self._raises is not None:
            raise self._raises
        self.consumed.append(challenge_id)
        return {"consumed_at": datetime.now(UTC).isoformat()}


class _StubAudit:
    def __init__(self) -> None:
        self.appended: list[bytes] = []

    async def append(self, audit_event_id, namespace, canonical_payload):
        self.appended.append(canonical_payload)


class _StubProducer:
    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []

    async def publish(self, **kwargs: Any) -> None:
        self.published.append(kwargs)


def _build(
    *,
    repo: _StubRepo | None = None,
    tenant_mutator: _StubTenantMutator | None = None,
    subscription_gate: _StubSubscriptionGate | None = None,
    two_pa_gate: _StubTwoPAGate | None = None,
    cascade_dispatcher: Any = None,
    tenant_cascade_dispatcher: Any = None,
    export_handler: Any = None,
    fixed_now: datetime | None = None,
):
    repo = repo or _StubRepo()
    tenant_mutator = tenant_mutator or _StubTenantMutator()
    subscription_gate = subscription_gate or _StubSubscriptionGate()
    two_pa_gate = two_pa_gate or _StubTwoPAGate()
    audit = _StubAudit()
    producer = _StubProducer()
    clock = (lambda fixed=fixed_now: fixed) if fixed_now else None
    service = DeletionService(
        repository=repo,  # type: ignore[arg-type]
        settings=DataLifecycleSettings(),
        workspace_mutator=_StubWorkspaceMutator(),  # type: ignore[arg-type]
        audit_chain=audit,  # type: ignore[arg-type]
        event_producer=producer,  # type: ignore[arg-type]
        cascade_dispatcher=cascade_dispatcher,
        tenant_mutator=tenant_mutator,  # type: ignore[arg-type]
        subscription_gate=subscription_gate,  # type: ignore[arg-type]
        two_pa_gate=two_pa_gate,  # type: ignore[arg-type]
        tenant_cascade_dispatcher=tenant_cascade_dispatcher,
        export_request_handler=export_handler,
        clock=clock,
    )
    return service, repo, tenant_mutator, subscription_gate, two_pa_gate, audit, producer


# ---------- Tests ----------


@pytest.mark.asyncio
async def test_request_tenant_deletion_happy_path() -> None:
    final_export_id = uuid4()

    async def _export(*, tenant_id, requested_by_user_id, correlation_ctx=None):
        from types import SimpleNamespace
        return SimpleNamespace(id=final_export_id)

    service, repo, mutator, _, two_pa, audit, producer = _build(
        export_handler=_export
    )
    challenge_id = uuid4()

    result = await service.request_tenant_deletion(
        tenant_id=uuid4(),
        requested_by_user_id=uuid4(),
        typed_confirmation="delete tenant acme",
        reason="contract end",
        two_pa_challenge_id=challenge_id,
        include_final_export=True,
    )

    assert isinstance(result, TenantDeletionRequestResult)
    assert result.final_export_job_id == final_export_id
    assert result.job.scope_type == ScopeType.tenant.value
    assert result.job.phase == DeletionPhase.phase_1.value
    assert result.job.grace_period_days == 30  # tenant default
    # 2PA consumed.
    assert challenge_id in two_pa.consumed
    # Audit + Kafka.
    assert any(b"tenant_deletion_phase_1" in p for p in audit.appended)
    types = [p["event_type"] for p in producer.published]
    assert "data_lifecycle.deletion.requested" in types
    # Tenant flipped to pending_deletion.
    assert any(s == "pending_deletion" for _, s in mutator.statuses)


@pytest.mark.asyncio
async def test_request_tenant_deletion_missing_2pa_raises() -> None:
    service, *_ = _build()
    with pytest.raises(TwoPATokenRequired):
        await service.request_tenant_deletion(
            tenant_id=uuid4(),
            requested_by_user_id=uuid4(),
            typed_confirmation="delete tenant acme",
            reason="x",
            two_pa_challenge_id=None,
            include_final_export=False,
        )


@pytest.mark.asyncio
async def test_request_tenant_deletion_invalid_2pa_raises() -> None:
    two_pa = _StubTwoPAGate(raises=RuntimeError("expired challenge"))
    service, *_ = _build(two_pa_gate=two_pa)
    with pytest.raises(TwoPATokenInvalid):
        await service.request_tenant_deletion(
            tenant_id=uuid4(),
            requested_by_user_id=uuid4(),
            typed_confirmation="delete tenant acme",
            reason="x",
            two_pa_challenge_id=uuid4(),
            include_final_export=False,
        )


@pytest.mark.asyncio
async def test_request_tenant_deletion_active_subscription_refused() -> None:
    service, *_ = _build(
        subscription_gate=_StubSubscriptionGate(has_active=True)
    )
    with pytest.raises(SubscriptionActiveCancelFirst):
        await service.request_tenant_deletion(
            tenant_id=uuid4(),
            requested_by_user_id=uuid4(),
            typed_confirmation="delete tenant acme",
            reason="x",
            two_pa_challenge_id=uuid4(),
            include_final_export=False,
        )


@pytest.mark.asyncio
async def test_request_tenant_deletion_default_tenant_refused() -> None:
    service, *_ = _build(tenant_mutator=_StubTenantMutator(kind="default"))
    with pytest.raises(DefaultTenantCannotBeDeleted):
        await service.request_tenant_deletion(
            tenant_id=uuid4(),
            requested_by_user_id=uuid4(),
            typed_confirmation="delete tenant acme",
            reason="x",
            two_pa_challenge_id=uuid4(),
            include_final_export=False,
        )


@pytest.mark.asyncio
async def test_request_tenant_deletion_typed_confirmation_must_match() -> None:
    service, *_ = _build()
    with pytest.raises(TypedConfirmationMismatch):
        await service.request_tenant_deletion(
            tenant_id=uuid4(),
            requested_by_user_id=uuid4(),
            typed_confirmation="WRONG",
            reason="x",
            two_pa_challenge_id=uuid4(),
            include_final_export=False,
        )


@pytest.mark.asyncio
async def test_request_tenant_deletion_grace_override_respected() -> None:
    service, *_ = _build(
        tenant_mutator=_StubTenantMutator(
            contract_metadata={"deletion_grace_period_days": 60}
        )
    )
    result = await service.request_tenant_deletion(
        tenant_id=uuid4(),
        requested_by_user_id=uuid4(),
        typed_confirmation="delete tenant acme",
        reason="x",
        two_pa_challenge_id=uuid4(),
        include_final_export=False,
    )
    assert result.job.grace_period_days == 60


@pytest.mark.asyncio
async def test_request_tenant_deletion_request_override_beats_contract() -> None:
    service, *_ = _build(
        tenant_mutator=_StubTenantMutator(
            contract_metadata={"deletion_grace_period_days": 60}
        )
    )
    result = await service.request_tenant_deletion(
        tenant_id=uuid4(),
        requested_by_user_id=uuid4(),
        typed_confirmation="delete tenant acme",
        reason="x",
        two_pa_challenge_id=uuid4(),
        include_final_export=False,
        grace_period_days_override=21,
    )
    assert result.job.grace_period_days == 21


@pytest.mark.asyncio
async def test_extend_grace_within_bounds() -> None:
    service, repo, *_ = _build()
    result = await service.request_tenant_deletion(
        tenant_id=uuid4(),
        requested_by_user_id=uuid4(),
        typed_confirmation="delete tenant acme",
        reason="x",
        two_pa_challenge_id=uuid4(),
        include_final_export=False,
    )
    job = result.job
    extended = await service.extend_grace(
        job_id=job.id,
        additional_days=14,
        actor_user_id=uuid4(),
        reason="legal review extension",
    )
    assert len(repo.grace_updates) == 1


@pytest.mark.asyncio
async def test_extend_grace_exceeds_max_raises() -> None:
    service, repo, *_ = _build()
    result = await service.request_tenant_deletion(
        tenant_id=uuid4(),
        requested_by_user_id=uuid4(),
        typed_confirmation="delete tenant acme",
        reason="x",
        two_pa_challenge_id=uuid4(),
        include_final_export=False,
        grace_period_days_override=85,
    )
    job = result.job
    with pytest.raises(GracePeriodOutOfRange):
        await service.extend_grace(
            job_id=job.id,
            additional_days=20,  # 85+20 > 90 max
            actor_user_id=uuid4(),
            reason="too long",
        )


@pytest.mark.asyncio
async def test_abort_tenant_deletion_in_grace_restores_active() -> None:
    service, repo, mutator, *_ = _build()
    result = await service.request_tenant_deletion(
        tenant_id=uuid4(),
        requested_by_user_id=uuid4(),
        typed_confirmation="delete tenant acme",
        reason="x",
        two_pa_challenge_id=uuid4(),
        include_final_export=False,
    )
    mutator.statuses.clear()  # ignore the phase_1 flip

    aborted = await service.abort_in_grace(
        job_id=result.job.id,
        actor_user_id=uuid4(),
        abort_reason="false alarm",
    )
    assert aborted.phase == DeletionPhase.aborted.value
    # Tenant flipped back to active.
    assert any(s == "active" for _, s in mutator.statuses)


@pytest.mark.asyncio
async def test_advance_grace_dispatches_tenant_cascade_for_tenant_scope() -> None:
    cascade_calls: list[dict[str, Any]] = []

    async def _dispatch(*, tenant_id: UUID, requested_by_user_id):
        cascade_calls.append({"tenant_id": tenant_id})
        return {"errors": [], "store_results": [{"store": "postgresql", "rows_affected": 99}]}

    repo = _StubRepo()
    job = DeletionJob(
        tenant_id=uuid4(),
        scope_type=ScopeType.tenant.value,
        scope_id=uuid4(),
        phase=DeletionPhase.phase_1.value,
        grace_period_days=30,
        grace_ends_at=datetime.now(UTC) - timedelta(seconds=1),
        cancel_token_hash=b"q" * 32,
        cancel_token_expires_at=datetime.now(UTC),
    )
    object.__setattr__(job, "id", uuid4())
    repo._jobs_by_id[job.id] = job

    # Override list_grace_expired to return our job.
    async def _list(*, now, limit=100):
        return [job]

    repo.list_grace_expired_phase_1_jobs = _list  # type: ignore[assignment]

    service, *_ = _build(
        repo=repo,
        tenant_cascade_dispatcher=_dispatch,
    )
    advanced = await service.advance_grace_expired_jobs()
    assert advanced == 1
    assert cascade_calls and cascade_calls[0]["tenant_id"] == job.scope_id
