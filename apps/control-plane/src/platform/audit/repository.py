from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime
from platform.audit.models import AuditChainEntry
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

AUDIT_CHAIN_APPEND_LOCK_ID = 740_740_001


class AuditChainRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def acquire_append_lock(self) -> None:
        await self.session.execute(select(func.pg_advisory_xact_lock(AUDIT_CHAIN_APPEND_LOCK_ID)))

    async def next_sequence_number(self) -> int:
        result = await self.session.execute(select(func.max(AuditChainEntry.sequence_number)))
        latest = result.scalar_one_or_none()
        return int(latest or 0) + 1

    async def insert_entry(
        self,
        *,
        sequence_number: int,
        previous_hash: str,
        entry_hash: str,
        audit_event_id: UUID | None,
        audit_event_source: str,
        canonical_payload_hash: str,
        event_type: str | None = None,
        actor_role: str | None = None,
        severity: str = "info",
        canonical_payload: dict[str, object] | None = None,
        impersonation_user_id: UUID | None = None,
    ) -> AuditChainEntry:
        entry = AuditChainEntry(
            sequence_number=sequence_number,
            previous_hash=previous_hash,
            entry_hash=entry_hash,
            audit_event_id=audit_event_id,
            audit_event_source=audit_event_source,
            canonical_payload_hash=canonical_payload_hash,
            event_type=event_type,
            actor_role=actor_role,
            severity=severity,
            canonical_payload=canonical_payload,
            impersonation_user_id=impersonation_user_id,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def get_latest_entry(self) -> AuditChainEntry | None:
        result = await self.session.execute(
            select(AuditChainEntry).order_by(AuditChainEntry.sequence_number.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_sequence_range(
        self,
        start_seq: int,
        end_seq: int,
    ) -> list[AuditChainEntry]:
        statement: Select[tuple[AuditChainEntry]] = (
            select(AuditChainEntry)
            .where(AuditChainEntry.sequence_number >= start_seq)
            .where(AuditChainEntry.sequence_number <= end_seq)
            .order_by(AuditChainEntry.sequence_number.asc())
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def list_audit_sources_in_window(
        self,
        start_ts: datetime,
        end_ts: datetime,
        sources: list[str] | None = None,
    ) -> list[AuditChainEntry]:
        statement = (
            select(AuditChainEntry)
            .where(AuditChainEntry.created_at >= start_ts)
            .where(AuditChainEntry.created_at <= end_ts)
        )
        if sources:
            statement = statement.where(AuditChainEntry.audit_event_source.in_(sources))
        result = await self.session.execute(
            statement.order_by(AuditChainEntry.created_at.asc(), AuditChainEntry.id.asc())
        )
        return list(result.scalars().all())

    async def list_entries_by_actor_or_subject(
        self,
        *,
        actor_id: UUID | None,
        subject_id: UUID | None,
        start_ts: datetime | None,
        end_ts: datetime | None,
        event_type: str | None,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[AuditChainEntry], str | None]:
        statement = select(AuditChainEntry)
        predicates = []
        if actor_id is not None:
            actor_value = str(actor_id)
            predicates.append(
                AuditChainEntry.canonical_payload["actor_id"].as_string() == actor_value
            )
            predicates.append(
                AuditChainEntry.canonical_payload["requested_by"].as_string() == actor_value
            )
        if subject_id is not None:
            subject_value = str(subject_id)
            predicates.append(
                AuditChainEntry.canonical_payload["subject_id"].as_string() == subject_value
            )
            predicates.append(
                AuditChainEntry.canonical_payload["user_id"].as_string() == subject_value
            )
            predicates.append(
                AuditChainEntry.canonical_payload["subject_user_id"].as_string() == subject_value
            )
        if predicates:
            statement = statement.where(or_(*predicates))
        if start_ts is not None:
            statement = statement.where(AuditChainEntry.created_at >= start_ts)
        if end_ts is not None:
            statement = statement.where(AuditChainEntry.created_at <= end_ts)
        if event_type is not None:
            statement = statement.where(AuditChainEntry.event_type == event_type)

        cursor_created_at, cursor_id = _decode_cursor(cursor)
        if cursor_created_at is not None and cursor_id is not None:
            statement = statement.where(
                or_(
                    AuditChainEntry.created_at < cursor_created_at,
                    and_(
                        AuditChainEntry.created_at == cursor_created_at,
                        AuditChainEntry.id < cursor_id,
                    ),
                )
            )

        result = await self.session.execute(
            statement.order_by(AuditChainEntry.created_at.desc(), AuditChainEntry.id.desc()).limit(
                limit + 1
            )
        )
        entries = list(result.scalars().all())
        next_cursor = None
        if len(entries) > limit:
            entries = entries[:limit]
            next_cursor = _encode_cursor(entries[-1])
        return entries, next_cursor

    async def get_by_sequence(self, sequence_number: int) -> AuditChainEntry | None:
        result = await self.session.execute(
            select(AuditChainEntry).where(AuditChainEntry.sequence_number == sequence_number)
        )
        return result.scalar_one_or_none()

    async def null_audit_event_reference(self, audit_event_id: UUID) -> int:
        result = await self.session.execute(
            update(AuditChainEntry)
            .where(AuditChainEntry.audit_event_id == audit_event_id)
            .values(audit_event_id=None)
        )
        await self.session.flush()
        rowcount = getattr(result, "rowcount", 0)
        return int(rowcount or 0)

    async def update(self, *_args: object, **_kwargs: object) -> None:
        raise NotImplementedError("audit_chain_entries is append-only")

    async def delete(self, *_args: object, **_kwargs: object) -> None:
        raise NotImplementedError("audit_chain_entries is append-only")


def _encode_cursor(entry: AuditChainEntry) -> str:
    payload = {"created_at": entry.created_at.isoformat(), "id": str(entry.id)}
    return base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")


def _decode_cursor(cursor: str | None) -> tuple[datetime | None, UUID | None]:
    if cursor is None:
        return None, None
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8"))
        if not isinstance(payload, dict):
            return None, None
        return datetime.fromisoformat(str(payload["created_at"])), UUID(str(payload["id"]))
    except (KeyError, ValueError, TypeError, json.JSONDecodeError, binascii.Error):
        return None, None
