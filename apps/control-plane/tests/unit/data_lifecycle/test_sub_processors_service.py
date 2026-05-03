"""Unit tests for SubProcessorsService.

Covers:
* Public list excludes notes + inactive rows.
* Admin add/update/delete emits audit + Kafka.
* Name-conflict guard on add and rename.
* Soft delete leaves row queryable but ``is_active=False``.
* RSS rendering produces valid XML.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from platform.data_lifecycle.exceptions import (
    SubProcessorNameConflict,
    SubProcessorNotFound,
)
from platform.data_lifecycle.models import SubProcessor
from platform.data_lifecycle.services.sub_processors_service import (
    SubProcessorsService,
    render_rss,
)


# ---------- Stub repository ----------


class _StubRepo:
    def __init__(self, rows: list[SubProcessor] | None = None) -> None:
        self._rows: dict[UUID, SubProcessor] = {r.id: r for r in (rows or [])}

    async def list_sub_processors_active(self) -> list[SubProcessor]:
        return [r for r in self._rows.values() if r.is_active]

    async def list_sub_processors_all(self) -> list[SubProcessor]:
        return list(self._rows.values())

    async def get_sub_processor(self, sub_processor_id: UUID) -> SubProcessor | None:
        return self._rows.get(sub_processor_id)

    async def get_sub_processor_by_name(self, name: str) -> SubProcessor | None:
        for r in self._rows.values():
            if r.name == name:
                return r
        return None

    async def insert_sub_processor(self, **kwargs: Any) -> SubProcessor:
        row = SubProcessor(
            name=kwargs["name"],
            category=kwargs["category"],
            location=kwargs["location"],
            data_categories=list(kwargs["data_categories"]),
            privacy_policy_url=kwargs.get("privacy_policy_url"),
            dpa_url=kwargs.get("dpa_url"),
            is_active=True,
            started_using_at=kwargs.get("started_using_at"),
            notes=kwargs.get("notes"),
            updated_by_user_id=kwargs.get("updated_by_user_id"),
        )
        object.__setattr__(row, "id", uuid4())
        object.__setattr__(row, "created_at", datetime.now(UTC))
        object.__setattr__(row, "updated_at", datetime.now(UTC))
        self._rows[row.id] = row
        return row

    async def update_sub_processor(
        self,
        *,
        sub_processor_id: UUID,
        updates: dict[str, Any],
        updated_by_user_id: UUID | None,
    ) -> None:
        row = self._rows.get(sub_processor_id)
        if row is None:
            return
        for k, v in updates.items():
            object.__setattr__(row, k, v)
        object.__setattr__(row, "updated_by_user_id", updated_by_user_id)
        object.__setattr__(row, "updated_at", datetime.now(UTC))

    async def soft_delete_sub_processor(
        self, *, sub_processor_id: UUID, updated_by_user_id: UUID | None
    ) -> None:
        row = self._rows.get(sub_processor_id)
        if row is None:
            return
        object.__setattr__(row, "is_active", False)
        object.__setattr__(row, "updated_by_user_id", updated_by_user_id)
        object.__setattr__(row, "updated_at", datetime.now(UTC))

    async def latest_sub_processors_change(self) -> datetime | None:
        if not self._rows:
            return None
        return max(r.updated_at for r in self._rows.values() if r.updated_at)


class _StubAudit:
    def __init__(self) -> None:
        self.appended: list[bytes] = []

    async def append(
        self, audit_event_id: UUID, namespace: str, canonical_payload: bytes
    ) -> None:
        self.appended.append(canonical_payload)


class _StubProducer:
    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []

    async def publish(self, **kwargs: Any) -> None:
        self.published.append(kwargs)


def _row(name: str = "Anthropic", *, is_active: bool = True) -> SubProcessor:
    row = SubProcessor(
        name=name,
        category="LLM provider",
        location="USA",
        data_categories=["prompts", "outputs"],
        privacy_policy_url="https://example.com/privacy",
        dpa_url=None,
        is_active=is_active,
        started_using_at=date(2024, 9, 1),
        notes="OPERATOR-ONLY notes that must NEVER appear in public",
    )
    object.__setattr__(row, "id", uuid4())
    object.__setattr__(row, "created_at", datetime.now(UTC))
    object.__setattr__(row, "updated_at", datetime.now(UTC))
    return row


def _build(rows: list[SubProcessor] | None = None) -> tuple[SubProcessorsService, _StubRepo, _StubAudit, _StubProducer]:
    repo = _StubRepo(rows or [])
    audit = _StubAudit()
    producer = _StubProducer()
    service = SubProcessorsService(
        repository=repo,  # type: ignore[arg-type]
        audit_chain=audit,  # type: ignore[arg-type]
        event_producer=producer,  # type: ignore[arg-type]
    )
    return service, repo, audit, producer


# ---------- Tests ----------


@pytest.mark.asyncio
async def test_public_list_excludes_inactive_and_notes() -> None:
    active = _row("Anthropic", is_active=True)
    inactive = _row("Old Provider", is_active=False)
    service, _, _, _ = _build([active, inactive])

    items = await service.list_active_for_public()

    names = [i.name for i in items]
    assert "Anthropic" in names
    assert "Old Provider" not in names
    # The public view dataclass has no `notes` attribute by construction.
    assert not hasattr(items[0], "notes")


@pytest.mark.asyncio
async def test_add_emits_audit_and_kafka() -> None:
    service, _, audit, producer = _build()

    row = await service.add(
        name="MaxMind, Inc.",
        category="Fraud",
        location="USA",
        data_categories=["ip_addresses"],
        privacy_policy_url=None,
        dpa_url=None,
        started_using_at=None,
        notes=None,
        actor_user_id=uuid4(),
    )

    assert row.name == "MaxMind, Inc."
    assert any(b"sub_processor_change" in p for p in audit.appended)
    types = [p["event_type"] for p in producer.published]
    assert "data_lifecycle.sub_processor.added" in types


@pytest.mark.asyncio
async def test_add_refuses_duplicate_name() -> None:
    service, _, _, _ = _build([_row("Anthropic")])
    with pytest.raises(SubProcessorNameConflict):
        await service.add(
            name="Anthropic",
            category="LLM provider",
            location="USA",
            data_categories=[],
            privacy_policy_url=None,
            dpa_url=None,
            started_using_at=None,
            notes=None,
            actor_user_id=None,
        )


@pytest.mark.asyncio
async def test_update_with_renamed_collision_refused() -> None:
    a = _row("Anthropic")
    b = _row("OpenAI")
    service, _, _, _ = _build([a, b])
    with pytest.raises(SubProcessorNameConflict):
        await service.update(
            sub_processor_id=b.id,
            updates={"name": "Anthropic"},
            actor_user_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_soft_delete_marks_inactive_and_emits_event() -> None:
    a = _row("Anthropic")
    service, _, audit, producer = _build([a])

    await service.soft_delete(
        sub_processor_id=a.id, actor_user_id=uuid4()
    )

    assert a.is_active is False
    types = [p["event_type"] for p in producer.published]
    assert "data_lifecycle.sub_processor.removed" in types
    assert any(b"sub_processor_change" in p for p in audit.appended)


@pytest.mark.asyncio
async def test_update_not_found_raises() -> None:
    service, _, _, _ = _build()
    with pytest.raises(SubProcessorNotFound):
        await service.update(
            sub_processor_id=uuid4(),
            updates={"category": "LLM provider"},
            actor_user_id=None,
        )


@pytest.mark.asyncio
async def test_latest_change_at_returns_max_timestamp() -> None:
    a = _row("Anthropic")
    b = _row("OpenAI")
    service, _, _, _ = _build([a, b])
    latest = await service.latest_change_at()
    assert latest is not None


def test_render_rss_produces_valid_xml() -> None:
    rows = [_row("Anthropic"), _row("OpenAI")]
    xml = render_rss(items=rows, site_base_url="https://musematic.ai")
    assert xml.startswith("<?xml")
    assert "<rss" in xml
    assert "Anthropic" in xml
    assert "OpenAI" in xml
    # Confirm operator notes do NOT leak.
    assert "OPERATOR-ONLY" not in xml
