from __future__ import annotations

import hashlib
import json
from datetime import datetime
from platform.audit.events import (
    AuditChainVerifiedPayload,
    publish_audit_chain_verified_event,
)
from platform.audit.exceptions import AuditChainIntegrityError
from platform.audit.models import AuditChainEntry
from platform.audit.repository import AuditChainRepository
from platform.audit.schemas import SignedAttestation, VerifyResult
from platform.audit.signing import AuditChainSigning
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.logging import get_logger
from typing import Any
from uuid import UUID, uuid4

GENESIS_HASH = "0" * 64


def compute_entry_hash(
    *,
    previous_hash: str,
    sequence_number: int,
    canonical_payload_hash: str,
) -> str:
    return hashlib.sha256(
        previous_hash.encode("ascii")
        + sequence_number.to_bytes(8, "big")
        + canonical_payload_hash.encode("ascii")
    ).hexdigest()


class AuditChainService:
    def __init__(
        self,
        repository: AuditChainRepository,
        settings: PlatformSettings,
        signing: AuditChainSigning | None = None,
        producer: EventProducer | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.signing = signing or AuditChainSigning(settings.audit)
        self.producer = producer

    async def append(
        self,
        audit_event_id: UUID | None,
        audit_event_source: str,
        canonical_payload: bytes,
        *,
        event_type: str | None = None,
        actor_role: str | None = None,
        severity: str = "info",
        canonical_payload_json: dict[str, object] | None = None,
        impersonation_user_id: UUID | None = None,
    ) -> AuditChainEntry:
        await self.repository.acquire_append_lock()
        latest = await self.repository.get_latest_entry()
        sequence_number = await self.repository.next_sequence_number()
        previous_hash = latest.entry_hash if latest is not None else GENESIS_HASH
        canonical_payload_hash = hashlib.sha256(canonical_payload).hexdigest()
        persisted_payload = canonical_payload_json or self._decode_payload(canonical_payload)
        entry_hash = compute_entry_hash(
            previous_hash=previous_hash,
            sequence_number=sequence_number,
            canonical_payload_hash=canonical_payload_hash,
        )
        entry = await self.repository.insert_entry(
            sequence_number=sequence_number,
            previous_hash=previous_hash,
            entry_hash=entry_hash,
            audit_event_id=audit_event_id,
            audit_event_source=audit_event_source,
            canonical_payload_hash=canonical_payload_hash,
            event_type=event_type,
            actor_role=actor_role,
            severity=severity,
            canonical_payload=persisted_payload,
            impersonation_user_id=impersonation_user_id,
        )
        get_logger(__name__).info(
            "audit.chain.appended",
            sequence_number=sequence_number,
            audit_event_source=audit_event_source,
            canonical_payload_hash=canonical_payload_hash,
            entry_hash=entry_hash,
        )
        return entry

    @staticmethod
    def _decode_payload(canonical_payload: bytes) -> dict[str, Any] | None:
        try:
            decoded = json.loads(canonical_payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return decoded if isinstance(decoded, dict) else None

    async def verify(
        self,
        start_seq: int | None = None,
        end_seq: int | None = None,
    ) -> VerifyResult:
        latest = await self.repository.get_latest_entry()
        if latest is None:
            result = VerifyResult(valid=True, entries_checked=0, broken_at=None)
            await self._publish_verification(result, start_seq, end_seq)
            return result
        start = start_seq or 1
        end = end_seq or latest.sequence_number
        entries = await self.repository.get_by_sequence_range(start, end)
        previous_hash = GENESIS_HASH
        if start > 1:
            previous = await self.repository.get_by_sequence(start - 1)
            previous_hash = previous.entry_hash if previous is not None else GENESIS_HASH

        for index, entry in enumerate(entries):
            expected = compute_entry_hash(
                previous_hash=previous_hash,
                sequence_number=entry.sequence_number,
                canonical_payload_hash=entry.canonical_payload_hash,
            )
            if expected != entry.entry_hash:
                result = VerifyResult(
                    valid=False,
                    entries_checked=index + 1,
                    broken_at=entry.sequence_number,
                )
                await self._publish_verification(result, start_seq, end_seq)
                return result
            previous_hash = entry.entry_hash
        result = VerifyResult(valid=True, entries_checked=len(entries), broken_at=None)
        await self._publish_verification(result, start_seq, end_seq)
        return result

    async def list_audit_sources_in_window(
        self,
        start_ts: datetime,
        end_ts: datetime,
        sources: list[str] | None = None,
    ) -> list[AuditChainEntry]:
        return await self.repository.list_audit_sources_in_window(start_ts, end_ts, sources)

    async def list_entries_by_actor_or_subject(
        self,
        actor_id: UUID | None,
        subject_id: UUID | None,
        start_ts: datetime | None,
        end_ts: datetime | None,
        limit: int,
        cursor: str | None,
        event_type: str | None = None,
    ) -> tuple[list[AuditChainEntry], str | None]:
        return await self.repository.list_entries_by_actor_or_subject(
            actor_id=actor_id,
            subject_id=subject_id,
            start_ts=start_ts,
            end_ts=end_ts,
            event_type=event_type,
            limit=limit,
            cursor=cursor,
        )

    async def export_attestation(self, start_seq: int, end_seq: int) -> SignedAttestation:
        verification = await self.verify(start_seq, end_seq)
        if not verification.valid:
            raise AuditChainIntegrityError(f"Audit chain broken at {verification.broken_at}")
        entries = await self.repository.get_by_sequence_range(start_seq, end_seq)
        if not entries:
            raise AuditChainIntegrityError("Cannot attest an empty audit chain range")
        document = {
            "platform": "musematic",
            "env": self.settings.profile,
            "start_seq": start_seq,
            "end_seq": end_seq,
            "start_entry_hash": entries[0].entry_hash,
            "end_entry_hash": entries[-1].entry_hash,
            "window_start_time": entries[0].created_at.isoformat(),
            "window_end_time": entries[-1].created_at.isoformat(),
            "chain_entries_count": len(entries),
            "key_version": 1,
        }
        payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
        signature = self.signing.sign(payload).hex()
        return SignedAttestation.model_validate({**document, "signature": signature})

    async def get_public_verifying_key(self) -> str:
        return self.signing.public_key_hex

    async def _publish_verification(
        self,
        result: VerifyResult,
        start_seq: int | None,
        end_seq: int | None,
    ) -> None:
        await publish_audit_chain_verified_event(
            AuditChainVerifiedPayload(
                valid=result.valid,
                entries_checked=result.entries_checked,
                broken_at=result.broken_at,
                start_seq=start_seq,
                end_seq=end_seq,
            ),
            CorrelationContext(correlation_id=uuid4()),
            self.producer,
        )
