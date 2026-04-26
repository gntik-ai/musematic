from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.events.consumer import EventConsumerManager
from platform.trust.events import (
    CertificationEventPayload,
    TrustEventPublisher,
    make_correlation,
    utcnow,
)
from platform.trust.models import (
    CertificationStatus,
    ReassessmentRecord,
    TrustCertification,
    TrustRecertificationRequest,
)
from platform.trust.repository import TrustRepository
from typing import Any

from sqlalchemy import or_, select


class SurveillanceService:
    def __init__(
        self,
        *,
        repository: TrustRepository,
        publisher: TrustEventPublisher,
        settings: Any,
    ) -> None:
        self.repository = repository
        self.events = publisher
        self.settings = settings

    def register(self, manager: EventConsumerManager) -> None:
        group = getattr(self.settings.kafka, "consumer_group", "platform")
        manager.subscribe(
            "policy.events",
            f"{group}.trust-surveillance-material-change",
            self.handle_material_change,
        )
        manager.subscribe(
            "trust.events",
            f"{group}.trust-surveillance-revision-signals",
            self.handle_material_change,
        )

    async def run_surveillance_cycle(self) -> None:
        now = datetime.now(UTC)
        warning_window_days = int(
            getattr(
                getattr(self.settings, "trust", self.settings),
                "surveillance_warning_window_days",
                7,
            )
        )
        warning_deadline = now + timedelta(days=warning_window_days)
        certifications = await self._list_surveillance_candidates()

        for certification in certifications:
            if certification.expires_at is not None and certification.expires_at <= now:
                certification.status = CertificationStatus.expired
                certification.updated_at = now
                await self.events.publish_certification_expired(
                    self._event_payload(certification),
                    make_correlation(),
                )
                await self._publish_alert(
                    "trust.certification.expired",
                    certification,
                    {"expires_at": certification.expires_at.isoformat()},
                )
                continue

            if (
                certification.status == CertificationStatus.active
                and certification.expires_at is not None
                and certification.expires_at <= warning_deadline
            ):
                certification.status = CertificationStatus.expiring
                certification.updated_at = now
                await self.events.publish_certification_expiring(
                    self._event_payload(certification),
                    make_correlation(),
                )
                await self._publish_alert(
                    "trust.certification.expiring",
                    certification,
                    {"expires_at": certification.expires_at.isoformat()},
                )

            schedule = certification.reassessment_schedule
            if schedule is None:
                continue
            latest = await self.repository.list_reassessments(certification.id)
            last_run_at = latest[0].created_at if latest else None
            if not self._is_reassessment_due(schedule, last_run_at, now):
                continue
            await self.repository.create_reassessment(
                certification.id,
                ReassessmentRecord(
                    certification_id=certification.id,
                    verdict="action_required",
                    reassessor_id="automated",
                    notes="Scheduled surveillance reassessment required",
                ),
            )
            await self._publish_alert(
                "trust.reassessment.required",
                certification,
                {"schedule": schedule},
            )
        await self.repository.session.flush()

    async def _list_surveillance_candidates(self) -> list[TrustCertification]:
        session = self.repository.session
        if hasattr(session, "execute"):
            result = await session.execute(
                select(TrustCertification).where(
                    TrustCertification.status.in_(
                        (CertificationStatus.active, CertificationStatus.expiring)
                    ),
                    or_(
                        TrustCertification.expires_at.is_not(None),
                        TrustCertification.reassessment_schedule.is_not(None),
                    ),
                )
            )
            return list(result.scalars().all())
        certifications = getattr(self.repository, "certifications", [])
        return [
            item
            for item in certifications
            if item.status in {CertificationStatus.active, CertificationStatus.expiring}
            and (item.expires_at is not None or item.reassessment_schedule is not None)
        ]

    async def handle_material_change(self, envelope: Any) -> None:
        payload = getattr(envelope, "payload", envelope)
        event_type = str(payload.get("event_type") or getattr(envelope, "event_type", ""))
        agent_id = payload.get("agent_id") or payload.get("agent_fqn")
        if not isinstance(agent_id, str) or not agent_id:
            return

        now = datetime.now(UTC)
        grace_period_days = int(
            getattr(
                getattr(self.settings, "trust", self.settings),
                "recertification_grace_period_days",
                14,
            )
        )
        deadline = now + timedelta(days=grace_period_days)
        certifications = await self.repository.get_active_or_expiring_certifications_for_agent(
            agent_id
        )
        for certification in certifications:
            certification.status = CertificationStatus.suspended
            certification.updated_at = now
            request = await self.repository.create_recertification_request(
                TrustRecertificationRequest(
                    certification_id=certification.id,
                    trigger_type="policy" if event_type.startswith("policy.") else "signal",
                    trigger_reference=str(
                        payload.get("event_id")
                        or payload.get("source_id")
                        or payload.get("agent_revision_id")
                        or event_type
                    ),
                    deadline=deadline,
                    resolution_status="pending",
                )
            )
            await self.events.publish_certification_suspended(
                self._event_payload(certification, reason=event_type or "material_change"),
                make_correlation(),
            )
            await self._publish_alert(
                "trust.certification.suspended",
                certification,
                {"trigger_type": request.trigger_type, "deadline": deadline.isoformat()},
            )
        await self.repository.session.flush()

    async def check_grace_period_expiry(self) -> None:
        now = datetime.now(UTC)
        pending = await self.repository.get_pending_requests_past_deadline(now)
        for request in pending:
            certification = await self.repository.get_certification(request.certification_id)
            if certification is None:
                continue
            certification.status = CertificationStatus.revoked
            certification.revoked_at = now
            certification.revocation_reason = "recertification timeout"
            await self.repository.resolve_recertification_request(request.id, "revoked")
            await self.events.publish_certification_revoked(
                self._event_payload(certification, reason="recertification timeout"),
                make_correlation(),
            )
            await self._publish_alert(
                "trust.certification.revoked",
                certification,
                {"reason": "recertification timeout"},
            )
        await self.repository.session.flush()

    async def _publish_alert(
        self,
        event_type: str,
        certification: TrustCertification,
        detail: dict[str, Any],
    ) -> None:
        producer = getattr(self.events, "producer", None)
        if producer is None:
            return
        await producer.publish(
            topic="monitor.alerts",
            key=str(certification.id),
            event_type=event_type,
            payload={
                "certification_id": str(certification.id),
                "agent_id": certification.agent_id,
                "agent_fqn": certification.agent_fqn,
                **detail,
            },
            correlation_ctx=make_correlation(),
            source="platform.trust",
        )

    @staticmethod
    def _is_reassessment_due(
        schedule: str,
        last_run_at: datetime | None,
        now: datetime,
    ) -> bool:
        if schedule == "@always":
            return True
        if schedule == "@daily":
            return last_run_at is None or last_run_at <= now - timedelta(days=1)
        if schedule == "@weekly":
            return last_run_at is None or last_run_at <= now - timedelta(days=7)
        if schedule == "@monthly":
            return last_run_at is None or last_run_at <= now - timedelta(days=30)
        return last_run_at is None

    @staticmethod
    def _event_payload(
        certification: TrustCertification,
        *,
        reason: str | None = None,
    ) -> CertificationEventPayload:
        return CertificationEventPayload(
            certification_id=certification.id,
            agent_id=certification.agent_id,
            agent_fqn=certification.agent_fqn,
            agent_revision_id=certification.agent_revision_id,
            occurred_at=utcnow(),
            reason=reason,
        )
