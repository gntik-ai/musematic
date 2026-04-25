from __future__ import annotations

from datetime import UTC, datetime
from platform.audit.service import AuditChainService
from platform.common.audit_hook import audit_chain_hook
from platform.common.events.producer import EventProducer
from platform.model_catalog.events import (
    ModelDeprecatedPayload,
    publish_model_deprecated,
)
from platform.model_catalog.repository import ModelCatalogRepository
from typing import Any
from uuid import uuid4


async def run_auto_deprecation_scan(
    *,
    repository: ModelCatalogRepository,
    producer: EventProducer | None = None,
    audit_chain: AuditChainService | None = None,
    compliance_service: Any | None = None,
    now: datetime | None = None,
) -> dict[str, int]:
    scan_time = now or datetime.now(UTC)
    deprecated_count = 0
    for entry in await repository.list_expired_approved_entries(now=scan_time):
        entry.status = "deprecated"
        entry.updated_at = scan_time
        deprecated_count += 1
        await publish_model_deprecated(
            ModelDeprecatedPayload(
                catalog_entry_id=entry.id,
                provider=entry.provider,
                model_id=entry.model_id,
                approval_expires_at=entry.approval_expires_at,
            ),
            uuid4(),
            producer,
        )
        if audit_chain is not None:
            await audit_chain_hook(
                audit_chain,
                entry.id,
                "model_catalog",
                {
                    "event": "model.deprecated",
                    "catalog_entry_id": entry.id,
                    "provider": entry.provider,
                    "model_id": entry.model_id,
                    "approval_expires_at": entry.approval_expires_at,
                },
            )

    gap_count = 0
    if compliance_service is not None:
        handler = getattr(compliance_service, "on_security_event", None)
        if callable(handler):
            for entry in await repository.list_entries_missing_cards(older_than_days=7):
                await handler(
                    evidence_type="model_card_missing",
                    source="model_catalog",
                    entity_id=str(entry.id),
                    payload={
                        "catalog_entry_id": str(entry.id),
                        "provider": entry.provider,
                        "model_id": entry.model_id,
                    },
                )
                gap_count += 1
    await repository.session.flush()
    return {"deprecated": deprecated_count, "compliance_gaps": gap_count}
