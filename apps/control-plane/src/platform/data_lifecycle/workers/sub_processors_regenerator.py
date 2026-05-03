"""Sub-processors regenerator — public-page snapshot cron + change fanout.

Tick interval: ``data_lifecycle.sub_processors_regenerate_interval_seconds``
(default 300 s, matching FR-757.5's 5-minute SLO).

On each tick:
1. Read the active sub-processors from PostgreSQL.
2. Render the current snapshot JSON.
3. Patch the ``public-pages-sub-processors-snapshot`` ConfigMap so the
   operationally-independent ``public-pages`` Helm release can fall back
   to it during a control-plane outage (rule 49).
4. Fan out the latest change events to verified email subscribers via
   UPD-077 (HMAC-signed outbound webhooks per rule 17).

The cron is idempotent: if no change has occurred since the last tick,
the patch operation is a no-op (etag comparison), and email fanout
deduplicates on `(subscription_id, sub_processor_id, change_id)`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from platform.common.logging import get_logger
from platform.data_lifecycle.models import (
    SubProcessor,
)
from platform.data_lifecycle.services.sub_processors_service import (
    _PublicView,
    render_rss,
)
from typing import Any, Protocol

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

LOGGER = get_logger(__name__)

DEFAULT_INTERVAL_SECONDS = 300


class _ConfigMapPatcher(Protocol):
    """Subset of the Kubernetes API client we need to patch a ConfigMap."""

    async def patch_namespaced_config_map(
        self, *, name: str, namespace: str, body: dict[str, Any]
    ) -> Any:
        ...


class _NotificationFanout(Protocol):
    """Subset of UPD-077 outbound-webhook fanout we use here."""

    async def fanout_to_subscribers(
        self,
        *,
        recipients: list[str],
        subject: str,
        body: str,
    ) -> None:
        ...


class SubProcessorsRegenerator:
    """Cron-friendly callable for the regenerator runtime profile."""

    def __init__(
        self,
        *,
        session_factory: Any,
        configmap_patcher: _ConfigMapPatcher | None = None,
        notification_fanout: _NotificationFanout | None = None,
        configmap_name: str = "public-pages-sub-processors-snapshot",
        configmap_namespace: str = "platform-public",
        interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
    ) -> None:
        self._session_factory = session_factory
        self._configmap_patcher = configmap_patcher
        self._notification_fanout = notification_fanout
        self._configmap_name = configmap_name
        self._configmap_namespace = configmap_namespace
        self.interval_seconds = interval_seconds
        self._last_snapshot_etag: str | None = None

    async def tick(self) -> dict[str, Any]:
        """Run one regeneration cycle. Returns a structured outcome dict."""

        async with self._session_factory() as session:
            try:
                snapshot = await self._read_snapshot(session)
                etag = snapshot["etag"]
                if etag == self._last_snapshot_etag:
                    return {
                        "status": "unchanged",
                        "etag": etag,
                        "items": snapshot["count"],
                    }
                await self._publish_configmap(snapshot)
                if self._notification_fanout is not None:
                    await self._fanout_changes(session, snapshot)
                self._last_snapshot_etag = etag
                return {
                    "status": "regenerated",
                    "etag": etag,
                    "items": snapshot["count"],
                }
            except Exception:
                LOGGER.exception(
                    "data_lifecycle.sub_processors_regenerator_failed"
                )
                return {"status": "failed"}

    def register(self, scheduler: Any) -> None:
        scheduler.add_job(
            self.tick,
            trigger="interval",
            seconds=self.interval_seconds,
            id="data_lifecycle_sub_processors_regenerator",
            replace_existing=True,
        )

    # =========================================================================
    # Internals
    # =========================================================================

    async def _read_snapshot(
        self, session: AsyncSession
    ) -> dict[str, Any]:
        result = await session.execute(
            select(SubProcessor).where(SubProcessor.is_active.is_(True))
        )
        rows = list(result.scalars().all())
        items = [_PublicView.from_row(r) for r in rows]
        latest = max((r.updated_at for r in rows if r.updated_at), default=None)
        last_updated_at = (
            latest.isoformat() if latest else datetime.now(UTC).isoformat()
        )
        snapshot = {
            "last_updated_at": last_updated_at,
            "count": len(items),
            "items": [
                {
                    "name": i.name,
                    "category": i.category,
                    "location": i.location,
                    "data_categories": i.data_categories,
                    "privacy_policy_url": i.privacy_policy_url,
                    "dpa_url": i.dpa_url,
                    "started_using_at": i.started_using_at,
                }
                for i in items
            ],
            "rss": render_rss(items=rows, site_base_url="https://musematic.ai"),
        }
        # Cheap etag = last_updated + count.
        snapshot["etag"] = f"{last_updated_at}|{len(items)}"
        return snapshot

    async def _publish_configmap(self, snapshot: dict[str, Any]) -> None:
        if self._configmap_patcher is None:
            LOGGER.info(
                "data_lifecycle.sub_processors_regenerator_no_patcher",
                items=snapshot["count"],
            )
            return
        body = {
            "data": {
                "sub-processors.json": json.dumps(
                    {
                        "last_updated_at": snapshot["last_updated_at"],
                        "items": snapshot["items"],
                    },
                    indent=2,
                    sort_keys=True,
                ),
                "sub-processors.rss": snapshot["rss"],
            }
        }
        await self._configmap_patcher.patch_namespaced_config_map(
            name=self._configmap_name,
            namespace=self._configmap_namespace,
            body=body,
        )
        LOGGER.info(
            "data_lifecycle.sub_processors_regenerator_published",
            items=snapshot["count"],
        )

    async def _fanout_changes(
        self, session: AsyncSession, snapshot: dict[str, Any]
    ) -> None:
        result = await session.execute(
            text(
                """
                SELECT email
                FROM sub_processor_email_subscriptions
                WHERE verified_at IS NOT NULL
                  AND unsubscribed_at IS NULL
                """
            )
        )
        emails = [str(row[0]) for row in result.all()]
        if not emails or self._notification_fanout is None:
            return
        subject = "Musematic sub-processors list updated"
        body = (
            "The Musematic sub-processors page has been updated. "
            f"Current list contains {snapshot['count']} active processors. "
            "View at https://musematic.ai/legal/sub-processors"
        )
        await self._notification_fanout.fanout_to_subscribers(
            recipients=emails,
            subject=subject,
            body=body,
        )
