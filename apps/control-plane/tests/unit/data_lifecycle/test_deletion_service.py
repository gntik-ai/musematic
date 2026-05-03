"""Unit tests for DeletionService.

Covers:
* Phase-1 request — happy path, slug-mismatch refusal, active-job
  conflict, audit + Kafka emission, plaintext token returned (T043).
* Cancel-via-token — anti-enumeration: same return shape regardless
  of outcome (T044 / T042 / R10).
* Superadmin abort during grace — phase_2 refused (CascadeInProgressError).
* Grace advance — finds expired phase_1 jobs, advances to phase_2,
  drives the cascade dispatcher.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from platform.common.config import DataLifecycleSettings
from platform.data_lifecycle.exceptions import (
    CascadeInProgressError,
    DeletionJobAlreadyActiveError,
    TypedConfirmationMismatchError,
)
from platform.data_lifecycle.models import DeletionJob, DeletionPhase, ScopeType
from platform.data_lifecycle.services.deletion_service import (
    DeletionService,
    WorkspaceDeletionRequestResult,
)
from typing import Any
from uuid import UUID, uuid4

import pytest

# ---------- Stubs ----------


class _StubRepo:
    def __init__(self) -> None:
        self.created: list[DeletionJob] = []
        self._active: DeletionJob | None = None
        self._jobs_by_id: dict[UUID, DeletionJob] = {}
        self._jobs_by_token_hash: dict[bytes, DeletionJob] = {}
        self._grace_expired: list[DeletionJob] = []
        self.phase_updates: list[dict[str, Any]] = []

    async def find_active_deletion_for_scope(
        self, *, scope_type: str, scope_id: UUID
    ) -> DeletionJob | None:
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
        self._jobs_by_token_hash[bytes(kwargs["cancel_token_hash"])] = job
        return job

    async def get_deletion_job(self, job_id: UUID) -> DeletionJob | None:
        return self._jobs_by_id.get(job_id)

    async def find_deletion_by_cancel_token_hash(
        self, *, token_hash: bytes
    ) -> DeletionJob | None:
        return self._jobs_by_token_hash.get(bytes(token_hash))

    async def list_grace_expired_phase_1_jobs(
        self, *, now: datetime, limit: int = 100
    ) -> list[DeletionJob]:
        return list(self._grace_expired)

    async def update_deletion_phase(self, **kwargs: Any) -> None:
        self.phase_updates.append(kwargs)
        job = self._jobs_by_id.get(kwargs["job_id"])
        if job is not None and "phase" in kwargs:
            object.__setattr__(job, "phase", kwargs["phase"])
            for field in ("cascade_started_at", "cascade_completed_at", "abort_reason"):
                if field in kwargs:
                    object.__setattr__(job, field, kwargs[field])


class _StubMutator:
    def __init__(self, *, name: str = "acme-pro", prior_status: str = "active") -> None:
        self._name = name
        self._prior_status = prior_status
        self.statuses: list[tuple[UUID, str]] = []
        self.refuse_with: Exception | None = None

    async def get_workspace_for_deletion(
        self, *, workspace_id: UUID, requested_by_user_id: UUID
    ) -> tuple[str, str]:
        if self.refuse_with is not None:
            raise self.refuse_with
        return self._name, self._prior_status

    async def set_workspace_status(self, *, workspace_id: UUID, status: str) -> None:
        self.statuses.append((workspace_id, status))


class _StubProducer:
    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []

    async def publish(self, **kwargs: Any) -> None:
        self.published.append(kwargs)


class _StubAudit:
    def __init__(self) -> None:
        self.appended: list[bytes] = []

    async def append(
        self, audit_event_id: UUID, namespace: str, canonical_payload: bytes
    ) -> None:
        self.appended.append(canonical_payload)


def _build(
    *,
    repo: _StubRepo | None = None,
    mutator: _StubMutator | None = None,
    audit: _StubAudit | None = None,
    producer: _StubProducer | None = None,
    cascade_dispatcher: Any = None,
    fixed_now: datetime | None = None,
) -> tuple[DeletionService, _StubRepo, _StubMutator, _StubAudit, _StubProducer]:
    repo = repo or _StubRepo()
    mutator = mutator or _StubMutator()
    audit = audit or _StubAudit()
    producer = producer or _StubProducer()
    clock = (lambda fixed=fixed_now: fixed) if fixed_now else None
    service = DeletionService(
        repository=repo,  # type: ignore[arg-type]
        settings=DataLifecycleSettings(),
        workspace_mutator=mutator,  # type: ignore[arg-type]
        audit_chain=audit,  # type: ignore[arg-type]
        event_producer=producer,  # type: ignore[arg-type]
        cascade_dispatcher=cascade_dispatcher,
        clock=clock,
    )
    return service, repo, mutator, audit, producer


# ---------- Phase-1 request ----------


@pytest.mark.asyncio
async def test_request_workspace_deletion_creates_phase_1_job() -> None:
    service, _repo, mutator, audit, producer = _build()
    workspace_id = uuid4()
    tenant_id = uuid4()
    user_id = uuid4()

    result = await service.request_workspace_deletion(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        requested_by_user_id=user_id,
        typed_confirmation="acme-pro",
        reason="cleanup",
        tenant_contract_metadata=None,
    )

    assert isinstance(result, WorkspaceDeletionRequestResult)
    assert result.cancel_token  # plaintext token is returned to the caller
    assert len(result.cancel_token) > 30  # 32-byte URL-safe is well over 30 chars

    job = result.job
    assert job.scope_type == ScopeType.workspace.value
    assert job.scope_id == workspace_id
    assert job.phase == DeletionPhase.phase_1.value
    assert job.grace_period_days == 7  # default

    # Workspace status flipped.
    assert (workspace_id, "pending_deletion") in mutator.statuses

    # Token hash matches what we'd compute from plaintext.
    expected_hash = hashlib.sha256(result.cancel_token.encode("utf-8")).digest()
    assert bytes(job.cancel_token_hash) == expected_hash

    # Audit + Kafka.
    assert any(b"workspace_deletion_phase_1" in payload for payload in audit.appended)
    types = [p["event_type"] for p in producer.published]
    assert "data_lifecycle.deletion.requested" in types


@pytest.mark.asyncio
async def test_request_workspace_deletion_refuses_typed_confirmation_mismatch() -> None:
    service, repo, _, _, _ = _build(mutator=_StubMutator(name="acme-pro"))

    with pytest.raises(TypedConfirmationMismatchError):
        await service.request_workspace_deletion(
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            requested_by_user_id=uuid4(),
            typed_confirmation="WRONG",
            reason=None,
            tenant_contract_metadata=None,
        )
    assert repo.created == []


@pytest.mark.asyncio
async def test_request_workspace_deletion_refuses_when_active_job_exists() -> None:
    repo = _StubRepo()
    existing = DeletionJob(
        tenant_id=uuid4(),
        scope_type=ScopeType.workspace.value,
        scope_id=uuid4(),
        phase=DeletionPhase.phase_1.value,
        grace_period_days=7,
        grace_ends_at=datetime.now(UTC) + timedelta(days=7),
        cancel_token_hash=b"x" * 32,
        cancel_token_expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    object.__setattr__(existing, "id", uuid4())
    repo._active = existing
    service, _, _, _, _ = _build(repo=repo)

    with pytest.raises(DeletionJobAlreadyActiveError):
        await service.request_workspace_deletion(
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            requested_by_user_id=uuid4(),
            typed_confirmation="acme-pro",
            reason=None,
            tenant_contract_metadata=None,
        )


@pytest.mark.asyncio
async def test_request_workspace_deletion_uses_tenant_grace_override() -> None:
    service, _, _, _, _ = _build()
    result = await service.request_workspace_deletion(
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        requested_by_user_id=uuid4(),
        typed_confirmation="acme-pro",
        reason=None,
        tenant_contract_metadata={"deletion_grace_period_days": 14},
    )
    assert result.job.grace_period_days == 14


# ---------- Cancel-via-token (R10 anti-enumeration) ----------


@pytest.mark.asyncio
async def test_cancel_via_token_unknown_returns_not_succeeded() -> None:
    service, _, mutator, audit, _ = _build()

    outcome = await service.cancel_via_token(token="not-a-real-token")

    assert outcome.succeeded is False
    assert outcome.detail == "token_unknown"
    # Workspace state untouched.
    assert mutator.statuses == []
    # Operator sees the truth via audit.
    assert any(b"cancel_token_invalid" in p for p in audit.appended)


@pytest.mark.asyncio
async def test_cancel_via_token_success_flips_workspace_to_active() -> None:
    service, _repo, mutator, _audit, producer = _build()
    workspace_id = uuid4()
    result = await service.request_workspace_deletion(
        tenant_id=uuid4(),
        workspace_id=workspace_id,
        requested_by_user_id=uuid4(),
        typed_confirmation="acme-pro",
        reason=None,
        tenant_contract_metadata=None,
    )

    outcome = await service.cancel_via_token(token=result.cancel_token)

    assert outcome.succeeded is True
    assert outcome.detail == "cancelled"
    # Workspace flipped pending_deletion -> active.
    assert (workspace_id, "active") in mutator.statuses
    # Audit + Kafka aborted event.
    types = [p["event_type"] for p in producer.published]
    assert "data_lifecycle.deletion.aborted" in types


@pytest.mark.asyncio
async def test_cancel_via_token_expired_returns_not_succeeded() -> None:
    """Token past expiry produces the same response shape — R10."""

    service, _repo, _mutator, audit, _ = _build()
    # Backdate a job so its expiry is in the past.
    workspace_id = uuid4()
    result = await service.request_workspace_deletion(
        tenant_id=uuid4(),
        workspace_id=workspace_id,
        requested_by_user_id=uuid4(),
        typed_confirmation="acme-pro",
        reason=None,
        tenant_contract_metadata=None,
    )
    job = result.job
    object.__setattr__(
        job, "cancel_token_expires_at", datetime.now(UTC) - timedelta(seconds=1)
    )
    object.__setattr__(
        job, "grace_ends_at", datetime.now(UTC) - timedelta(seconds=1)
    )

    outcome = await service.cancel_via_token(token=result.cancel_token)

    assert outcome.succeeded is False
    assert outcome.detail == "token_expired"
    assert any(b"token_expired" in p for p in audit.appended)


@pytest.mark.asyncio
async def test_cancel_via_token_already_used_is_silent() -> None:
    service, _, _, audit, _ = _build()
    workspace_id = uuid4()
    result = await service.request_workspace_deletion(
        tenant_id=uuid4(),
        workspace_id=workspace_id,
        requested_by_user_id=uuid4(),
        typed_confirmation="acme-pro",
        reason=None,
        tenant_contract_metadata=None,
    )
    # First cancel succeeds.
    await service.cancel_via_token(token=result.cancel_token)
    audit.appended.clear()
    # Second cancel of the same token must be silent.
    second = await service.cancel_via_token(token=result.cancel_token)
    assert second.succeeded is False
    assert second.detail == "wrong_phase"
    assert any(b"wrong_phase" in p for p in audit.appended)


# ---------- Abort / grace advance ----------


@pytest.mark.asyncio
async def test_abort_in_grace_in_phase_2_raises_cascade_in_progress() -> None:
    service, repo, _, _, _ = _build()
    job = DeletionJob(
        tenant_id=uuid4(),
        scope_type=ScopeType.workspace.value,
        scope_id=uuid4(),
        phase=DeletionPhase.phase_2.value,
        grace_period_days=7,
        grace_ends_at=datetime.now(UTC),
        cancel_token_hash=b"y" * 32,
        cancel_token_expires_at=datetime.now(UTC),
    )
    object.__setattr__(job, "id", uuid4())
    repo._jobs_by_id[job.id] = job

    with pytest.raises(CascadeInProgressError):
        await service.abort_in_grace(
            job_id=job.id,
            actor_user_id=uuid4(),
            abort_reason="false alarm",
        )


@pytest.mark.asyncio
async def test_advance_grace_expired_jobs_dispatches_cascade() -> None:
    cascade_calls: list[dict[str, Any]] = []

    async def _cascade(*, workspace_id: UUID, requested_by_user_id: UUID | None) -> dict[str, Any]:
        cascade_calls.append(
            {"workspace_id": workspace_id, "requested_by_user_id": requested_by_user_id}
        )
        return {"errors": [], "store_results": [{"store": "postgresql", "rows_affected": 1}]}

    repo = _StubRepo()
    job = DeletionJob(
        tenant_id=uuid4(),
        scope_type=ScopeType.workspace.value,
        scope_id=uuid4(),
        phase=DeletionPhase.phase_1.value,
        grace_period_days=7,
        grace_ends_at=datetime.now(UTC) - timedelta(seconds=1),
        cancel_token_hash=b"z" * 32,
        cancel_token_expires_at=datetime.now(UTC),
    )
    object.__setattr__(job, "id", uuid4())
    repo._jobs_by_id[job.id] = job
    repo._grace_expired = [job]
    service, _, mutator, _audit, producer = _build(
        repo=repo, cascade_dispatcher=_cascade
    )

    advanced = await service.advance_grace_expired_jobs()

    assert advanced == 1
    assert len(cascade_calls) == 1
    assert cascade_calls[0]["workspace_id"] == job.scope_id
    # Workspace flipped to deleted on cascade success.
    assert (job.scope_id, "deleted") in mutator.statuses
    # Phase advanced + completed events emitted.
    types = [p["event_type"] for p in producer.published]
    assert "data_lifecycle.deletion.phase_advanced" in types
