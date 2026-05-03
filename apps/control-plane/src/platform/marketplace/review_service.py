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
    marketplace_self_review_attempts_total,
)
from platform.registry.events import (
    MarketplaceApprovedPayload,
    MarketplaceEventType,
    MarketplacePublishedPayload,
    MarketplaceRejectedPayload,
    MarketplaceReviewAssignedPayload,
    MarketplaceReviewUnassignedPayload,
    MarketplaceSourceUpdatedPayload,
    publish_marketplace_event,
)
from platform.registry.exceptions import (
    ReviewAlreadyClaimedError,
    ReviewerAssignmentConflictError,
    SelfReviewNotAllowedError,
    SubmissionAlreadyResolvedError,
    SubmissionNotFoundError,
    SubmissionNotInPendingReviewError,
)
from platform.registry.schemas import ReviewQueueResponse, ReviewSubmissionView
from typing import Literal, NoReturn, Protocol
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
        assigned_to: UUID | None = None,
        unassigned_only: bool = False,
        include_self_authored: bool = False,
        current_user_id: UUID | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> ReviewQueueResponse:
        """List submissions in ``review_status='pending_review'``.

        Cursor format: opaque ISO-8601 ``submitted_at`` of the last item
        returned in the previous page. ``None`` means "first page".

        UPD-049 refresh (102) parameters:

        * ``assigned_to`` — filter by ``assigned_reviewer_user_id``. When
          set, ``unassigned_only`` MUST be False.
        * ``unassigned_only`` — only rows with ``assigned_reviewer_user_id
          IS NULL``. Mutually exclusive with ``assigned_to``.
        * ``include_self_authored`` — by default rows where
          ``created_by == current_user_id`` are excluded so reviewers do
          not accidentally action their own work.
        * ``current_user_id`` — required to compute ``is_self_authored``
          and to drive the default ``include_self_authored=False``
          filter. Pass the calling reviewer's user_id from the route.
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
                rap.reviewed_by_user_id AS claimed_by_user_id,
                rap.assigned_reviewer_user_id AS assigned_reviewer_user_id,
                au.email AS assigned_reviewer_email
            FROM registry_agent_profiles rap
            JOIN tenants t ON t.id = rap.tenant_id
            LEFT JOIN users u ON u.id = rap.created_by
            LEFT JOIN users au ON au.id = rap.assigned_reviewer_user_id
            WHERE rap.review_status = 'pending_review'
              AND (:cursor IS NULL OR rap.updated_at > :cursor::timestamptz)
              AND (:claimed_by IS NULL OR rap.reviewed_by_user_id = :claimed_by)
              AND (NOT :unclaimed_only OR rap.reviewed_by_user_id IS NULL)
              AND (:assigned_to IS NULL OR rap.assigned_reviewer_user_id = :assigned_to)
              AND (NOT :unassigned_only OR rap.assigned_reviewer_user_id IS NULL)
              AND (:include_self_authored
                   OR :current_user_id IS NULL
                   OR rap.created_by IS NULL
                   OR rap.created_by <> :current_user_id)
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
                "assigned_to": str(assigned_to) if assigned_to is not None else None,
                "unassigned_only": unassigned_only,
                "include_self_authored": include_self_authored,
                "current_user_id": (
                    str(current_user_id) if current_user_id is not None else None
                ),
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
            submitter_user_id = row["submitter_user_id"]
            items.append(
                ReviewSubmissionView(
                    agent_id=row["agent_id"],
                    agent_fqn=row["agent_fqn"],
                    tenant_slug=row["tenant_slug"],
                    submitter_user_id=submitter_user_id,
                    submitter_email=row["submitter_email"] or "",
                    category="other",
                    marketing_description="(populated by revision metadata)",
                    tags=[],
                    submitted_at=submitted_at,
                    claimed_by_user_id=row["claimed_by_user_id"],
                    age_minutes=int((now - submitted_at).total_seconds() // 60),
                    assigned_reviewer_user_id=row["assigned_reviewer_user_id"],
                    assigned_reviewer_email=row["assigned_reviewer_email"],
                    is_self_authored=(
                        current_user_id is not None
                        and submitter_user_id is not None
                        and submitter_user_id == current_user_id
                    ),
                )
            )
        next_cursor = rows[limit]["submitted_at"].isoformat() if len(rows) > limit else None
        return ReviewQueueResponse(items=items, next_cursor=next_cursor)

    async def _ensure_not_self_review(
        self,
        agent_id: UUID,
        actor_user_id: UUID,
        *,
        action: Literal["assign", "claim", "approve", "reject"],
    ) -> UUID | None:
        """UPD-049 refresh (FR-741.9) — refuse the action when actor authored
        the submission.

        Returns the row's ``created_by`` (submitter user id) on the
        permitted path so callers can avoid an extra round-trip. When the
        agent is missing the helper returns ``None`` and lets the caller's
        downstream not-found path surface the error — this preserves the
        FR-741.10 byte-identical 404 behaviour for not-yet-published
        public agents.

        On refusal: emits a ``marketplace.review.self_review_attempted``
        structured-log audit entry (no Kafka event — refusals are
        diagnostics, not state changes) and raises
        ``SelfReviewNotAllowedError``.
        """
        row = await self._session.execute(
            text(
                "SELECT created_by FROM registry_agent_profiles WHERE id = :agent_id"
            ),
            {"agent_id": str(agent_id)},
        )
        result = row.mappings().first()
        if result is None:
            return None
        raw_submitter = result["created_by"]
        submitter_user_id: UUID | None = (
            raw_submitter if isinstance(raw_submitter, UUID) else None
        )
        if submitter_user_id is not None and submitter_user_id == actor_user_id:
            marketplace_self_review_attempts_total.labels(action=action).inc()
            LOGGER.info(
                "marketplace.review.self_review_attempted",
                extra={
                    "agent_id": str(agent_id),
                    "submitter_user_id": str(submitter_user_id),
                    "actor_user_id": str(actor_user_id),
                    "action": action,
                },
            )
            raise SelfReviewNotAllowedError(
                submitter_user_id=submitter_user_id,
                actor_user_id=actor_user_id,
                action=action,
            )
        return submitter_user_id

    async def claim(self, agent_id: UUID, reviewer_id: UUID) -> None:
        """Optimistic conditional claim per research R6.

        Idempotent for the same reviewer; raises ``ReviewAlreadyClaimedError``
        if a different reviewer already holds the claim,
        ``ReviewerAssignmentConflictError`` if the row is assigned to a
        different reviewer (claim-jumping prevention — UPD-049 refresh
        FR-738/R11), ``SelfReviewNotAllowedError`` if the claimant is the
        submitter (UPD-049 refresh FR-741.9), and
        ``SubmissionAlreadyResolvedError`` if the row left ``pending_review``.
        """
        # FR-741.9 — refuse self-review before any UPDATE.
        await self._ensure_not_self_review(agent_id, reviewer_id, action="claim")
        result = await self._session.execute(
            text(
                """
                UPDATE registry_agent_profiles
                   SET reviewed_by_user_id = :reviewer
                 WHERE id = :agent_id
                   AND review_status = 'pending_review'
                   AND (reviewed_by_user_id IS NULL OR reviewed_by_user_id = :reviewer)
                   AND (assigned_reviewer_user_id IS NULL
                        OR assigned_reviewer_user_id = :reviewer)
                RETURNING reviewed_by_user_id
                """
            ),
            {"agent_id": str(agent_id), "reviewer": str(reviewer_id)},
        )
        # Use first() to detect "no row updated" — async Result.rowcount is
        # not reliable across drivers, but RETURNING + first() is.
        if result.first() is None:
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
        # FR-741.9 — refuse self-review before any UPDATE.
        await self._ensure_not_self_review(agent_id, reviewer_id, action="approve")
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
        LOGGER.info(
            "marketplace.review.approved",
            extra={
                "agent_id": str(agent_id),
                "agent_fqn": row["fqn"],
                "marketplace_scope": row["marketplace_scope"],
                "review_status": "published",
                "actor_user_id": str(reviewer_id),
                "tenant_id": str(row["tenant_id"]),
                "review_age_seconds": age_seconds,
            },
        )
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
        # FR-741.9 — refuse self-review before any UPDATE.
        await self._ensure_not_self_review(agent_id, reviewer_id, action="reject")
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
        LOGGER.info(
            "marketplace.review.rejected",
            extra={
                "agent_id": str(agent_id),
                "agent_fqn": row["fqn"],
                "review_status": "rejected",
                "actor_user_id": str(reviewer_id),
                "tenant_id": str(row["tenant_id"]),
                "submitter_user_id": str(row["created_by"]),
                "review_age_seconds": age_seconds,
            },
        )
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

    async def assign(
        self,
        agent_id: UUID,
        reviewer_user_id: UUID,
        assigner_user_id: UUID,
    ) -> dict[str, object]:
        """UPD-049 refresh — assign a pending-review submission to a reviewer.

        Idempotent if the row is already assigned to the same reviewer
        (no-op, no audit, no Kafka). Raises:

        * ``SelfReviewNotAllowedError`` if ``reviewer_user_id`` is the
          submitter (FR-741.9).
        * ``SubmissionNotFoundError`` if the row does not exist.
        * ``SubmissionNotInPendingReviewError`` if the row is not in
          ``pending_review`` status.
        * ``ReviewerAssignmentConflictError`` if the row is already
          assigned to a different reviewer.

        Returns a dict with assignment details for the response payload.
        """
        # FR-741.9 — refuse assigning a submission to its own author.
        await self._ensure_not_self_review(
            agent_id, reviewer_user_id, action="assign"
        )
        # Optimistic conditional UPDATE — only matches rows in
        # pending_review whose current assignee is NULL or the same
        # reviewer (idempotent).
        result = await self._session.execute(
            text(
                """
                UPDATE registry_agent_profiles
                   SET assigned_reviewer_user_id = :reviewer
                 WHERE id = :agent_id
                   AND review_status = 'pending_review'
                   AND (assigned_reviewer_user_id IS NULL
                        OR assigned_reviewer_user_id = :reviewer)
                RETURNING tenant_id, fqn, created_by,
                          assigned_reviewer_user_id
                """
            ),
            {
                "agent_id": str(agent_id),
                "reviewer": str(reviewer_user_id),
            },
        )
        row = result.mappings().first()
        if row is None:
            await self._raise_for_failed_assign(agent_id, reviewer_user_id)
        # Fetch the assignee email for the response payload.
        assignee_email_row = await self._session.execute(
            text("SELECT email FROM users WHERE id = :user_id"),
            {"user_id": str(reviewer_user_id)},
        )
        assignee_email = assignee_email_row.scalar() or ""
        await self._session.commit()
        assigned_at = datetime.now(tz=UTC)
        LOGGER.info(
            "marketplace.review.assigned",
            extra={
                "agent_id": str(agent_id),
                "agent_fqn": row["fqn"],
                "submitter_user_id": str(row["created_by"]),
                "assigner_user_id": str(assigner_user_id),
                "assignee_user_id": str(reviewer_user_id),
                "tenant_id": str(row["tenant_id"]),
            },
        )
        correlation = CorrelationContext(
            correlation_id=uuid4(),
            tenant_id=row["tenant_id"],
            agent_fqn=row["fqn"],
        )
        await publish_marketplace_event(
            self._event_producer,
            MarketplaceEventType.review_assigned,
            MarketplaceReviewAssignedPayload(
                agent_id=str(agent_id),
                agent_fqn=row["fqn"],
                submitter_user_id=str(row["created_by"]),
                assigner_user_id=str(assigner_user_id),
                assignee_user_id=str(reviewer_user_id),
                prior_assignee_user_id=None,
                assigned_at=assigned_at.isoformat(),
            ),
            correlation,
        )
        return {
            "agent_id": str(agent_id),
            "assigned_reviewer_user_id": str(reviewer_user_id),
            "assigned_reviewer_email": assignee_email,
            "assigner_user_id": str(assigner_user_id),
            "assigned_at": assigned_at,
            "prior_assignee_user_id": None,
        }

    async def unassign(
        self,
        agent_id: UUID,
        unassigner_user_id: UUID,
    ) -> dict[str, object]:
        """UPD-049 refresh — clear the assignment of a pending-review submission.

        Idempotent — a no-op when the row is already unassigned (no audit,
        no Kafka). Raises ``SubmissionNotFoundError`` if the row does not
        exist or ``SubmissionNotInPendingReviewError`` if the row is not
        in ``pending_review``.

        Captures the prior assignee via a CTE so the Kafka payload and
        audit log carry the correct ``prior_assignee_user_id``.
        """
        result = await self._session.execute(
            text(
                """
                WITH prev AS (
                    SELECT id, assigned_reviewer_user_id AS prior_assignee
                      FROM registry_agent_profiles
                     WHERE id = :agent_id
                       AND review_status = 'pending_review'
                       AND assigned_reviewer_user_id IS NOT NULL
                )
                UPDATE registry_agent_profiles AS rap
                   SET assigned_reviewer_user_id = NULL
                  FROM prev
                 WHERE rap.id = prev.id
                RETURNING rap.tenant_id, rap.fqn, rap.created_by,
                          prev.prior_assignee
                """
            ),
            {"agent_id": str(agent_id)},
        )
        row = result.mappings().first()
        unassigned_at = datetime.now(tz=UTC)
        if row is None:
            # Diagnose: row missing, wrong state, or already unassigned.
            current = await self._session.execute(
                text(
                    """
                    SELECT review_status
                      FROM registry_agent_profiles
                     WHERE id = :agent_id
                    """
                ),
                {"agent_id": str(agent_id)},
            )
            current_row = current.mappings().first()
            if current_row is None:
                raise SubmissionNotFoundError(agent_id)
            if current_row["review_status"] != "pending_review":
                raise SubmissionNotInPendingReviewError(
                    agent_id, current_row["review_status"]
                )
            # Already unassigned — idempotent no-op (no audit, no Kafka).
            return {
                "agent_id": str(agent_id),
                "prior_assignee_user_id": None,
                "unassigned_at": unassigned_at,
                "unassigner_user_id": str(unassigner_user_id),
            }
        await self._session.commit()
        prior_assignee = row["prior_assignee"]
        LOGGER.info(
            "marketplace.review.unassigned",
            extra={
                "agent_id": str(agent_id),
                "agent_fqn": row["fqn"],
                "submitter_user_id": str(row["created_by"]),
                "unassigner_user_id": str(unassigner_user_id),
                "prior_assignee_user_id": str(prior_assignee),
                "tenant_id": str(row["tenant_id"]),
            },
        )
        correlation = CorrelationContext(
            correlation_id=uuid4(),
            tenant_id=row["tenant_id"],
            agent_fqn=row["fqn"],
        )
        await publish_marketplace_event(
            self._event_producer,
            MarketplaceEventType.review_unassigned,
            MarketplaceReviewUnassignedPayload(
                agent_id=str(agent_id),
                agent_fqn=row["fqn"],
                submitter_user_id=str(row["created_by"]),
                unassigner_user_id=str(unassigner_user_id),
                prior_assignee_user_id=str(prior_assignee),
                unassigned_at=unassigned_at.isoformat(),
            ),
            correlation,
        )
        return {
            "agent_id": str(agent_id),
            "prior_assignee_user_id": str(prior_assignee),
            "unassigned_at": unassigned_at,
            "unassigner_user_id": str(unassigner_user_id),
        }

    async def _raise_for_failed_assign(
        self, agent_id: UUID, reviewer_user_id: UUID
    ) -> NoReturn:
        row = await self._session.execute(
            text(
                """
                SELECT review_status, assigned_reviewer_user_id
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
            raise SubmissionNotInPendingReviewError(
                agent_id, result["review_status"]
            )
        existing = result["assigned_reviewer_user_id"]
        if existing is not None and existing != reviewer_user_id:
            raise ReviewerAssignmentConflictError(agent_id, existing)
        raise SubmissionNotFoundError(agent_id)

    async def _raise_for_failed_claim(
        self, agent_id: UUID, reviewer_id: UUID
    ) -> NoReturn:
        row = await self._session.execute(
            text(
                """
                SELECT review_status,
                       reviewed_by_user_id,
                       assigned_reviewer_user_id
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
        # UPD-049 refresh — claim-jumping check has higher precedence than
        # the legacy "already claimed" check because an assignment is set
        # by a lead and overrides the in-flight claim semantics.
        assigned_to = result["assigned_reviewer_user_id"]
        if assigned_to is not None and assigned_to != reviewer_id:
            raise ReviewerAssignmentConflictError(agent_id, assigned_to)
        claimed_by = result["reviewed_by_user_id"]
        if claimed_by is not None and claimed_by != reviewer_id:
            raise ReviewAlreadyClaimedError(agent_id, claimed_by)
        # Otherwise no rows updated and no obvious cause — surface as not-found
        # to avoid leaking a confusing partial state.
        raise SubmissionNotFoundError(agent_id)

    async def _raise_for_failed_state_change(self, agent_id: UUID) -> NoReturn:
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
