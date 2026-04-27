from __future__ import annotations

import json
from asyncio import gather
from datetime import UTC, datetime
from hashlib import sha256
from platform.audit import dependencies as audit_dependencies
from platform.audit.exceptions import AuditChainIntegrityError
from platform.audit.models import AuditChainEntry
from platform.audit.service import GENESIS_HASH, AuditChainService, compute_entry_hash
from platform.audit.signing import AuditChainSigning
from platform.common.config import PlatformSettings
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


class InMemoryAuditChainRepository:
    def __init__(self) -> None:
        self.entries: list[AuditChainEntry] = []

    async def acquire_append_lock(self) -> None:
        return None

    async def get_latest_entry(self) -> AuditChainEntry | None:
        return self.entries[-1] if self.entries else None

    async def next_sequence_number(self) -> int:
        return len(self.entries) + 1

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
            id=uuid4(),
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
            created_at=datetime.now(UTC),
        )
        self.entries.append(entry)
        return entry

    async def get_by_sequence_range(
        self,
        start_seq: int,
        end_seq: int,
    ) -> list[AuditChainEntry]:
        return [entry for entry in self.entries if start_seq <= entry.sequence_number <= end_seq]

    async def get_by_sequence(self, sequence_number: int) -> AuditChainEntry | None:
        return next(
            (entry for entry in self.entries if entry.sequence_number == sequence_number),
            None,
        )

    async def list_audit_sources_in_window(
        self,
        start_ts: datetime,
        end_ts: datetime,
        sources: list[str] | None = None,
    ) -> list[AuditChainEntry]:
        return [
            entry
            for entry in self.entries
            if start_ts <= entry.created_at <= end_ts
            and (sources is None or entry.audit_event_source in sources)
        ]

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
        del actor_id, subject_id, start_ts, end_ts, event_type, cursor
        return self.entries[:limit], None


class RecordingProducer:
    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []

    async def publish(self, **kwargs: Any) -> None:
        self.published.append(kwargs)


def _settings(seed: str = "1" * 64) -> PlatformSettings:
    return PlatformSettings(audit={"signing_key_hex": seed})


@pytest.mark.asyncio
async def test_audit_chain_dependency_factory_uses_request_state() -> None:
    settings = _settings()
    producer = object()
    session = object()
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=settings, clients={"kafka": producer}))
    )

    service = await audit_dependencies.get_audit_chain_service(
        request,  # type: ignore[arg-type]
        session,  # type: ignore[arg-type]
    )

    assert isinstance(service, AuditChainService)
    assert service.settings is settings
    assert service.producer is producer


@pytest.mark.asyncio
async def test_audit_chain_single_entry_matches_hash_formula() -> None:
    settings = _settings()
    repository = InMemoryAuditChainRepository()
    service = AuditChainService(repository=repository, settings=settings)
    payload = b'{"action":"created"}'

    entry = await service.append(uuid4(), "unit-test", payload)

    assert entry.entry_hash == compute_entry_hash(
        previous_hash=GENESIS_HASH,
        sequence_number=1,
        canonical_payload_hash=sha256(payload).hexdigest(),
    )


@pytest.mark.asyncio
async def test_audit_chain_appends_three_entries_verifies_and_attests() -> None:
    settings = _settings()
    repository = InMemoryAuditChainRepository()
    producer = RecordingProducer()
    service = AuditChainService(  # type: ignore[arg-type]
        repository=repository,
        settings=settings,
        producer=producer,
    )

    first = await service.append(uuid4(), "unit-test", b'{"action":"created"}')
    second = await service.append(uuid4(), "unit-test", b'{"action":"updated"}')
    third = await service.append(uuid4(), "unit-test", b'{"action":"published"}')

    assert first.sequence_number == 1
    assert second.sequence_number == 2
    assert third.sequence_number == 3
    assert second.previous_hash == first.entry_hash
    assert third.previous_hash == second.entry_hash

    verification = await service.verify()
    assert verification.valid is True
    assert verification.entries_checked == 3
    assert producer.published[0]["event_type"] == "security.audit.chain.verified"
    assert producer.published[0]["payload"]["valid"] is True

    attestation = await service.export_attestation(1, 3)
    assert attestation.start_entry_hash == first.entry_hash
    assert attestation.end_entry_hash == third.entry_hash
    assert len(attestation.signature) == 128
    public_key_hex = await service.get_public_verifying_key()
    assert len(public_key_hex) == 64

    document = attestation.model_dump()
    signature = bytes.fromhex(str(document.pop("signature")))
    document["window_start_time"] = document["window_start_time"].isoformat()
    document["window_end_time"] = document["window_end_time"].isoformat()
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex)).verify(
        signature,
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8"),
    )


@pytest.mark.asyncio
async def test_audit_chain_remains_valid_after_source_audit_rtbf() -> None:
    settings = _settings("4" * 64)
    repository = InMemoryAuditChainRepository()
    service = AuditChainService(repository=repository, settings=settings)

    await service.append(uuid4(), "unit-test", b'{"action":"deleted-user"}')
    repository.entries[0].audit_event_id = None

    verification = await service.verify()
    assert verification.valid is True


@pytest.mark.asyncio
async def test_audit_chain_concurrent_appends_have_unique_sequences() -> None:
    settings = _settings("5" * 64)
    repository = InMemoryAuditChainRepository()
    service = AuditChainService(repository=repository, settings=settings)

    await gather(
        *(
            service.append(uuid4(), "unit-test", f'{{"index":{index}}}'.encode())
            for index in range(1000)
        )
    )

    sequence_numbers = [entry.sequence_number for entry in repository.entries]
    assert sorted(sequence_numbers) == list(range(1, 1001))
    assert len({entry.entry_hash for entry in repository.entries}) == 1000
    assert (await service.verify()).valid is True


@pytest.mark.asyncio
async def test_audit_chain_detects_hash_tampering() -> None:
    settings = _settings("2" * 64)
    repository = InMemoryAuditChainRepository()
    service = AuditChainService(repository=repository, settings=settings)
    await service.append(uuid4(), "unit-test", b'{"action":"created"}')

    repository.entries[0].entry_hash = "f" * 64

    verification = await service.verify()
    assert verification.valid is False
    assert verification.broken_at == 1


@pytest.mark.asyncio
async def test_audit_chain_empty_wrappers_and_attestation_error_paths() -> None:
    settings = _settings("7" * 64)
    repository = InMemoryAuditChainRepository()
    service = AuditChainService(repository=repository, settings=settings)

    assert service._decode_payload(b"\xff") is None
    empty_verification = await service.verify()
    assert empty_verification.valid is True
    assert empty_verification.entries_checked == 0
    assert await service.list_audit_sources_in_window(datetime.now(UTC), datetime.now(UTC)) == []
    assert await service.list_entries_by_actor_or_subject(
        actor_id=None,
        subject_id=None,
        start_ts=None,
        end_ts=None,
        event_type=None,
        limit=10,
        cursor=None,
    ) == ([], None)
    with pytest.raises(AuditChainIntegrityError, match="empty audit chain"):
        await service.export_attestation(1, 1)

    first = await service.append(uuid4(), "unit-test", b'{"action":"created"}')
    second = await service.append(uuid4(), "other-source", b'{"action":"updated"}')
    assert (await service.verify(2, 2)).valid is True
    assert await service.list_audit_sources_in_window(
        first.created_at,
        second.created_at,
        ["unit-test"],
    ) == [first]
    assert await service.list_entries_by_actor_or_subject(
        actor_id=uuid4(),
        subject_id=None,
        start_ts=first.created_at,
        end_ts=second.created_at,
        event_type="auth.session.revoked",
        limit=1,
        cursor=None,
    ) == ([first], None)

    second.entry_hash = "f" * 64
    with pytest.raises(AuditChainIntegrityError, match="Audit chain broken"):
        await service.export_attestation(1, 2)


def test_audit_signing_does_not_log_private_seed(caplog: pytest.LogCaptureFixture) -> None:
    private_seed = "3" * 64

    with caplog.at_level("DEBUG"):
        signing = AuditChainSigning(_settings(private_seed).audit)

    assert len(signing.public_key_hex) == 64
    assert private_seed not in caplog.text


def test_audit_signing_validation_and_failed_verify() -> None:
    with pytest.raises(ValueError, match="32-byte hex-encoded"):
        AuditChainSigning(_settings("1" * 62).audit)

    signing = AuditChainSigning(_settings("6" * 64).audit)
    signature = signing.sign(b"document")

    assert signing.verify(b"document", signature, signing.public_key_hex) is True
    assert signing.verify(b"tampered", signature, signing.public_key_hex) is False
