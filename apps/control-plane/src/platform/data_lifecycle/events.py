"""Kafka event types for the data_lifecycle bounded context.

Topic: ``data_lifecycle.events`` (registered via Strimzi KafkaTopic CRD;
12 partitions; 30-day retention; partitioned by ``tenant_id``).

See ``specs/104-data-lifecycle/contracts/data-lifecycle-events-kafka.md``.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Final
from uuid import UUID

from pydantic import BaseModel

from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry

KAFKA_TOPIC: Final[str] = "data_lifecycle.events"


class DataLifecycleEventType(StrEnum):
    export_requested = "data_lifecycle.export.requested"
    export_started = "data_lifecycle.export.started"
    export_completed = "data_lifecycle.export.completed"
    export_failed = "data_lifecycle.export.failed"
    deletion_requested = "data_lifecycle.deletion.requested"
    deletion_phase_advanced = "data_lifecycle.deletion.phase_advanced"
    deletion_aborted = "data_lifecycle.deletion.aborted"
    deletion_completed = "data_lifecycle.deletion.completed"
    dpa_uploaded = "data_lifecycle.dpa.uploaded"
    dpa_removed = "data_lifecycle.dpa.removed"
    sub_processor_added = "data_lifecycle.sub_processor.added"
    sub_processor_modified = "data_lifecycle.sub_processor.modified"
    sub_processor_removed = "data_lifecycle.sub_processor.removed"
    backup_purge_completed = "data_lifecycle.backup.purge_completed"


# ---------------------------------------------------------------------------
# Export payloads
# ---------------------------------------------------------------------------


class ExportRequestedPayload(BaseModel):
    job_id: UUID
    scope_type: str
    scope_id: UUID
    requested_at: datetime
    estimated_size_bytes_lower_bound: int = 0
    correlation_context: CorrelationContext


class ExportStartedPayload(BaseModel):
    job_id: UUID
    worker_id: str
    started_at: datetime
    correlation_context: CorrelationContext


class ExportCompletedPayload(BaseModel):
    job_id: UUID
    output_size_bytes: int
    output_url_expires_at: datetime
    completed_at: datetime
    correlation_context: CorrelationContext


class ExportFailedPayload(BaseModel):
    job_id: UUID
    failure_reason_code: str
    retries_remaining: int
    failed_at: datetime
    correlation_context: CorrelationContext


# ---------------------------------------------------------------------------
# Deletion payloads
# ---------------------------------------------------------------------------


class DeletionRequestedPayload(BaseModel):
    job_id: UUID
    scope_type: str
    scope_id: UUID
    grace_period_days: int
    grace_ends_at: datetime
    two_pa_token_id: UUID | None = None
    final_export_job_id: UUID | None = None
    correlation_context: CorrelationContext


class DeletionPhaseAdvancedPayload(BaseModel):
    job_id: UUID
    from_phase: str
    to_phase: str
    advanced_at: datetime
    correlation_context: CorrelationContext


class DeletionAbortedPayload(BaseModel):
    job_id: UUID
    scope_type: str
    scope_id: UUID
    abort_source: str
    aborted_at: datetime
    correlation_context: CorrelationContext


class StoreResult(BaseModel):
    store: str
    rows_affected: int


class DeletionCompletedPayload(BaseModel):
    job_id: UUID
    scope_type: str
    scope_id: UUID
    tombstone_id: UUID
    store_results: list[StoreResult]
    cascade_started_at: datetime
    cascade_completed_at: datetime
    correlation_context: CorrelationContext


# ---------------------------------------------------------------------------
# DPA payloads
# ---------------------------------------------------------------------------


class DPAUploadedPayload(BaseModel):
    tenant_id: UUID
    dpa_version: str
    sha256: str
    effective_date: datetime
    vault_path_redacted: str
    correlation_context: CorrelationContext


class DPARemovedPayload(BaseModel):
    tenant_id: UUID
    dpa_version: str
    removed_at: datetime
    correlation_context: CorrelationContext


# ---------------------------------------------------------------------------
# Sub-processor payloads
# ---------------------------------------------------------------------------


class SubProcessorChangedPayload(BaseModel):
    sub_processor_id: UUID
    name: str
    category: str
    is_active: bool
    changed_at: datetime
    correlation_context: CorrelationContext


# ---------------------------------------------------------------------------
# Backup-purge payload
# ---------------------------------------------------------------------------


class BackupPurgeCompletedPayload(BaseModel):
    tenant_id: UUID
    purge_method: str
    kms_key_id: str
    kms_key_version: int
    purge_completed_at: datetime
    cold_storage_objects_retained: int
    correlation_context: CorrelationContext


DATA_LIFECYCLE_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    DataLifecycleEventType.export_requested.value: ExportRequestedPayload,
    DataLifecycleEventType.export_started.value: ExportStartedPayload,
    DataLifecycleEventType.export_completed.value: ExportCompletedPayload,
    DataLifecycleEventType.export_failed.value: ExportFailedPayload,
    DataLifecycleEventType.deletion_requested.value: DeletionRequestedPayload,
    DataLifecycleEventType.deletion_phase_advanced.value: DeletionPhaseAdvancedPayload,
    DataLifecycleEventType.deletion_aborted.value: DeletionAbortedPayload,
    DataLifecycleEventType.deletion_completed.value: DeletionCompletedPayload,
    DataLifecycleEventType.dpa_uploaded.value: DPAUploadedPayload,
    DataLifecycleEventType.dpa_removed.value: DPARemovedPayload,
    DataLifecycleEventType.sub_processor_added.value: SubProcessorChangedPayload,
    DataLifecycleEventType.sub_processor_modified.value: SubProcessorChangedPayload,
    DataLifecycleEventType.sub_processor_removed.value: SubProcessorChangedPayload,
    DataLifecycleEventType.backup_purge_completed.value: BackupPurgeCompletedPayload,
}


def register_data_lifecycle_event_types() -> None:
    """Register all data_lifecycle event payloads with the global registry.

    Called from ``main.py`` startup. Idempotent — safe to call multiple
    times because the registry deduplicates on event type.
    """

    for event_type, schema in DATA_LIFECYCLE_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


async def publish_data_lifecycle_event(
    producer: EventProducer | None,
    event_type: DataLifecycleEventType | str,
    payload: BaseModel,
    correlation_ctx: CorrelationContext,
    *,
    partition_key: str | UUID,
    source: str = "platform.data_lifecycle",
) -> None:
    """Publish a data_lifecycle event partitioned by ``partition_key``.

    The partition key is typically ``tenant_id`` so per-tenant ordering
    is preserved.
    """

    if producer is None:
        return
    event_name = (
        event_type.value
        if isinstance(event_type, DataLifecycleEventType)
        else event_type
    )
    payload_dict = payload.model_dump(mode="json")
    await producer.publish(
        topic=KAFKA_TOPIC,
        key=str(partition_key),
        event_type=event_name,
        payload=payload_dict,
        correlation_ctx=correlation_ctx,
        source=source,
    )
