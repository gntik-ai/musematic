from __future__ import annotations

import json
from decimal import Decimal
from platform.audit.service import AuditChainService
from platform.billing.exceptions import PlanNotFoundError, PlanVersionImmutableError
from platform.billing.metrics import metrics
from platform.billing.plans.models import Plan, PlanVersion
from platform.billing.plans.repository import PLAN_VERSION_FIELDS, PlansRepository
from platform.billing.plans.schemas import PlanUpdate, PlanVersionPublish
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from typing import Any
from uuid import UUID, uuid4


class PlansService:
    def __init__(
        self,
        repository: PlansRepository,
        *,
        audit_chain: AuditChainService | None = None,
        producer: EventProducer | None = None,
    ) -> None:
        self.repository = repository
        self.audit_chain = audit_chain
        self.producer = producer

    async def publish_new_version(
        self,
        slug: str,
        payload: PlanVersionPublish,
        *,
        actor_id: UUID | None = None,
        tenant_id: UUID | None = None,
    ) -> PlanVersion:
        plan = await self.repository.get_by_slug(slug)
        if plan is None:
            raise PlanNotFoundError(slug)
        parameters = payload.model_dump(exclude_none=True)
        prior, new_version = await self.repository.publish_new_version(
            plan,
            parameters,
            created_by=actor_id or payload.created_by,
        )
        diff = self.compute_diff_against_prior(prior, new_version)
        await self._append_audit(
            "billing.plan.published",
            {
                "plan_id": str(plan.id),
                "plan_slug": plan.slug,
                "new_version": new_version.version,
                "prior_version": prior.version if prior is not None else None,
                "diff": diff,
            },
            tenant_id=tenant_id,
        )
        await self._publish_event(
            "billing.plan.published",
            str(plan.id),
            {
                "plan_id": str(plan.id),
                "plan_slug": plan.slug,
                "new_version": new_version.version,
                "prior_version": prior.version if prior is not None else None,
                "diff": diff,
                "deprecated_prior_at": (
                    prior.deprecated_at.isoformat() if prior and prior.deprecated_at else None
                ),
            },
            tenant_id=tenant_id,
        )
        metrics.record_plan_publish()
        return new_version

    async def deprecate_version(
        self,
        plan_id: UUID,
        version: int,
        *,
        tenant_id: UUID | None = None,
    ) -> PlanVersion | None:
        stored = await self.repository.deprecate_version(plan_id, version)
        if stored is None:
            return None
        subscription_count = await self.repository.count_subscriptions_on_version(plan_id, version)
        await self._append_audit(
            "billing.plan.deprecated",
            {
                "plan_id": str(plan_id),
                "version": version,
                "subscriptions_pinned_count": subscription_count,
            },
            tenant_id=tenant_id,
        )
        return stored

    async def update_plan_metadata(self, slug: str, payload: PlanUpdate) -> Plan:
        plan = await self.repository.get_by_slug(slug)
        if plan is None:
            raise PlanNotFoundError(slug)
        return await self.repository.update_plan(plan, **payload.model_dump(exclude_unset=True))

    def guard_published_version_update(
        self,
        version: PlanVersion,
        updates: dict[str, Any],
    ) -> None:
        if version.published_at is None:
            return
        blocked = sorted(set(updates).intersection(PLAN_VERSION_FIELDS) - {"extras_json"})
        if blocked:
            raise PlanVersionImmutableError(version.plan_id, version.version)

    def compute_diff_against_prior(
        self,
        prior: PlanVersion | None,
        current: PlanVersion,
    ) -> dict[str, dict[str, object | None]]:
        diff: dict[str, dict[str, object | None]] = {}
        for field in PLAN_VERSION_FIELDS:
            before = getattr(prior, field, None) if prior is not None else None
            after = getattr(current, field)
            if before != after:
                diff[field] = {"from": _jsonable(before), "to": _jsonable(after)}
        return diff

    async def _append_audit(
        self,
        event_type: str,
        payload: dict[str, object],
        *,
        tenant_id: UUID | None,
    ) -> None:
        if self.audit_chain is None:
            return
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        await self.audit_chain.append(
            uuid4(),
            "billing.plans",
            canonical,
            event_type=event_type,
            actor_role="super_admin",
            canonical_payload_json=dict(payload),
            tenant_id=tenant_id,
        )

    async def _publish_event(
        self,
        event_type: str,
        key: str,
        payload: dict[str, object],
        *,
        tenant_id: UUID | None,
    ) -> None:
        if self.producer is None:
            return
        await self.producer.publish(
            "billing.lifecycle",
            key,
            event_type,
            payload,
            CorrelationContext(correlation_id=uuid4(), tenant_id=tenant_id),
            "billing.plans",
        )


def _jsonable(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()  # type: ignore[no-any-return]
    return value
