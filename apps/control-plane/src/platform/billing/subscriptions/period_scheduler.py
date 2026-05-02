from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from platform.audit.dependencies import build_audit_chain_service
from platform.audit.service import AuditChainService
from platform.billing.subscriptions.repository import SubscriptionsRepository
from platform.common import database
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.logging import get_logger
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import text

LOGGER = get_logger(__name__)


async def run_period_rollover(app: Any) -> None:
    now = datetime.now(UTC)
    producer = cast(EventProducer | None, app.state.clients.get("kafka"))
    settings = cast(PlatformSettings, getattr(app.state, "settings", PlatformSettings()))
    async with database.PlatformStaffAsyncSessionLocal() as session:
        audit_chain = build_audit_chain_service(session, settings, producer)
        repository = SubscriptionsRepository(session)
        due = await repository.list_due_for_period_rollover(now)
        for subscription in due:
            await _rollover_subscription(session, repository, subscription, producer, audit_chain)
        await session.commit()
    if due:
        LOGGER.info("billing.period_rollover.completed", subscription_count=len(due))


async def _rollover_subscription(
    session: Any,
    repository: SubscriptionsRepository,
    subscription: Any,
    producer: EventProducer | None,
    audit_chain: AuditChainService,
) -> None:
    previous_start = subscription.current_period_start
    previous_end = subscription.current_period_end
    new_start = previous_end
    new_end = previous_end + timedelta(days=30)
    downgrade_due = subscription.cancel_at_period_end
    old_plan_slug = await _plan_slug(session, subscription.plan_id)
    old_plan_version = subscription.plan_version
    status = "active" if downgrade_due else subscription.status
    await repository.advance_period(
        subscription,
        new_period_start=new_start,
        new_period_end=new_end,
        status=status,
    )
    cleanup_payload: dict[str, int] = {}
    new_plan_slug = old_plan_slug
    new_plan_version = old_plan_version
    if downgrade_due:
        free_plan = await session.execute(
            text(
                """
                SELECT p.id, pv.version
                  FROM plans p
                  JOIN plan_versions pv ON pv.plan_id = p.id
                 WHERE p.slug = 'free'
                   AND pv.deprecated_at IS NULL
                 ORDER BY pv.published_at DESC NULLS LAST, pv.version DESC
                 LIMIT 1
                """
            )
        )
        row = free_plan.one_or_none()
        if row is not None:
            subscription.plan_id = row[0]
            subscription.plan_version = int(row[1])
            subscription.cancel_at_period_end = False
            cleanup_payload = await _data_exceeding_free_limits(session, subscription)
            new_plan_slug = "free"
            new_plan_version = int(row[1])
            await session.flush()
    event_type = (
        "billing.subscription.downgrade_effective"
        if downgrade_due
        else "billing.subscription.period_renewed"
    )
    payload = (
        {
            "from_plan_slug": old_plan_slug,
            "from_plan_version": old_plan_version,
            "to_plan_slug": new_plan_slug,
            "to_plan_version": new_plan_version,
            "data_exceeding_free_limits": cleanup_payload,
        }
        if event_type == "billing.subscription.downgrade_effective"
        else {
            "previous_period_start": previous_start.isoformat(),
            "previous_period_end": previous_end.isoformat(),
            "new_period_start": new_start.isoformat(),
            "new_period_end": new_end.isoformat(),
            "previous_period_overage_eur": "0.00",
        }
    )
    if producer is not None:
        await producer.publish(
            "billing.lifecycle",
            str(subscription.tenant_id),
            event_type,
            payload,
            CorrelationContext(
                correlation_id=uuid4(),
                tenant_id=subscription.tenant_id,
                workspace_id=(
                    subscription.scope_id if subscription.scope_type == "workspace" else None
                ),
            ),
            "billing.period_scheduler",
        )
    await _append_audit(audit_chain, subscription, event_type, payload)


async def _data_exceeding_free_limits(session: Any, subscription: Any) -> dict[str, int]:
    workspace_id = subscription.scope_id if subscription.scope_type == "workspace" else None
    active_workspaces = 0
    active_agents = 0
    active_users = 0
    if workspace_id is not None:
        owner_id = await session.scalar(
            text("SELECT owner_id FROM workspaces_workspaces WHERE id = :workspace_id"),
            {"workspace_id": str(workspace_id)},
        )
        if owner_id is not None:
            active_workspaces = int(
                await session.scalar(
                    text(
                        """
                        SELECT count(*)
                          FROM workspaces_workspaces
                         WHERE owner_id = :owner_id
                           AND status != 'deleted'
                        """
                    ),
                    {"owner_id": str(owner_id)},
                )
                or 0
            )
        active_agents = int(
            await session.scalar(
                text(
                    """
                    SELECT count(*)
                      FROM registry_agent_profiles
                     WHERE workspace_id = :workspace_id
                       AND status = 'published'
                    """
                ),
                {"workspace_id": str(workspace_id)},
            )
            or 0
        )
        active_users = int(
            await session.scalar(
                text(
                    """
                    SELECT count(*)
                      FROM workspaces_memberships
                     WHERE workspace_id = :workspace_id
                    """
                ),
                {"workspace_id": str(workspace_id)},
            )
            or 0
        )
    else:
        active_workspaces = int(
            await session.scalar(
                text(
                    """
                    SELECT count(*)
                      FROM workspaces_workspaces
                     WHERE tenant_id = :tenant_id
                       AND status != 'deleted'
                    """
                ),
                {"tenant_id": str(subscription.tenant_id)},
            )
            or 0
        )
    return {
        "workspaces": max(int(active_workspaces or 0) - 1, 0),
        "agents": max(active_agents - 5, 0),
        "users": max(active_users - 3, 0),
    }


async def _plan_slug(session: Any, plan_id: Any) -> str:
    return str(
        await session.scalar(
            text("SELECT slug FROM plans WHERE id = :plan_id"),
            {"plan_id": str(plan_id)},
        )
        or "unknown"
    )


async def _append_audit(
    audit_chain: AuditChainService,
    subscription: Any,
    event_type: str,
    payload: dict[str, object],
) -> None:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )
    await audit_chain.append(
        uuid4(),
        "billing.period_scheduler",
        canonical,
        event_type=event_type,
        canonical_payload_json=dict(payload),
        tenant_id=subscription.tenant_id,
    )


def build_period_rollover_scheduler(app: Any) -> Any | None:
    try:
        scheduler_module = __import__(
            "apscheduler.schedulers.asyncio",
            fromlist=["AsyncIOScheduler"],
        )
    except Exception:
        return None
    settings = cast(PlatformSettings, app.state.settings)
    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")

    async def _run() -> None:
        await run_period_rollover(app)

    scheduler.add_job(
        _run,
        "interval",
        seconds=settings.BILLING_PERIOD_SCHEDULER_INTERVAL_SECONDS,
        id="billing.period_rollover",
        replace_existing=True,
    )
    return scheduler
