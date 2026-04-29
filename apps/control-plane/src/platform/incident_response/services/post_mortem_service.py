from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from platform.common.clients.object_storage import AsyncObjectStorageClient
from platform.common.config import PlatformSettings
from platform.common.logging import get_logger
from platform.incident_response.exceptions import (
    IncidentNotFoundError,
    PostMortemNotFoundError,
    PostMortemOnOpenIncidentError,
)
from platform.incident_response.models import PostMortem
from platform.incident_response.repository import IncidentResponseRepository
from platform.incident_response.schemas import (
    PostMortemResponse,
    TimelineEntry,
    TimelineSourceCoverage,
)
from platform.incident_response.services.timeline_assembler import TimelineAssembler
from typing import Any
from uuid import UUID, uuid4

LOGGER = get_logger(__name__)


class PostMortemService:
    def __init__(
        self,
        *,
        repository: IncidentResponseRepository,
        settings: PlatformSettings,
        timeline_assembler: TimelineAssembler,
        object_storage: AsyncObjectStorageClient | None = None,
        alert_service: Any | None = None,
        audit_chain_service: Any | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.timeline_assembler = timeline_assembler
        self.object_storage = object_storage
        self.alert_service = alert_service
        self.audit_chain_service = audit_chain_service

    async def start(self, incident_id: UUID, by_user_id: UUID | None) -> PostMortemResponse:
        existing = await self.repository.get_post_mortem_by_incident(incident_id)
        if existing is not None:
            return await self._response(existing)
        incident = await self.repository.get_incident(incident_id)
        if incident is None:
            raise IncidentNotFoundError(incident_id)
        if incident.status not in {"resolved", "auto_resolved"}:
            raise PostMortemOnOpenIncidentError(incident.id, incident.status)
        resolved_at = incident.resolved_at or datetime.now(UTC)
        entries, coverage = await self.timeline_assembler.assemble(
            incident_id=incident.id,
            window_start=incident.triggered_at - timedelta(minutes=5),
            window_end=resolved_at + timedelta(minutes=5),
        )
        post_mortem_id = uuid4()
        timeline_payload = [entry.model_dump(mode="json") for entry in entries]
        inline_timeline, blob_ref = await self._maybe_spill_timeline(
            post_mortem_id,
            timeline_payload,
        )
        post_mortem = await self.repository.insert_post_mortem(
            post_mortem_id=post_mortem_id,
            incident_id=incident.id,
            timeline=inline_timeline,
            timeline_blob_ref=blob_ref,
            timeline_source_coverage=coverage.model_dump(mode="json"),
            created_by=by_user_id,
        )
        await self.repository.update_incident_post_mortem(incident.id, post_mortem.id)
        await self._audit(
            "post_mortem.created",
            post_mortem,
            extra={"incident_id": str(incident.id)},
        )
        return await self._response(post_mortem)

    async def get(self, post_mortem_id: UUID) -> PostMortemResponse:
        post_mortem = await self.repository.get_post_mortem(post_mortem_id)
        if post_mortem is None:
            raise PostMortemNotFoundError(post_mortem_id)
        return await self._response(post_mortem)

    async def get_by_incident(self, incident_id: UUID) -> PostMortemResponse:
        post_mortem = await self.repository.get_post_mortem_by_incident(incident_id)
        if post_mortem is None:
            raise PostMortemNotFoundError(str(incident_id))
        return await self._response(post_mortem)

    async def save_section(
        self,
        post_mortem_id: UUID,
        *,
        impact_assessment: str | None = None,
        root_cause: str | None = None,
        action_items: list[dict[str, Any]] | None = None,
    ) -> PostMortemResponse:
        post_mortem = await self.repository.update_post_mortem_section(
            post_mortem_id,
            impact_assessment=impact_assessment,
            root_cause=root_cause,
            action_items=action_items,
        )
        if post_mortem is None:
            raise PostMortemNotFoundError(post_mortem_id)
        await self._audit("post_mortem.section_saved", post_mortem)
        return await self._response(post_mortem)

    async def link_execution(self, post_mortem_id: UUID, execution_id: UUID) -> PostMortemResponse:
        post_mortem = await self.repository.get_post_mortem(post_mortem_id)
        if post_mortem is None:
            raise PostMortemNotFoundError(post_mortem_id)
        await self.repository.append_incident_execution(post_mortem.incident_id, execution_id)
        await self._audit(
            "post_mortem.execution_linked",
            post_mortem,
            extra={"execution_id": str(execution_id)},
        )
        return await self._response(post_mortem)

    async def link_certification(
        self,
        post_mortem_id: UUID,
        certification_id: UUID,
    ) -> PostMortemResponse:
        post_mortem = await self.repository.append_linked_certification(
            post_mortem_id,
            certification_id,
        )
        if post_mortem is None:
            raise PostMortemNotFoundError(post_mortem_id)
        await self._audit(
            "post_mortem.certification_linked",
            post_mortem,
            extra={"certification_id": str(certification_id)},
        )
        return await self._response(post_mortem)

    async def mark_blameless(self, post_mortem_id: UUID) -> PostMortemResponse:
        post_mortem = await self.repository.update_post_mortem_section(
            post_mortem_id,
            blameless=True,
        )
        if post_mortem is None:
            raise PostMortemNotFoundError(post_mortem_id)
        await self._audit("post_mortem.marked_blameless", post_mortem)
        return await self._response(post_mortem)

    async def publish(self, post_mortem_id: UUID) -> PostMortemResponse:
        post_mortem = await self.repository.mark_published(post_mortem_id, datetime.now(UTC))
        if post_mortem is None:
            raise PostMortemNotFoundError(post_mortem_id)
        await self._audit("post_mortem.published", post_mortem)
        return await self._response(post_mortem)

    async def distribute(
        self,
        post_mortem_id: UUID,
        recipients: list[str],
    ) -> PostMortemResponse:
        post_mortem = await self.repository.get_post_mortem(post_mortem_id)
        if post_mortem is None:
            raise PostMortemNotFoundError(post_mortem_id)
        outcomes: list[dict[str, Any]] = []
        for recipient in recipients:
            try:
                await self._notify_recipient(post_mortem, recipient)
            except Exception as exc:
                outcomes.append({"recipient": recipient, "outcome": f"failed:{exc}"})
            else:
                outcomes.append({"recipient": recipient, "outcome": "delivered"})
        updated = await self.repository.mark_distributed(
            post_mortem_id,
            outcomes,
            datetime.now(UTC),
        )
        if updated is None:
            raise PostMortemNotFoundError(post_mortem_id)
        await self._audit(
            "post_mortem.distributed",
            updated,
            extra={
                "recipient_count": len(outcomes),
                "failed_count": sum(
                    1 for item in outcomes if str(item["outcome"]).startswith("failed")
                ),
            },
        )
        return await self._response(updated)

    async def find_for_execution(self, execution_id: UUID) -> list[PostMortemResponse]:
        rows = await self.repository.list_post_mortems_by_execution(execution_id)
        return [await self._response(row) for row in rows]

    async def find_for_certification(self, certification_id: UUID) -> list[PostMortemResponse]:
        rows = await self.repository.list_post_mortems_by_certification(certification_id)
        return [await self._response(row) for row in rows]

    async def _maybe_spill_timeline(
        self,
        post_mortem_id: UUID,
        timeline_payload: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]] | None, str | None]:
        serialized = json.dumps(timeline_payload, sort_keys=True, separators=(",", ":")).encode()
        if len(serialized) <= self.settings.incident_response.postmortem_blob_threshold_bytes:
            return timeline_payload, None
        if self.object_storage is None:
            return timeline_payload, None
        key = f"{post_mortem_id}/timeline.json"
        bucket = self.settings.incident_response.postmortem_minio_bucket
        try:
            await self.object_storage.create_bucket_if_not_exists(bucket)
            await self.object_storage.put_object(
                bucket,
                key,
                serialized,
                content_type="application/json",
            )
        except Exception:
            LOGGER.warning("post_mortem_timeline_blob_spill_failed", exc_info=True)
            return timeline_payload, None
        return None, key

    async def _load_timeline(self, post_mortem: PostMortem) -> list[TimelineEntry] | None:
        raw = post_mortem.timeline
        if raw is None and post_mortem.timeline_blob_ref and self.object_storage is not None:
            payload = await self.object_storage.get_object(
                self.settings.incident_response.postmortem_minio_bucket,
                post_mortem.timeline_blob_ref,
            )
            parsed = json.loads(payload.decode())
            raw = parsed if isinstance(parsed, list) else []
        if raw is None:
            return None
        return [TimelineEntry.model_validate(item) for item in raw]

    async def _response(self, post_mortem: PostMortem) -> PostMortemResponse:
        return PostMortemResponse.model_validate(
            {
                "id": post_mortem.id,
                "incident_id": post_mortem.incident_id,
                "status": post_mortem.status,
                "timeline": await self._load_timeline(post_mortem),
                "timeline_blob_ref": post_mortem.timeline_blob_ref,
                "timeline_source_coverage": TimelineSourceCoverage.model_validate(
                    post_mortem.timeline_source_coverage
                ),
                "impact_assessment": post_mortem.impact_assessment,
                "root_cause": post_mortem.root_cause,
                "action_items": post_mortem.action_items,
                "distribution_list": post_mortem.distribution_list,
                "linked_certification_ids": post_mortem.linked_certification_ids,
                "blameless": post_mortem.blameless,
                "created_at": post_mortem.created_at,
                "created_by": post_mortem.created_by,
                "published_at": post_mortem.published_at,
                "distributed_at": post_mortem.distributed_at,
            }
        )

    async def _notify_recipient(self, post_mortem: PostMortem, recipient: str) -> None:
        del post_mortem
        if self.alert_service is None:
            return
        sender = getattr(self.alert_service, "send_post_mortem", None)
        if callable(sender):
            result = sender(recipient=recipient)
            if hasattr(result, "__await__"):
                await result

    async def _audit(
        self,
        action: str,
        post_mortem: PostMortem,
        *,
        extra: dict[str, Any] | None = None,
    ) -> None:
        append = getattr(self.audit_chain_service, "append", None)
        if append is None:
            return
        payload = {
            "action": action,
            "post_mortem_id": str(post_mortem.id),
            "incident_id": str(post_mortem.incident_id),
            **(extra or {}),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        await append(uuid4(), "incident_response.post_mortems", canonical)
