"""Platform-staff marketplace-review service (UPD-049 FR-013 to FR-017).

Owns the cross-tenant review queue, the optimistic claim semantics
(research R6), the approve/reject transitions, and the audit + Kafka +
notification side effects.

Reads use the platform-staff session (BYPASSRLS) per UPD-046 — the queue
must show submissions across all default-tenant rows even though the RLS
policy on ``registry_agent_profiles`` would otherwise scope reads.
"""

from __future__ import annotations

from datetime import UTC, datetime
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.logging import get_logger
from platform.marketplace.metrics import (
    marketplace_review_age_seconds,
    marketplace_review_decisions_total,
)
from platform.registry.events import (
    MarketplaceApprovedPayload,
    MarketplaceEventType,
    MarketplacePublishedPayload,
    MarketplaceRejectedPayload,
    MarketplaceSourceUpdatedPayload,
    publish_marketplace_event,
)
from platform.registry.exceptions import (
    ReviewAlreadyClaimedError,
    SubmissionAlreadyResolvedError,
    SubmissionNotFoundError,
)
from platform.registry.schemas import ReviewQueueResponse, ReviewSubmissionView
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

LOGGER = get_logger(__name__)


class MarketplaceNotificationServiceProtocol(Protocol):
    """Decoupling shim for the rejection notifier (UPD-049 T037)."""

    async def notify_review_rejected(
        self,
        *,
        agent_id: UUID,
        submitter_user_id: UUID,
        rejection_reason: str,
    ) -> None: ...


class MarketplaceAdminService:
    """Cross-tenant review-queue + approve/reject service.

    The session passed in MUST be the platform-staff (BYPASSRLS) session
    for queue listings to span tenants. Per-row claim/approve/reject
    operations also use this session because the policy-checked tenant
    context isn't set on platform-staff requests.
    """

    def __init__(
        self,
        *,
        platform_staff_session: AsyncSession,
        event_producer: EventProducer | None,
        notifications: MarketplaceNotificationServiceProtocol | None,
    ) -> None:
        self._session = platform_staff_session
        self._event_producer = event_producer
        self._notifications = notifications

    async def list_queue(
        self,
        *,
        claimed_by: UUID | None = None,
        unclaimed_only: bool = False,
        limit: int = 50,
        cursor: str | None = None,
    ) -> ReviewQueueResponse:
        """List submissions in ``review_status='pending_review'``.

        Cursor format: opaque ISO-8601 ``submitted_at`` of the last item
        returned in the previous page. ``None`` means "first page".
        """
        sql = text(
            """
            SELECT
                rap.id AS agent_id,
                rap.fqn AS agent_fqn,
                t.slug AS tenant_slug,
                rap.created_by AS submitter_user_id,
                u.email AS submitter_email,
                rap.updated_at AS submitted_at,
                rap.reviewed_by_user_id AS claimed_by_user_id
            FROM registry_agent_profiles rap
            JOIN tenants t ON t.id = rap.tenant_id
            LEFT JOIN users u ON u.id = rap.created_by
            WHERE rap.review_status = 'pending_review'
              AND (:cursor IS NULL OR rap.updated_at > :cursor::timestamptz)
              AND (:claimed_by IS NULL OR rap.reviewed_by_user_id = :claimed_by)
              AND (NOT :unclaimed_only OR rap.reviewed_by_user_id IS NULL)
            ORDER BY rap.updated_at ASC
            LIMIT :limit
            """
        )
        result = await self._session.execute(
            sql,
            {
                "cursor": cursor,
                "claimed_by": str(claimed_by) if claimed_by is not None else None,
                "unclaimed_only": unclaimed_only,
                "limit": limit + 1,  # peek for next cursor
            },
        )
        rows = result.mappings().all()
        # Note: marketing metadata (category / description / tags) lives on
        # the current revision — for now we surface defaults to keep this
        # method shippable; T091 (frontend mirror) will populate them via
        # registry_agent_revisions once the revision mapping is wired up.
        items: list[ReviewSubmissionView] = []
        now = datetime.now(tz=UTC)
        for row in rows[:limit]:
            submitted_at = row["submitted_at"]
            items.append(
                ReviewSubmissionView(
                    agent_id=row["agent_id"],
                    agent_fqn=row["agent_fqn"],
                    tenant_slug=row["tenant_slug"],
                    submitter_user_id=row["submitter_user_id"],
                    submitter_email=row["submitter_email"] or "",
                    category="other",
                    marketing_description="(populated by revision metadata)",
                    tags=[],
                    submitted_at=submitted_at,
                    claimed_by_user_id=row["claimed_by_user_id"],
                    age_minutes=int((now - submitted_at).total_seconds() // 60),
                )
            )
        next_cursor = rows[limit]["submitted_at"].isoformat() if len(rows) > limit else None
        return ReviewQueueResponse(items=items, next_cursor=next_cursor)

    async def claim(self, agent_id: UUID, reviewer_id: UUID) -> None:
        """Optimistic conditional claim per research R6.

        Idempotent for the same reviewer; raises ``ReviewAlreadyClaimedError``
        if a different reviewer already holds the claim, and
        ``SubmissionAlreadyResolvedError`` if the row left ``pending_review``.
        """
        result = await self._session.execute(
            text(
                """
                UPDATE registry_agent_profiles
                   SET reviewed_by_user_id = :reviewer
                 WHERE id = :agent_id
                   AND review_status = 'pending_review'
                   AND (reviewed_by_user_id IS NULL OR reviewed_by_user_id = :reviewer)
                RETURNING reviewed_by_user_id
                """
            ),
            {"agent_id": str(agent_id), "reviewer": str(reviewer_id)},
        )
        if result.rowcount == 0:
            await self._raise_for_failed_claim(agent_id, reviewer_id)
        await self._session.commit()

    async def release(self, agent_id: UUID, reviewer_id: UUID) -> None:
        """Release a claim. Idempotent — sets ``reviewed_by_user_id = NULL``
        only if the caller currently holds the claim."""
        await self._session.execute(
            text(
                """
                UPDATE registry_agent_profiles
                   SET reviewed_by_user_id = NULL
                 WHERE id = :agent_id
                   AND review_status = 'pending_review'
                   AND reviewed_by_user_id = :reviewer
                """
            ),
            {"agent_id": str(agent_id), "reviewer": str(reviewer_id)},
        )
        await self._session.commit()

    async def approve(
        self,
        agent_id: UUID,
        reviewer_id: UUID,
        notes: str | None,
    ) -> None:
        """Transition ``pending_review → published`` and emit
        ``marketplace.approved`` followed by ``marketplace.published``.

        Per UPD-049 T073: also emits ``marketplace.source_updated`` so that
        the fan-out consumer (``MarketplaceFanoutConsumer``) can deliver
        notifications to fork owners. The fan-out is naturally a no-op
        for first-time approvals because no forks exist yet — we don't
        gate the event emission on fork existence to avoid an extra DB
        round-trip on the hot path.
        """
        # Capture whether this is a re-approval — used to populate the
        # source_updated payload's diff_summary_hash with the new revision's
        # id (see contract). For the first publication and subsequent
        # re-approvals the payload looks the same; the consumer's "find
        # forks" query is what determines whether a notification fires.
        result = await self._session.execute(
            text(
                """
                UPDATE registry_agent_profiles
                   SET review_status = 'published',
                       reviewed_by_user_id = :reviewer,
                       reviewed_at = now(),
                       review_notes = :notes
                 WHERE id = :agent_id
                   AND review_status = 'pending_review'
                RETURNING tenant_id, fqn, marketplace_scope, updated_at
                """
            ),
            {
                "agent_id": str(agent_id),
                "reviewer": str(reviewer_id),
                "notes": notes,
            },
        )
        row = result.mappings().first()
        if row is None:
            await self._raise_for_failed_state_change(agent_id)
        await self._session.commit()
        marketplace_review_decisions_total.labels(decision="approved").inc()
        # Approximate review age = now - the row's updated_at at the
        # moment of approval (the submission updated_at advances on
        # publish_with_scope, so it's a reasonable lower bound).
        age_seconds = max(
            0.0,
            (datetime.now(tz=UTC) - row["updated_at"]).total_seconds(),
        )
        marketplace_review_age_seconds.labels(decision="approved").observe(age_seconds)
        correlation = CorrelationContext(
            correlation_id=uuid4(),
            tenant_id=row["tenant_id"],
            agent_fqn=row["fqn"],
        )
        await publish_marketplace_event(
            self._event_producer,
            MarketplaceEventType.approved,
            MarketplaceApprovedPayload(
                agent_id=str(agent_id),
                reviewer_user_id=str(reviewer_id),
                approval_notes=notes,
            ),
            correlation,
        )
        await publish_marketplace_event(
            self._event_producer,
            MarketplaceEventType.published,
            MarketplacePublishedPayload(
                agent_id=str(agent_id),
                published_at=datetime.now(tz=UTC).isoformat(),
            ),
            correlation,
        )
        # T073 — fan-out trigger for fork owners. Only meaningful for
        # public_default_tenant scope (forks live downstream of public
        # agents). The fan-out consumer skips events with no matching
        # forks, so first-time approvals are no-ops at the consumer.
        if row["marketplace_scope"] == "public_default_tenant":
            new_version_id = await self._lookup_current_revision_id(agent_id)
            await publish_marketplace_event(
                self._event_producer,
                MarketplaceEventType.source_updated,
                MarketplaceSourceUpdatedPayload(
                    source_agent_id=str(agent_id),
                    new_version_id=str(new_version_id) if new_version_id else str(agent_id),
                    diff_summary_hash="sha256-pending",
                ),
                correlation,
            )

    async def _lookup_current_revision_id(self, agent_id: UUID) -> UUID | None:
        result = await self._session.execute(
            text(
                """
                SELECT id FROM registry_agent_revisions
                 WHERE agent_profile_id = :agent_id
                 ORDER BY created_at DESC
                 LIMIT 1
                """
            ),
            {"agent_id": str(agent_id)},
        )
        row = result.mappings().first()
        return row["id"] if row else None

    async def reject(
        self,
        agent_id: UUID,
        reviewer_id: UUID,
        reason: str,
    ) -> None:
        """Transition ``pending_review → rejected``, emit
        ``marketplace.rejected``, and trigger the submitter notification."""
        result = await self._session.execute(
            text(
                """
                UPDATE registry_agent_profiles
                   SET review_status = 'rejected',
                       reviewed_by_user_id = :reviewer,
                       reviewed_at = now(),
                       review_notes = :reason
                 WHERE id = :agent_id
                   AND review_status = 'pending_review'
                RETURNING tenant_id, fqn, created_by, updated_at
                """
            ),
            {
                "agent_id": str(agent_id),
                "reviewer": str(reviewer_id),
                "reason": reason,
            },
        )
        row = result.mappings().first()
        if row is None:
            await self._raise_for_failed_state_change(agent_id)
        await self._session.commit()
        marketplace_review_decisions_total.labels(decision="rejected").inc()
        age_seconds = max(
            0.0,
            (datetime.now(tz=UTC) - row["updated_at"]).total_seconds(),
        )
        marketplace_review_age_seconds.labels(decision="rejected").observe(age_seconds)
        correlation = CorrelationContext(
            correlation_id=uuid4(),
            tenant_id=row["tenant_id"],
            agent_fqn=row["fqn"],
        )
        await publish_marketplace_event(
            self._event_producer,
            MarketplaceEventType.rejected,
            MarketplaceRejectedPayload(
                agent_id=str(agent_id),
                reviewer_user_id=str(reviewer_id),
                rejection_reason=reason,
            ),
            correlation,
        )
        if self._notifications is not None:
            await self._notifications.notify_review_rejected(
                agent_id=agent_id,
                submitter_user_id=row["created_by"],
                rejection_reason=reason,
            )

    async def _raise_for_failed_claim(self, agent_id: UUID, reviewer_id: UUID) -> None:
        row = await self._session.execute(
            text(
                """
                SELECT review_status, reviewed_by_user_id
                  FROM registry_agent_profiles
                 WHERE id = :agent_id
                """
            ),
            {"agent_id": str(agent_id)},
        )
        result = row.mappings().first()
        if result is None:
            raise SubmissionNotFoundError(agent_id)
        if result["review_status"] != "pending_review":
            raise SubmissionAlreadyResolvedError(agent_id, result["review_status"])
        claimed_by = result["reviewed_by_user_id"]
        if claimed_by is not None and claimed_by != reviewer_id:
            raise ReviewAlreadyClaimedError(agent_id, claimed_by)
        # Otherwise no rows updated and no obvious cause — surface as not-found
        # to avoid leaking a confusing partial state.
        raise SubmissionNotFoundError(agent_id)

    async def _raise_for_failed_state_change(self, agent_id: UUID) -> None:
        row = await self._session.execute(
            text(
                "SELECT review_status FROM registry_agent_profiles WHERE id = :agent_id"
            ),
            {"agent_id": str(agent_id)},
        )
        result = row.mappings().first()
        if result is None:
            raise SubmissionNotFoundError(agent_id)
        raise SubmissionAlreadyResolvedError(agent_id, result["review_status"])
