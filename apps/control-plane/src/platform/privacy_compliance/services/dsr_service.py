from __future__ import annotations

import binascii
import hashlib
import json
from base64 import urlsafe_b64decode
from datetime import UTC, datetime, timedelta
from platform.privacy_compliance.events import (
    DSRLifecyclePayload,
    PrivacyEventPublisher,
    PrivacyEventType,
    make_correlation,
    utcnow,
)
from platform.privacy_compliance.exceptions import CascadePartialFailure, DSRNotFoundError
from platform.privacy_compliance.models import DSRRequestType, DSRStatus, PrivacyDSRRequest
from platform.privacy_compliance.repository import PrivacyComplianceRepository
from platform.privacy_compliance.schemas import DSRCreateRequest, DSRResponse
from typing import Any
from uuid import UUID


class DSRService:
    def __init__(
        self,
        *,
        repository: PrivacyComplianceRepository,
        event_publisher: PrivacyEventPublisher,
        orchestrator: Any | None = None,
        audit_chain: Any | None = None,
    ) -> None:
        self.repository = repository
        self.events = event_publisher
        self.orchestrator = orchestrator
        self.audit_chain = audit_chain

    async def create_request(
        self,
        payload: DSRCreateRequest,
        *,
        requested_by: UUID,
    ) -> DSRResponse:
        now = datetime.now(UTC)
        status = DSRStatus.scheduled if payload.hold_hours > 0 else DSRStatus.received
        dsr = await self.repository.create_dsr(
            PrivacyDSRRequest(
                subject_user_id=payload.subject_user_id,
                request_type=payload.request_type.value,
                requested_by=requested_by,
                status=status.value,
                legal_basis=payload.legal_basis,
                scheduled_release_at=(
                    now + timedelta(hours=payload.hold_hours)
                    if payload.hold_hours > 0
                    else None
                ),
                requested_at=now,
            )
        )
        await self._audit_and_publish(
            PrivacyEventType.dsr_scheduled_with_hold
            if status is DSRStatus.scheduled
            else PrivacyEventType.dsr_received,
            dsr,
        )
        return DSRResponse.model_validate(dsr)

    async def list_requests(
        self,
        *,
        subject_user_id: UUID | None = None,
        request_type: str | None = None,
        status: str | None = None,
    ) -> list[DSRResponse]:
        items = await self.repository.list_dsrs(
            subject_user_id=subject_user_id,
            request_type=request_type,
            status=status,
        )
        return [DSRResponse.model_validate(item) for item in items]

    async def list_for_subject(
        self,
        subject_user_id: UUID,
        limit: int,
        cursor: str | None,
    ) -> list[DSRResponse]:
        offset = _decode_offset_cursor(cursor)
        items = await self.repository.list_dsrs(subject_user_id=subject_user_id)
        limited = items[offset : offset + limit]
        return [DSRResponse.model_validate(item) for item in limited]

    async def get_request(self, dsr_id: UUID) -> DSRResponse:
        return DSRResponse.model_validate(await self._get_dsr(dsr_id))

    async def cancel(self, dsr_id: UUID, *, reason: str) -> DSRResponse:
        dsr = await self._get_dsr(dsr_id)
        if dsr.status != DSRStatus.scheduled.value:
            raise ValueError("only scheduled DSRs can be cancelled")
        await self.repository.update_dsr(
            dsr,
            status=DSRStatus.cancelled.value,
            failure_reason=reason,
        )
        await self._audit_and_publish(PrivacyEventType.dsr_failed, dsr)
        return DSRResponse.model_validate(dsr)

    async def process(self, dsr_id: UUID) -> DSRResponse:
        dsr = await self._get_dsr(dsr_id)
        await self.repository.update_dsr(dsr, status=DSRStatus.in_progress.value)
        await self._audit_and_publish(PrivacyEventType.dsr_in_progress, dsr)
        try:
            if dsr.request_type == DSRRequestType.erasure.value and self.orchestrator is not None:
                tombstone = await self.orchestrator.run(dsr.id, dsr.subject_user_id)
                proof_hash = tombstone.proof_hash
                tombstone_id = tombstone.id
            else:
                proof_hash = self._completion_hash(dsr)
                tombstone_id = None
            await self.repository.update_dsr(
                dsr,
                status=DSRStatus.completed.value,
                completed_at=datetime.now(UTC),
                completion_proof_hash=proof_hash,
                tombstone_id=tombstone_id,
            )
            await self._audit_and_publish(PrivacyEventType.dsr_completed, dsr)
        except CascadePartialFailure as exc:
            await self.repository.update_dsr(
                dsr,
                status=DSRStatus.failed.value,
                completed_at=datetime.now(UTC),
                failure_reason="; ".join(exc.errors),
                tombstone_id=getattr(exc.tombstone, "id", None),
            )
            await self._audit_and_publish(PrivacyEventType.dsr_failed, dsr)
        return DSRResponse.model_validate(dsr)

    async def retry(self, dsr_id: UUID) -> DSRResponse:
        dsr = await self._get_dsr(dsr_id)
        if dsr.status != DSRStatus.failed.value:
            raise ValueError("only failed DSRs can be retried")
        return await self.process(dsr_id)

    async def release_due_holds(self, now: datetime | None = None) -> list[DSRResponse]:
        due = await self.repository.list_due_scheduled_dsrs(now or datetime.now(UTC))
        responses = []
        for dsr in due:
            responses.append(await self.process(dsr.id))
        return responses

    async def _get_dsr(self, dsr_id: UUID) -> PrivacyDSRRequest:
        dsr = await self.repository.get_dsr(dsr_id)
        if dsr is None:
            raise DSRNotFoundError(dsr_id)
        return dsr

    def _completion_hash(self, dsr: PrivacyDSRRequest) -> str:
        payload = {
            "dsr_id": str(dsr.id),
            "subject_user_id": str(dsr.subject_user_id),
            "request_type": dsr.request_type,
            "status": DSRStatus.completed.value,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    async def _audit_and_publish(
        self,
        event_type: PrivacyEventType,
        dsr: PrivacyDSRRequest,
    ) -> None:
        payload = DSRLifecyclePayload(
            dsr_id=dsr.id,
            subject_user_id=dsr.subject_user_id,
            request_type=dsr.request_type,
            status=dsr.status,
            occurred_at=utcnow(),
            tombstone_id=dsr.tombstone_id,
            failure_reason=dsr.failure_reason,
        )
        append = getattr(self.audit_chain, "append", None)
        if callable(append):
            await append(dsr.id, "privacy_compliance", payload.model_dump_json().encode("utf-8"))
        await self.events.publish(
            event_type,
            payload,
            key=str(dsr.subject_user_id),
            correlation_ctx=make_correlation(),
        )


def _decode_offset_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        decoded = urlsafe_b64decode(cursor.encode("ascii")).decode("ascii")
        return max(0, int(decoded))
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return 0
