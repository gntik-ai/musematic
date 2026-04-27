from __future__ import annotations

from platform.audit.service import AuditChainService
from platform.common.config import PlatformSettings
from typing import Any
from uuid import uuid4

import pytest
from tests.unit.audit.test_audit_chain_service import InMemoryAuditChainRepository


class RecordingLogger:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def info(self, event: str, **fields: Any) -> None:
        self.events.append((event, fields))


class FailingLogger:
    def info(self, event: str, **fields: Any) -> None:
        raise OSError("stdout closed")


async def _append_with_rollback(
    service: AuditChainService,
    repository: InMemoryAuditChainRepository,
) -> None:
    try:
        await service.append(uuid4(), "unit-test", b'{"action":"created"}')
    except OSError:
        repository.entries.clear()
        raise


def _settings() -> PlatformSettings:
    return PlatformSettings(audit={"signing_key_hex": "7" * 64})


@pytest.mark.asyncio
async def test_append_emits_transactional_structured_log(monkeypatch: pytest.MonkeyPatch) -> None:
    logger = RecordingLogger()
    monkeypatch.setattr("platform.audit.service.get_logger", lambda _name: logger)
    repository = InMemoryAuditChainRepository()
    service = AuditChainService(repository=repository, settings=_settings())

    entry = await service.append(uuid4(), "unit-test", b'{"action":"created"}')

    assert repository.entries == [entry]
    assert logger.events == [
        (
            "audit.chain.appended",
            {
                "sequence_number": 1,
                "audit_event_source": "unit-test",
                "canonical_payload_hash": entry.canonical_payload_hash,
                "entry_hash": entry.entry_hash,
            },
        )
    ]


@pytest.mark.asyncio
async def test_append_log_failure_propagates_for_session_rollback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("platform.audit.service.get_logger", lambda _name: FailingLogger())
    repository = InMemoryAuditChainRepository()
    service = AuditChainService(repository=repository, settings=_settings())

    with pytest.raises(OSError, match="stdout closed"):
        await _append_with_rollback(service, repository)

    assert repository.entries == []
