"""Two-phase deletion service for workspace + tenant scopes.

Workspace deletion (US2) — public surface:

* :meth:`DeletionService.request_workspace_deletion` — flips workspace
  to ``pending_deletion``, generates a SHA-256-hashed cancel token,
  audits, emits Kafka event. Returns the deletion job + the plaintext
  cancel token (the caller emails it to the owner; only the hash is
  persisted).
* :meth:`DeletionService.cancel_via_token` — R10 anti-enumeration
  cancel endpoint. ALWAYS returns the same response shape. Server-side
  branches on token validity, expiry, phase, then either flips
  workspace back to ``active`` (success path) or audits the failure
  (silent path).
* :meth:`DeletionService.advance_phase_1_to_phase_2` — called by the
  GraceMonitor cron when ``grace_ends_at <= now()``. Flips phase,
  triggers cascade dispatch, transitions workspace to ``deleted``.
* :meth:`DeletionService.abort_in_grace` — superadmin abort during
  phase_1 only.

Tenant deletion (US3) lands in Phase 5 and reuses the same plumbing
with 2PA + subscription preflight + final-export linkage.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Awaitable, Callable, Protocol
from uuid import UUID, uuid4

from platform.common.config import DataLifecycleSettings
from platform.common.events.envelope import CorrelationContext
from platform.data_lifecycle.events import (
    DataLifecycleEventType,
    DeletionAbortedPayload,
    DeletionPhaseAdvancedPayload,
    DeletionRequestedPayload,
    publish_data_lifecycle_event,
)
from platform.data_lifecycle.exceptions import (
    CascadeInProgress,
    DataLifecycleError,
    DefaultTenantCannotBeDeleted,
    DeletionJobAlreadyActive,
    DeletionJobAlreadyFinalised,
    GracePeriodOutOfRange,
    SubscriptionActiveCancelFirst,
    TwoPATokenInvalid,
    TwoPATokenRequired,
    TypedConfirmationMismatch,
)
from platform.data_lifecycle.models import DeletionJob, DeletionPhase, ScopeType
from platform.data_lifecycle.repository import DataLifecycleRepository
from platform.data_lifecycle.services.grace_calculator import (
    resolve_tenant_grace,
    resolve_workspace_grace,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TenantDeletionRequestResult:
    """Return shape of ``request_tenant_deletion``.

    Carries both the deletion job and the (optional) final-export job
    so the caller can email the tenant admin a single confirmation
    referencing both.
    """

    job: DeletionJob
    final_export_job_id: UUID | None


@dataclass(frozen=True, slots=True)
class WorkspaceDeletionRequestResult:
    """Return shape of ``request_workspace_deletion``.

    The plaintext ``cancel_token`` is sent to the owner via email and
    NEVER persisted; only its SHA-256 hash lives in
    ``deletion_jobs.cancel_token_hash``.
    """

    job: DeletionJob
    cancel_token: str


@dataclass(frozen=True, slots=True)
class CancelOutcome:
    """Internal result of cancel_via_token. Never returned to callers.

    The router always sends the same anti-enumeration message
    regardless of outcome — but operators see the truth via audit.
    """

    succeeded: bool
    detail: str  # "cancelled" | "token_unknown" | "token_expired" | "token_already_used" | "wrong_phase"


class _AuditAppender(Protocol):
    async def append(
        self, audit_event_id: UUID, namespace: str, canonical_payload: bytes
    ) -> Any:
        ...


class _EventProducer(Protocol):
    async def publish(
        self,
        *,
        topic: str,
        key: str,
        event_type: str,
        payload: dict[str, Any],
        correlation_ctx: Any,
        source: str,
    ) -> Any:
        ...


class _WorkspaceStateMutator(Protocol):
    """Subset of WorkspacesService used to flip workspace status.

    Owns the validation that a workspace exists, the caller is the
    owner, and the slug-confirmation matches. Implementations of this
    protocol live in ``platform.workspaces.service``.
    """

    async def get_workspace_for_deletion(
        self, *, workspace_id: UUID, requested_by_user_id: UUID
    ) -> tuple[str, str]:
        """Return ``(slug, prior_status)`` if the caller may delete.

        Raises an HTTP-mappable exception otherwise.
        """

    async def set_workspace_status(
        self, *, workspace_id: UUID, status: str
    ) -> None:
        ...


class _TenantStateMutator(Protocol):
    """Subset of tenant operations needed by the deletion service.

    Implementations live in ``platform.tenants.service``; the data
    lifecycle BC remains decoupled from tenant-internal concerns
    (subdomain routing, branding, etc.).
    """

    async def get_tenant_for_deletion(
        self, *, tenant_id: UUID
    ) -> tuple[str, str, dict[str, Any]]:
        """Return ``(slug, prior_status, contract_metadata)``.

        Raises if the tenant is the platform default tenant or is
        already in ``pending_deletion`` / ``deleted``.
        """

    async def set_tenant_status(self, *, tenant_id: UUID, status: str) -> None:
        ...


class _SubscriptionGate(Protocol):
    """Subset of UPD-052 subscription service we need.

    The tenant cannot enter phase_1 while any subscription is in an
    active billing state (``trial`` / ``active`` / ``past_due``). The
    super admin must cancel via UPD-052 first (FR-754.2).
    """

    async def has_active_subscription(self, *, tenant_id: UUID) -> bool:
        ...


class _TwoPAGate(Protocol):
    """Subset of UPD-039 two-person-approval service we need.

    The deletion service consumes a fresh 2PA challenge atomically; the
    challenge must be in the ``approved`` state and not yet consumed.
    """

    async def consume_or_raise(
        self, *, challenge_id: UUID, requester_id: UUID
    ) -> dict[str, Any]:
        """Atomically mark the 2PA challenge consumed.

        Raises ``TwoPATokenInvalid`` if the challenge does not exist,
        is not approved, is expired, or has already been consumed.
        """


class DeletionService:
    def __init__(
        self,
        *,
        repository: DataLifecycleRepository,
        settings: DataLifecycleSettings,
        workspace_mutator: _WorkspaceStateMutator,
        audit_chain: _AuditAppender | None,
        event_producer: _EventProducer | None,
        cascade_dispatcher: Callable[..., Awaitable[dict[str, Any]]] | None = None,
        tenant_mutator: _TenantStateMutator | None = None,
        subscription_gate: _SubscriptionGate | None = None,
        two_pa_gate: _TwoPAGate | None = None,
        tenant_cascade_dispatcher: Callable[..., Awaitable[dict[str, Any]]] | None = None,
        export_request_handler: Callable[..., Awaitable[Any]] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repo = repository
        self._settings = settings
        self._workspaces = workspace_mutator
        self._audit = audit_chain
        self._producer = event_producer
        self._cascade_dispatcher = cascade_dispatcher
        self._tenants = tenant_mutator
        self._subscriptions = subscription_gate
        self._two_pa = two_pa_gate
        self._tenant_cascade_dispatcher = tenant_cascade_dispatcher
        self._export_request_handler = export_request_handler
        self._clock = clock or (lambda: datetime.now(UTC))

    # ====================================================================
    # Phase 1 — request
    # ====================================================================

    async def request_workspace_deletion(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        requested_by_user_id: UUID,
        typed_confirmation: str,
        reason: str | None,
        tenant_contract_metadata: dict[str, Any] | None,
        correlation_ctx: Any = None,
    ) -> WorkspaceDeletionRequestResult:
        """Mark a workspace ``pending_deletion`` and arm the grace clock.

        Validation order: confirmation match -> no active deletion ->
        grace resolution -> token generation -> persist + audit + Kafka.
        """

        # 1. Caller authorization + slug-confirmation. Delegated to the
        #    workspace BC because that's where slug + ownership live.
        slug, _prior_status = await self._workspaces.get_workspace_for_deletion(
            workspace_id=workspace_id, requested_by_user_id=requested_by_user_id
        )
        if typed_confirmation.strip() != slug:
            raise TypedConfirmationMismatch(
                f"typed_confirmation must equal the workspace slug ({slug!r})"
            )

        # 2. No active deletion job already in flight (the partial-unique
        #    index prevents two phase_1/phase_2 rows; we surface the error
        #    eagerly here for a cleaner 409 response).
        existing = await self._repo.find_active_deletion_for_scope(
            scope_type=ScopeType.workspace.value, scope_id=workspace_id
        )
        if existing is not None:
            raise DeletionJobAlreadyActive(
                f"workspace {workspace_id} already has an active deletion job"
            )

        # 3. Grace resolution.
        grace = resolve_workspace_grace(
            settings=self._settings,
            tenant_contract_metadata=tenant_contract_metadata,
        )
        now = self._clock()
        grace_ends_at = now + timedelta(days=grace.days)

        # 4. Cancel token: 32-byte URL-safe; we persist only its SHA-256.
        cancel_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(cancel_token.encode("utf-8")).digest()

        # 5. Persist + flip workspace status.
        job = await self._repo.create_deletion_job(
            tenant_id=tenant_id,
            scope_type=ScopeType.workspace.value,
            scope_id=workspace_id,
            requested_by_user_id=requested_by_user_id,
            two_pa_token_id=None,
            grace_period_days=grace.days,
            grace_ends_at=grace_ends_at,
            cancel_token_hash=token_hash,
            cancel_token_expires_at=grace_ends_at,
            correlation_id=getattr(correlation_ctx, "correlation_id", None),
        )
        await self._workspaces.set_workspace_status(
            workspace_id=workspace_id, status="pending_deletion"
        )

        # 6. Audit + Kafka event.
        await self._emit_audit(
            event_type="data_lifecycle.workspace_deletion_phase_1",
            payload={
                "job_id": str(job.id),
                "tenant_id": str(tenant_id),
                "workspace_id": str(workspace_id),
                "actor_user_id": str(requested_by_user_id),
                "grace_period_days": grace.days,
                "grace_source": grace.source,
                "grace_ends_at": grace_ends_at.isoformat(),
                "reason": reason or "",
            },
        )
        await publish_data_lifecycle_event(
            self._producer,
            DataLifecycleEventType.deletion_requested,
            DeletionRequestedPayload(
                job_id=job.id,
                scope_type=ScopeType.workspace.value,
                scope_id=workspace_id,
                grace_period_days=grace.days,
                grace_ends_at=grace_ends_at,
                two_pa_token_id=None,
                final_export_job_id=None,
                correlation_context=_ensure_corr(correlation_ctx),
            ),
            _ensure_corr(correlation_ctx),
            partition_key=tenant_id,
        )
        return WorkspaceDeletionRequestResult(job=job, cancel_token=cancel_token)

    # ====================================================================
    # Tenant-scope deletion (US3)
    # ====================================================================

    async def request_tenant_deletion(
        self,
        *,
        tenant_id: UUID,
        requested_by_user_id: UUID,
        typed_confirmation: str,
        reason: str,
        two_pa_challenge_id: UUID | None,
        include_final_export: bool,
        grace_period_days_override: int | None = None,
        correlation_ctx: Any = None,
    ) -> TenantDeletionRequestResult:
        """Phase-1 tenant deletion.

        Order: 2PA validation -> tenant lookup + default-tenant guard ->
        subscription preflight -> typed-confirmation -> grace resolve ->
        active-job guard -> persist + status flip + final-export linkage
        + audit + Kafka.
        """

        if self._tenants is None:
            raise DataLifecycleError(
                "tenant_mutator is not configured on DeletionService"
            )

        # 1. Two-person authorization (rule 33).
        consumed_2pa = None
        if two_pa_challenge_id is None:
            raise TwoPATokenRequired("tenant deletion requires a 2PA challenge id")
        if self._two_pa is None:
            raise TwoPATokenRequired("2PA gate is not configured")
        try:
            consumed_2pa = await self._two_pa.consume_or_raise(
                challenge_id=two_pa_challenge_id,
                requester_id=requested_by_user_id,
            )
        except Exception as exc:
            raise TwoPATokenInvalid(str(exc)) from exc

        # 2. Tenant lookup + default-tenant + status guard.
        slug, _prior_status, contract_metadata = (
            await self._tenants.get_tenant_for_deletion(tenant_id=tenant_id)
        )

        # 3. Subscription preflight (FR-754.2).
        if self._subscriptions is not None:
            has_sub = await self._subscriptions.has_active_subscription(
                tenant_id=tenant_id
            )
            if has_sub:
                raise SubscriptionActiveCancelFirst(
                    f"tenant {tenant_id} still has an active subscription; "
                    "cancel via UPD-052 before requesting deletion"
                )

        # 4. Typed confirmation MUST equal "delete tenant {slug}".
        expected = f"delete tenant {slug}"
        if typed_confirmation.strip() != expected:
            raise TypedConfirmationMismatch(
                f"typed_confirmation must equal {expected!r}"
            )

        # 5. No concurrent active deletion job.
        existing = await self._repo.find_active_deletion_for_scope(
            scope_type=ScopeType.tenant.value, scope_id=tenant_id
        )
        if existing is not None:
            raise DeletionJobAlreadyActive(
                f"tenant {tenant_id} already has an active deletion job"
            )

        # 6. Grace resolution.
        grace = resolve_tenant_grace(
            settings=self._settings,
            tenant_contract_metadata=contract_metadata,
            request_override_days=grace_period_days_override,
        )
        now = self._clock()
        grace_ends_at = now + timedelta(days=grace.days)

        # 7. Cancel token (super admin uses /abort separately, but the
        #    schema requires a cancel_token_hash so we generate a unique
        #    placeholder that's effectively unguessable).
        cancel_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(cancel_token.encode("utf-8")).digest()

        # 8. Optional final-export job.
        final_export_job_id: UUID | None = None
        if include_final_export and self._export_request_handler is not None:
            try:
                final_export_job = await self._export_request_handler(
                    tenant_id=tenant_id,
                    requested_by_user_id=requested_by_user_id,
                    correlation_ctx=correlation_ctx,
                )
                final_export_job_id = getattr(final_export_job, "id", None)
            except Exception:
                logger.exception(
                    "data_lifecycle.tenant_final_export_request_failed",
                    extra={"tenant_id": str(tenant_id)},
                )

        # 9. Persist + flip tenant status.
        job = await self._repo.create_deletion_job(
            tenant_id=tenant_id,
            scope_type=ScopeType.tenant.value,
            scope_id=tenant_id,
            requested_by_user_id=requested_by_user_id,
            two_pa_token_id=two_pa_challenge_id,
            grace_period_days=grace.days,
            grace_ends_at=grace_ends_at,
            cancel_token_hash=token_hash,
            cancel_token_expires_at=grace_ends_at,
            final_export_job_id=final_export_job_id,
            correlation_id=getattr(correlation_ctx, "correlation_id", None),
        )
        await self._tenants.set_tenant_status(
            tenant_id=tenant_id, status="pending_deletion"
        )

        # 10. Audit + Kafka.
        await self._emit_audit(
            event_type="data_lifecycle.tenant_deletion_phase_1",
            payload={
                "job_id": str(job.id),
                "tenant_id": str(tenant_id),
                "actor_user_id": str(requested_by_user_id),
                "two_pa_challenge_id": str(two_pa_challenge_id),
                "two_pa_consumed_at": (consumed_2pa or {}).get(
                    "consumed_at", now.isoformat()
                ),
                "grace_period_days": grace.days,
                "grace_source": grace.source,
                "grace_ends_at": grace_ends_at.isoformat(),
                "final_export_job_id": (
                    str(final_export_job_id) if final_export_job_id else None
                ),
                "reason": reason,
            },
        )
        await publish_data_lifecycle_event(
            self._producer,
            DataLifecycleEventType.deletion_requested,
            DeletionRequestedPayload(
                job_id=job.id,
                scope_type=ScopeType.tenant.value,
                scope_id=tenant_id,
                grace_period_days=grace.days,
                grace_ends_at=grace_ends_at,
                two_pa_token_id=two_pa_challenge_id,
                final_export_job_id=final_export_job_id,
                correlation_context=_ensure_corr(correlation_ctx),
            ),
            _ensure_corr(correlation_ctx),
            partition_key=tenant_id,
        )
        return TenantDeletionRequestResult(
            job=job, final_export_job_id=final_export_job_id
        )

    async def extend_grace(
        self,
        *,
        job_id: UUID,
        additional_days: int,
        actor_user_id: UUID,
        reason: str,
        correlation_ctx: Any = None,
    ) -> DeletionJob:
        """Extend grace on a phase_1 job (super-admin only).

        Bounded by ``grace_max_days`` measured from job creation.
        """

        if additional_days < 1:
            raise GracePeriodOutOfRange("additional_days must be >= 1")
        job = await self._repo.get_deletion_job(job_id)
        if job is None:
            raise DeletionJobAlreadyFinalised(
                f"deletion job {job_id} not found"
            )
        if job.phase != DeletionPhase.phase_1.value:
            raise DeletionJobAlreadyFinalised(
                f"deletion job {job_id} is in {job.phase}; only phase_1 may extend grace"
            )
        new_ends_at = job.grace_ends_at + timedelta(days=additional_days)
        max_ends_at = job.created_at + timedelta(days=self._settings.grace_max_days)
        if new_ends_at > max_ends_at:
            raise GracePeriodOutOfRange(
                f"resulting grace_ends_at exceeds max ({self._settings.grace_max_days}d)"
            )
        await self._repo.extend_grace(job_id=job.id, new_grace_ends_at=new_ends_at)
        now = self._clock()
        await self._emit_audit(
            event_type=f"data_lifecycle.{job.scope_type}_deletion_grace_extended",
            payload={
                "job_id": str(job.id),
                "scope_id": str(job.scope_id),
                "additional_days": additional_days,
                "new_grace_ends_at": new_ends_at.isoformat(),
                "actor_user_id": str(actor_user_id),
                "reason": reason,
                "extended_at": now.isoformat(),
            },
        )
        return await self._repo.get_deletion_job(job_id)  # type: ignore[return-value]

    # ====================================================================
    # Anti-enumeration cancel (R10)
    # ====================================================================

    async def cancel_via_token(self, *, token: str) -> CancelOutcome:
        """Resolve a cancel attempt. Always returns; never raises.

        The router uses the result to emit audit but always sends the
        same response body (R10). Operators see the actual outcome via
        the audit chain.
        """

        token_hash = hashlib.sha256(token.encode("utf-8")).digest()
        job = await self._repo.find_deletion_by_cancel_token_hash(
            token_hash=token_hash
        )
        now = self._clock()
        if job is None:
            await self._emit_audit(
                event_type="data_lifecycle.cancel_token_invalid",
                payload={"reason": "token_unknown", "checked_at": now.isoformat()},
            )
            return CancelOutcome(succeeded=False, detail="token_unknown")
        if job.cancel_token_expires_at <= now:
            await self._emit_audit(
                event_type="data_lifecycle.cancel_token_invalid",
                payload={
                    "reason": "token_expired",
                    "job_id": str(job.id),
                    "checked_at": now.isoformat(),
                },
            )
            return CancelOutcome(succeeded=False, detail="token_expired")
        if job.phase != DeletionPhase.phase_1.value:
            # Either already-aborted or already-cascaded; both look
            # identical to the caller per anti-enumeration.
            await self._emit_audit(
                event_type="data_lifecycle.cancel_token_invalid",
                payload={
                    "reason": "wrong_phase",
                    "job_id": str(job.id),
                    "phase": job.phase,
                    "checked_at": now.isoformat(),
                },
            )
            return CancelOutcome(succeeded=False, detail="wrong_phase")

        # Success — flip job to aborted, restore workspace.
        await self._repo.update_deletion_phase(
            job_id=job.id,
            phase=DeletionPhase.aborted.value,
            abort_reason="owner_cancel_link",
        )
        if job.scope_type == ScopeType.workspace.value:
            await self._workspaces.set_workspace_status(
                workspace_id=job.scope_id, status="active"
            )
        await self._emit_audit(
            event_type=f"data_lifecycle.{job.scope_type}_deletion_aborted",
            payload={
                "job_id": str(job.id),
                "tenant_id": str(job.tenant_id),
                "scope_id": str(job.scope_id),
                "abort_source": "owner_cancel_link",
                "aborted_at": now.isoformat(),
            },
        )
        await publish_data_lifecycle_event(
            self._producer,
            DataLifecycleEventType.deletion_aborted,
            DeletionAbortedPayload(
                job_id=job.id,
                scope_type=job.scope_type,
                scope_id=job.scope_id,
                abort_source="owner_cancel_link",
                aborted_at=now,
                correlation_context=_ensure_corr(None),
            ),
            _ensure_corr(None),
            partition_key=job.tenant_id,
        )
        return CancelOutcome(succeeded=True, detail="cancelled")

    # ====================================================================
    # Superadmin abort during grace
    # ====================================================================

    async def abort_in_grace(
        self,
        *,
        job_id: UUID,
        actor_user_id: UUID,
        abort_reason: str,
        correlation_ctx: Any = None,
    ) -> DeletionJob:
        job = await self._repo.get_deletion_job(job_id)
        if job is None:
            raise DeletionJobAlreadyFinalised(
                f"deletion job {job_id} not found"
            )
        if job.phase == DeletionPhase.phase_2.value:
            raise CascadeInProgress(
                f"deletion job {job_id} is in phase_2; cannot abort"
            )
        if job.phase != DeletionPhase.phase_1.value:
            raise DeletionJobAlreadyFinalised(
                f"deletion job {job_id} is already {job.phase}"
            )
        await self._repo.update_deletion_phase(
            job_id=job.id,
            phase=DeletionPhase.aborted.value,
            abort_reason=abort_reason,
        )
        if job.scope_type == ScopeType.workspace.value:
            await self._workspaces.set_workspace_status(
                workspace_id=job.scope_id, status="active"
            )
        elif (
            job.scope_type == ScopeType.tenant.value
            and self._tenants is not None
        ):
            # FR-754.4 recovery — restore tenant to active.
            await self._tenants.set_tenant_status(
                tenant_id=job.scope_id, status="active"
            )
        now = self._clock()
        await self._emit_audit(
            event_type=f"data_lifecycle.{job.scope_type}_deletion_aborted",
            payload={
                "job_id": str(job.id),
                "tenant_id": str(job.tenant_id),
                "scope_id": str(job.scope_id),
                "abort_source": "super_admin",
                "actor_user_id": str(actor_user_id),
                "abort_reason": abort_reason,
                "aborted_at": now.isoformat(),
            },
        )
        await publish_data_lifecycle_event(
            self._producer,
            DataLifecycleEventType.deletion_aborted,
            DeletionAbortedPayload(
                job_id=job.id,
                scope_type=job.scope_type,
                scope_id=job.scope_id,
                abort_source="super_admin",
                aborted_at=now,
                correlation_context=_ensure_corr(correlation_ctx),
            ),
            _ensure_corr(correlation_ctx),
            partition_key=job.tenant_id,
        )
        # Refresh from DB so the caller sees phase=aborted.
        return await self._repo.get_deletion_job(job_id)  # type: ignore[return-value]

    # ====================================================================
    # Phase 1 -> Phase 2 advance (cron-driven)
    # ====================================================================

    async def advance_grace_expired_jobs(self, *, limit: int = 100) -> int:
        """Find phase_1 jobs whose grace has expired and dispatch phase_2.

        Returns the count of jobs advanced. Idempotent: a job that's
        already advanced is skipped because the partial-unique index
        and the phase check prevent re-entry.
        """

        now = self._clock()
        jobs = await self._repo.list_grace_expired_phase_1_jobs(
            now=now, limit=limit
        )
        advanced = 0
        for job in jobs:
            try:
                await self._advance_one(job, now=now)
                advanced += 1
            except Exception:
                logger.exception(
                    "data_lifecycle.advance_phase_2_failed",
                    extra={"job_id": str(job.id)},
                )
        return advanced

    async def _advance_one(self, job: DeletionJob, *, now: datetime) -> None:
        await self._repo.update_deletion_phase(
            job_id=job.id,
            phase=DeletionPhase.phase_2.value,
            cascade_started_at=now,
        )
        await publish_data_lifecycle_event(
            self._producer,
            DataLifecycleEventType.deletion_phase_advanced,
            DeletionPhaseAdvancedPayload(
                job_id=job.id,
                from_phase=DeletionPhase.phase_1.value,
                to_phase=DeletionPhase.phase_2.value,
                advanced_at=now,
                correlation_context=_ensure_corr(None),
            ),
            _ensure_corr(None),
            partition_key=job.tenant_id,
        )
        await self._emit_audit(
            event_type=f"data_lifecycle.{job.scope_type}_deletion_phase_2",
            payload={
                "job_id": str(job.id),
                "tenant_id": str(job.tenant_id),
                "scope_id": str(job.scope_id),
                "advanced_at": now.isoformat(),
            },
        )
        # Cascade dispatch — workspace path delegates to
        # ``cascade_dispatch.workspace_cascade``; tenant path uses the
        # ``cascade_dispatch.tenant_cascade`` adapter (which also calls
        # the UPD-053 DNS teardown leg behind a feature flag).
        dispatcher = (
            self._tenant_cascade_dispatcher
            if job.scope_type == ScopeType.tenant.value
            else self._cascade_dispatcher
        )
        if dispatcher is None:
            return
        try:
            if job.scope_type == ScopeType.tenant.value:
                cascade_result = await dispatcher(
                    tenant_id=job.scope_id,
                    requested_by_user_id=job.requested_by_user_id,
                )
            else:
                cascade_result = await dispatcher(
                    workspace_id=job.scope_id,
                    requested_by_user_id=job.requested_by_user_id,
                )
            completed_at = self._clock()
            await self._repo.update_deletion_phase(
                job_id=job.id,
                phase=DeletionPhase.completed.value,
                cascade_completed_at=completed_at,
            )
            if job.scope_type == ScopeType.workspace.value:
                await self._workspaces.set_workspace_status(
                    workspace_id=job.scope_id, status="deleted"
                )
            elif (
                job.scope_type == ScopeType.tenant.value
                and self._tenants is not None
            ):
                # Tenant table only models active/suspended/pending_deletion;
                # the cascade itself removes the row, so this is best-effort.
                try:
                    await self._tenants.set_tenant_status(
                        tenant_id=job.scope_id, status="deleted"
                    )
                except Exception:
                    pass
            await self._emit_audit(
                event_type=(
                    f"data_lifecycle.{job.scope_type}_deletion_completed"
                ),
                payload={
                    "job_id": str(job.id),
                    "tenant_id": str(job.tenant_id),
                    "scope_id": str(job.scope_id),
                    "errors": len(cascade_result.get("errors", [])),
                    "completed_at": completed_at.isoformat(),
                },
            )
        except Exception:
            logger.exception(
                "data_lifecycle.cascade_failed",
                extra={"job_id": str(job.id)},
            )

    # ====================================================================
    # Audit emission helper
    # ====================================================================

    async def _emit_audit(
        self,
        *,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        if self._audit is None:
            return
        canonical = json.dumps(
            {"event_type": event_type, **payload},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        try:
            await self._audit.append(uuid4(), "data_lifecycle", canonical)
        except Exception:
            logger.exception(
                "data_lifecycle.audit_emission_failed",
                extra={"event_type": event_type},
            )


def _ensure_corr(ctx: Any) -> CorrelationContext:
    if isinstance(ctx, CorrelationContext):
        return ctx
    return CorrelationContext(correlation_id=uuid4())
