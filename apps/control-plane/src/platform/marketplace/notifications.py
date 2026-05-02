"""Marketplace notification helpers (UPD-049 FR-017 / FR-027).

Two delivery surfaces:

1. ``notify_review_rejected`` — called by ``MarketplaceAdminService.reject``
   to deliver the rejection reason to the submitter via the existing
   ``AlertService.create_admin_alert`` (UPD-042). The notification carries
   the rejection reason so the submitter can address it before
   resubmitting.

2. ``MarketplaceNotificationConsumer`` — Kafka consumer subscribed to
   ``marketplace.events`` that fans out ``marketplace.source_updated``
   events to fork owners. Implemented in UPD-049 T072 (Phase 7); this
   module exposes the protocol shape today so the admin service can be
   wired up without circular imports.

Per ``MARKETPLACE_FORK_NOTIFY_SOURCE_OWNERS`` (settings, default ``True``)
the source-updated fan-out is on; setting it to ``False`` disables the
fan-out without code changes.
"""

from __future__ import annotations

from platform.common.logging import get_logger
from platform.notifications.service import AlertService
from uuid import UUID

LOGGER = get_logger(__name__)


class MarketplaceNotificationService:
    """Thin wrapper that delivers marketplace-specific notifications via the
    UPD-042 AlertService surface."""

    def __init__(self, alert_service: AlertService) -> None:
        self._alerts = alert_service

    async def notify_review_rejected(
        self,
        *,
        agent_id: UUID,
        submitter_user_id: UUID,
        rejection_reason: str,
    ) -> None:
        """Deliver a rejection notification to the submitter.

        The alert body includes the reviewer's reason so the submitter can
        address it before resubmitting.
        """
        await self._alerts.create_admin_alert(
            user_id=submitter_user_id,
            alert_type="marketplace.review_rejected",
            title="Marketplace submission rejected",
            body=(
                "Your public-marketplace submission was reviewed and rejected. "
                f"Reason from the reviewer: {rejection_reason}"
            ),
            urgency="medium",
            source_reference={
                "agent_id": str(agent_id),
                "kind": "marketplace.review_rejected",
            },
        )

    async def notify_source_updated(
        self,
        *,
        fork_owner_user_id: UUID,
        source_agent_id: UUID,
        source_fqn: str,
        new_version_id: UUID,
        diff_summary_hash: str,
    ) -> None:
        """Deliver a source-updated notification to a fork owner.

        Per FR-027 the body MUST clearly state that the fork has NOT been
        auto-updated, so the owner does not assume the upstream change
        propagated.
        """
        await self._alerts.create_admin_alert(
            user_id=fork_owner_user_id,
            alert_type="marketplace.source_updated",
            title=f"Upstream agent {source_fqn} was updated",
            body=(
                f"The public marketplace agent {source_fqn} has a new approved "
                f"version. Your fork has NOT been automatically updated. "
                f"Open the source detail page to compare versions if you "
                f"want to merge in the changes."
            ),
            urgency="low",
            source_reference={
                "kind": "marketplace.source_updated",
                "source_agent_id": str(source_agent_id),
                "new_version_id": str(new_version_id),
                "diff_summary_hash": diff_summary_hash,
            },
        )
