"""Sub-processors service — admin CRUD + public read + RSS feed.

Reads/writes the platform-level ``sub_processors`` table. Public reads
(unauthenticated) go through :meth:`list_active_for_public` which never
exposes operator-only fields (``notes``).

Audit + Kafka emission on every mutation, per FR-757 + rule 17 (HMAC
webhook fanout via UPD-077, wired by the regenerator cron).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from platform.common.events.envelope import CorrelationContext
from platform.data_lifecycle.events import (
    DataLifecycleEventType,
    SubProcessorChangedPayload,
    publish_data_lifecycle_event,
)
from platform.data_lifecycle.exceptions import (
    SubProcessorNameConflict,
    SubProcessorNotFound,
)
from platform.data_lifecycle.models import SubProcessor
from platform.data_lifecycle.repository import DataLifecycleRepository

logger = logging.getLogger(__name__)


class _AuditAppender(Protocol):
    async def append(
        self, audit_event_id: UUID, namespace: str, canonical_payload: bytes
    ) -> Any:
        ...


class _EventProducer(Protocol):
    async def publish(self, **kwargs: Any) -> Any:
        ...


@dataclass(frozen=True, slots=True)
class _PublicView:
    """Subset of fields exposed by the public list endpoint."""

    name: str
    category: str
    location: str
    data_categories: list[str]
    privacy_policy_url: str | None
    dpa_url: str | None
    started_using_at: str | None  # ISO date

    @classmethod
    def from_row(cls, row: SubProcessor) -> "_PublicView":
        return cls(
            name=row.name,
            category=row.category,
            location=row.location,
            data_categories=list(row.data_categories or []),
            privacy_policy_url=row.privacy_policy_url,
            dpa_url=row.dpa_url,
            started_using_at=(
                row.started_using_at.isoformat()
                if row.started_using_at is not None
                else None
            ),
        )


class SubProcessorsService:
    def __init__(
        self,
        *,
        repository: DataLifecycleRepository,
        audit_chain: _AuditAppender | None,
        event_producer: _EventProducer | None,
    ) -> None:
        self._repo = repository
        self._audit = audit_chain
        self._producer = event_producer

    # =========================================================================
    # Public surface
    # =========================================================================

    async def list_active_for_public(self) -> list[_PublicView]:
        rows = await self._repo.list_sub_processors_active()
        return [_PublicView.from_row(r) for r in rows]

    async def latest_change_at(self) -> datetime | None:
        return await self._repo.latest_sub_processors_change()

    # =========================================================================
    # Admin surface
    # =========================================================================

    async def list_all(self) -> list[SubProcessor]:
        return await self._repo.list_sub_processors_all()

    async def get(self, sub_processor_id: UUID) -> SubProcessor:
        row = await self._repo.get_sub_processor(sub_processor_id)
        if row is None:
            raise SubProcessorNotFound(
                f"sub-processor {sub_processor_id} not found"
            )
        return row

    async def add(
        self,
        *,
        name: str,
        category: str,
        location: str,
        data_categories: list[str],
        privacy_policy_url: str | None,
        dpa_url: str | None,
        started_using_at: datetime | None,
        notes: str | None,
        actor_user_id: UUID | None,
    ) -> SubProcessor:
        existing = await self._repo.get_sub_processor_by_name(name)
        if existing is not None:
            raise SubProcessorNameConflict(
                f"sub-processor with name {name!r} already exists"
            )
        row = await self._repo.insert_sub_processor(
            name=name,
            category=category,
            location=location,
            data_categories=data_categories,
            privacy_policy_url=privacy_policy_url,
            dpa_url=dpa_url,
            started_using_at=started_using_at,
            notes=notes,
            updated_by_user_id=actor_user_id,
        )
        await self._on_change(
            row=row,
            event_type=DataLifecycleEventType.sub_processor_added,
            audit_subtype="added",
            actor_user_id=actor_user_id,
        )
        return row

    async def update(
        self,
        *,
        sub_processor_id: UUID,
        updates: dict[str, Any],
        actor_user_id: UUID | None,
    ) -> SubProcessor:
        existing = await self._repo.get_sub_processor(sub_processor_id)
        if existing is None:
            raise SubProcessorNotFound(
                f"sub-processor {sub_processor_id} not found"
            )
        # If name is changing, ensure no collision.
        if "name" in updates and updates["name"] != existing.name:
            collision = await self._repo.get_sub_processor_by_name(updates["name"])
            if collision is not None and collision.id != sub_processor_id:
                raise SubProcessorNameConflict(
                    f"sub-processor with name {updates['name']!r} already exists"
                )
        await self._repo.update_sub_processor(
            sub_processor_id=sub_processor_id,
            updates=updates,
            updated_by_user_id=actor_user_id,
        )
        # Re-read for the event payload + return.
        updated = await self._repo.get_sub_processor(sub_processor_id)
        assert updated is not None  # we just confirmed it existed
        await self._on_change(
            row=updated,
            event_type=DataLifecycleEventType.sub_processor_modified,
            audit_subtype="modified",
            actor_user_id=actor_user_id,
        )
        return updated

    async def soft_delete(
        self, *, sub_processor_id: UUID, actor_user_id: UUID | None
    ) -> SubProcessor:
        existing = await self._repo.get_sub_processor(sub_processor_id)
        if existing is None:
            raise SubProcessorNotFound(
                f"sub-processor {sub_processor_id} not found"
            )
        await self._repo.soft_delete_sub_processor(
            sub_processor_id=sub_processor_id,
            updated_by_user_id=actor_user_id,
        )
        # Refresh.
        updated = await self._repo.get_sub_processor(sub_processor_id)
        assert updated is not None
        await self._on_change(
            row=updated,
            event_type=DataLifecycleEventType.sub_processor_removed,
            audit_subtype="removed",
            actor_user_id=actor_user_id,
        )
        return updated

    # =========================================================================
    # Audit + Kafka emission
    # =========================================================================

    async def _on_change(
        self,
        *,
        row: SubProcessor,
        event_type: DataLifecycleEventType,
        audit_subtype: str,
        actor_user_id: UUID | None,
    ) -> None:
        now = datetime.now(UTC)
        await self._emit_audit(
            event_type="data_lifecycle.sub_processor_change",
            payload={
                "sub_processor_id": str(row.id),
                "name": row.name,
                "category": row.category,
                "is_active": bool(row.is_active),
                "subtype": audit_subtype,
                "actor_user_id": str(actor_user_id) if actor_user_id else None,
                "changed_at": now.isoformat(),
            },
        )
        await publish_data_lifecycle_event(
            self._producer,
            event_type,
            SubProcessorChangedPayload(
                sub_processor_id=row.id,
                name=row.name,
                category=row.category,
                is_active=bool(row.is_active),
                changed_at=now,
                correlation_context=CorrelationContext(correlation_id=uuid4()),
            ),
            CorrelationContext(correlation_id=uuid4()),
            partition_key=row.id,
        )

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


def render_rss(
    *,
    items: list[SubProcessor],
    site_base_url: str,
    last_build: datetime | None = None,
) -> str:
    """Render an RSS 2.0 feed of recent sub-processor changes.

    Per the contract, the feed lists added/modified/removed entries
    chronologically. We use ``feedgen`` for valid XML emission.
    """

    from feedgen.feed import FeedGenerator

    fg = FeedGenerator()
    fg.title("Musematic Sub-Processors Changes")
    fg.link(href=f"{site_base_url}/legal/sub-processors", rel="alternate")
    fg.description(
        "Changes to the list of third-party data processors used by Musematic."
    )
    fg.language("en")
    if last_build is not None:
        fg.lastBuildDate(last_build)
    for row in items:
        fe = fg.add_entry()
        fe.title(f"{'Active' if row.is_active else 'Removed'}: {row.name}")
        fe.guid(f"sub_processor:{row.id}", permalink=False)
        fe.pubDate(row.updated_at)
        fe.description(
            f"{row.name} - {row.category} - {row.location}; "
            f"data categories: {', '.join(row.data_categories or [])}."
        )
    return fg.rss_str(pretty=True).decode("utf-8")
