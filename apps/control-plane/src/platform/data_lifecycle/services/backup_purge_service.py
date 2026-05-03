"""Backup purge — schedule + execute key-destruction for deleted tenants.

Per FR-759 + R4: 30 days after a tenant cascade completes, the platform
re-keys the tenant's encrypted backup segment and destroys the prior
key. The cipher-text remains for regulatory retention but is
unrecoverable, satisfying GDPR right-to-be-forgotten.

This service has two surfaces:

* :meth:`BackupPurgeService.schedule_purge_for_tenant` — called by the
  tenant cascade dispatcher at phase_2 completion. Marks the tenant
  for purge at ``cascade_completed_at + backup_purge_offset_days``.
* :meth:`BackupPurgeService.run_due_purges` — APScheduler cron tick.
  Finds scheduled purges whose target time has elapsed, calls the KMS
  key-destruction adapter, audits + emits the
  ``data_lifecycle.backup.purge_completed`` event.

For the MVP we persist scheduled purges as audit-chain entries +
correlate via the deletion job's ``cascade_completed_at`` rather than
introducing a new table. A follow-up may promote this to its own
ledger if the operator surface needs richer queries.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from platform.common.config import DataLifecycleSettings
from platform.common.events.envelope import CorrelationContext
from platform.data_lifecycle.events import (
    BackupPurgeCompletedPayload,
    DataLifecycleEventType,
    publish_data_lifecycle_event,
)
from platform.data_lifecycle.models import DeletionPhase, ScopeType

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _DuePurge:
    tenant_id: UUID
    cascade_completed_at: datetime
    deletion_job_id: UUID


class _KMSKeyDestroyer(Protocol):
    """Subset of the KMS rotation client we need for key-shred."""

    async def destroy_tenant_data_key(
        self, *, tenant_id: UUID
    ) -> dict[str, Any]:
        """Destroy the data-encryption key for a tenant.

        Returns ``{"kms_key_id": ..., "kms_key_version": ...}``. Raises
        on failure; the caller treats partial failures as transient and
        retries on the next cron tick.
        """


class _AuditAppender(Protocol):
    async def append(
        self, audit_event_id: UUID, namespace: str, canonical_payload: bytes
    ) -> Any:
        ...


class _EventProducer(Protocol):
    async def publish(self, **kwargs: Any) -> Any:
        ...


class BackupPurgeService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: DataLifecycleSettings,
        kms_destroyer: _KMSKeyDestroyer | None,
        audit_chain: _AuditAppender | None,
        event_producer: _EventProducer | None,
        clock: Any = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._kms = kms_destroyer
        self._audit = audit_chain
        self._producer = event_producer
        self._clock = clock or (lambda: datetime.now(UTC))

    async def schedule_purge_for_tenant(
        self,
        *,
        tenant_id: UUID,
        cascade_completed_at: datetime,
        deletion_job_id: UUID,
    ) -> None:
        """Record that the tenant's backup is due for purge.

        Stored as an audit chain entry because:
          * The audit chain is the regulatory-binding ledger (rule 9 +
            AD-18) — auditors trust the chain, not auxiliary tables.
          * The cron query reads from ``deletion_jobs.cascade_completed_at``
            so no extra table lookup is needed.
        """

        purge_at = cascade_completed_at + timedelta(
            days=self._settings.backup_purge_offset_days
        )
        await self._emit_audit(
            event_type="data_lifecycle.backup_purge_scheduled",
            payload={
                "tenant_id": str(tenant_id),
                "deletion_job_id": str(deletion_job_id),
                "cascade_completed_at": cascade_completed_at.isoformat(),
                "purge_at": purge_at.isoformat(),
                "method": "key_destruction",
            },
        )

    async def run_due_purges(self, *, limit: int = 50) -> int:
        """Cron tick — find tenants past their purge target and shred keys.

        Returns the number of purges processed.
        """

        now = self._clock()
        cutoff = now - timedelta(days=self._settings.backup_purge_offset_days)
        result = await self._session.execute(
            text(
                f"""
                SELECT id::text AS deletion_job_id,
                       scope_id::text AS tenant_id,
                       cascade_completed_at
                FROM deletion_jobs
                WHERE phase = '{DeletionPhase.completed.value}'
                  AND scope_type = '{ScopeType.tenant.value}'
                  AND cascade_completed_at IS NOT NULL
                  AND cascade_completed_at <= :cutoff
                  AND tombstone_id IS NOT NULL
                ORDER BY cascade_completed_at ASC
                LIMIT :limit
                """
            ),
            {"cutoff": cutoff.isoformat(), "limit": limit},
        )
        purged = 0
        for row in result.mappings().all():
            try:
                await self._purge_one(
                    _DuePurge(
                        tenant_id=UUID(str(row["tenant_id"])),
                        deletion_job_id=UUID(str(row["deletion_job_id"])),
                        cascade_completed_at=row["cascade_completed_at"],
                    )
                )
                purged += 1
            except Exception:
                logger.exception(
                    "data_lifecycle.backup_purge_failed",
                    extra={"tenant_id": str(row["tenant_id"])},
                )
        return purged

    async def _purge_one(self, due: _DuePurge) -> None:
        if self._kms is None:
            logger.warning(
                "data_lifecycle.backup_purge_skipped_no_kms",
                extra={"tenant_id": str(due.tenant_id)},
            )
            return
        result = await self._kms.destroy_tenant_data_key(tenant_id=due.tenant_id)
        kms_key_id = str(result.get("kms_key_id", "unknown"))
        kms_key_version = int(result.get("kms_key_version", 0))
        completed = self._clock()
        await self._emit_audit(
            event_type="data_lifecycle.backup_purge_completed",
            payload={
                "tenant_id": str(due.tenant_id),
                "deletion_job_id": str(due.deletion_job_id),
                "kms_key_id": kms_key_id,
                "kms_key_version": kms_key_version,
                "purge_completed_at": completed.isoformat(),
                "method": "key_destruction",
            },
        )
        if self._producer is not None:
            ctx = CorrelationContext(correlation_id=uuid4())
            await publish_data_lifecycle_event(
                self._producer,
                DataLifecycleEventType.backup_purge_completed,
                BackupPurgeCompletedPayload(
                    tenant_id=due.tenant_id,
                    purge_method="key_destruction",
                    kms_key_id=kms_key_id,
                    kms_key_version=kms_key_version,
                    purge_completed_at=completed,
                    cold_storage_objects_retained=0,
                    correlation_context=ctx,
                ),
                ctx,
                partition_key=due.tenant_id,
            )

    async def _emit_audit(
        self, *, event_type: str, payload: dict[str, Any]
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
            logger.exception("data_lifecycle.audit_emission_failed")
