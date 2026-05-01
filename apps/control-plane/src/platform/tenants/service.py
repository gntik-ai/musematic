from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from platform.audit.service import AuditChainService
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.logging import get_logger
from platform.tenants.cascade import tenant_cascade_handlers
from platform.tenants.dns_automation import DnsAutomationClient
from platform.tenants.events import (
    TenantBrandingUpdatedPayload,
    TenantCreatedPayload,
    TenantDeletedPayload,
    TenantDeletionCancelledPayload,
    TenantEventType,
    TenantReactivatedPayload,
    TenantScheduledForDeletionPayload,
    TenantSuspendedPayload,
    publish_tenant_event,
)
from platform.tenants.exceptions import (
    DefaultTenantImmutableError,
    DPAMissingError,
    RegionInvalidError,
    ReservedSlugError,
    SlugInvalidError,
    SlugTakenError,
    TenantNotFoundError,
)
from platform.tenants.models import Tenant
from platform.tenants.repository import TenantsRepository
from platform.tenants.reserved_slugs import RESERVED_SLUGS
from platform.tenants.resolver import TENANT_INVALIDATION_CHANNEL
from platform.tenants.schemas import SLUG_RE, TenantCreate, TenantScheduleDeletion, TenantUpdate
from platform.two_person_approval.service import TwoPersonApprovalError, TwoPersonApprovalService
from typing import Any, Protocol, cast
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

TENANT_DPA_BUCKET = "tenant-dpas"
ALLOWED_TENANT_REGIONS = frozenset({"global", "eu-central", "us-east", "us-west"})
LOGGER = get_logger(__name__)


class ObjectStorageClient(Protocol):
    async def create_bucket_if_not_exists(self, bucket: str) -> None: ...

    async def upload_object(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> None: ...

    async def download_object(self, bucket: str, key: str) -> bytes: ...

    async def delete_object(self, bucket: str, key: str) -> None: ...


class FirstAdminInvitationService(Protocol):
    async def send_first_admin_invitation(self, tenant: Tenant, email: str) -> str: ...


class TenantsService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        repository: TenantsRepository,
        settings: PlatformSettings,
        producer: EventProducer | None,
        audit_chain: AuditChainService | None,
        dns_automation: DnsAutomationClient,
        notifications: FirstAdminInvitationService | None,
        object_storage: ObjectStorageClient | None,
        redis_client: AsyncRedisClient | None = None,
    ) -> None:
        self.session = session
        self.repository = repository
        self.settings = settings
        self.producer = producer
        self.audit_chain = audit_chain
        self.dns_automation = dns_automation
        self.notifications = notifications
        self.object_storage = object_storage
        self.redis_client = redis_client

    async def provision_enterprise_tenant(
        self,
        actor: dict[str, Any],
        request: TenantCreate,
    ) -> Tenant:
        await self._validate_create_request(request)
        artifact = await self._finalize_dpa_artifact(request)
        now = datetime.now(UTC)
        tenant = Tenant(
            slug=request.slug,
            kind="enterprise",
            subdomain=request.slug,
            display_name=request.display_name,
            region=request.region,
            data_isolation_mode="pool",
            branding_config_json=request.branding_config.model_dump(exclude_none=True),
            status="active",
            created_by_super_admin_id=_actor_id(actor),
            dpa_signed_at=now,
            dpa_version=request.dpa_version,
            dpa_artifact_uri=artifact["uri"],
            dpa_artifact_sha256=artifact["sha256"],
            contract_metadata_json=dict(request.contract_metadata),
            feature_flags_json={},
        )
        await self.repository.create(tenant)
        await self.dns_automation.ensure_records(tenant.subdomain)
        if self.notifications is not None:
            await self.notifications.send_first_admin_invitation(
                tenant,
                str(request.first_admin_email),
            )
        await self._append_created_audit(actor, tenant, request)
        await self.session.commit()
        await publish_tenant_event(
            producer=self.producer,
            event_type=TenantEventType.created,
            payload=TenantCreatedPayload(
                tenant_id=tenant.id,
                slug=tenant.slug,
                subdomain=tenant.subdomain,
                kind=tenant.kind,
                region=tenant.region,
                display_name=tenant.display_name,
                first_admin_email=str(request.first_admin_email),
                dpa_version=request.dpa_version,
                dpa_artifact_sha256=tenant.dpa_artifact_sha256,
            ),
            correlation_ctx=CorrelationContext(correlation_id=uuid4()),
        )
        return tenant

    async def update_tenant(
        self,
        actor: dict[str, Any],
        tenant_id: UUID,
        request: TenantUpdate,
    ) -> Tenant:
        tenant = await self.repository.get_by_id(tenant_id)
        if tenant is None:
            raise TenantNotFoundError()
        self._guard_default_tenant(tenant)
        previous_branding_hash = _stable_hash(tenant.branding_config_json or {})
        values: dict[str, object] = {}
        changed_fields: list[str] = []
        if request.display_name is not None and request.display_name != tenant.display_name:
            values["display_name"] = request.display_name
            changed_fields.append("display_name")
        if request.region is not None and request.region != tenant.region:
            if request.region not in ALLOWED_TENANT_REGIONS:
                raise RegionInvalidError(request.region)
            values["region"] = request.region
            changed_fields.append("region")
        if request.branding_config is not None:
            branding = request.branding_config.model_dump(exclude_none=True)
            if branding != (tenant.branding_config_json or {}):
                values["branding_config_json"] = branding
                changed_fields.append("branding_config")
        if request.contract_metadata is not None:
            values["contract_metadata_json"] = dict(request.contract_metadata)
            changed_fields.append("contract_metadata")
        if request.feature_flags is not None:
            values["feature_flags_json"] = dict(request.feature_flags)
            changed_fields.append("feature_flags")
        if values:
            await self.repository.update(tenant, **values)
        await self.session.commit()
        await self._publish_cache_invalidation(tenant)
        _log_tenant_event("tenant_updated", tenant, changed_fields=changed_fields)
        if "branding_config" in changed_fields:
            await publish_tenant_event(
                producer=self.producer,
                event_type=TenantEventType.branding_updated,
                payload=TenantBrandingUpdatedPayload(
                    tenant_id=tenant.id,
                    fields_changed=changed_fields,
                    previous_hash=previous_branding_hash,
                    new_hash=_stable_hash(tenant.branding_config_json or {}),
                ),
                correlation_ctx=CorrelationContext(correlation_id=uuid4()),
            )
        return tenant

    async def suspend_tenant(self, actor: dict[str, Any], tenant_id: UUID, reason: str) -> Tenant:
        tenant = await self._get_mutable_tenant(tenant_id)
        previous_status = tenant.status
        tenant.status = "suspended"
        tenant.scheduled_deletion_at = None
        await self.session.flush()
        await self._append_lifecycle_audit(
            actor,
            tenant,
            TenantEventType.suspended.value,
            {"reason": reason, "status_before": previous_status, "status_after": tenant.status},
        )
        await self.session.commit()
        await self._publish_cache_invalidation(tenant)
        _log_tenant_event("tenant_suspended", tenant, reason=reason)
        await publish_tenant_event(
            producer=self.producer,
            event_type=TenantEventType.suspended,
            payload=TenantSuspendedPayload(
                tenant_id=tenant.id,
                reason=reason,
                previous_status=previous_status,
            ),
            correlation_ctx=CorrelationContext(correlation_id=uuid4()),
        )
        return tenant

    async def reactivate_tenant(self, actor: dict[str, Any], tenant_id: UUID) -> Tenant:
        tenant = await self._get_mutable_tenant(tenant_id)
        previous_status = tenant.status
        tenant.status = "active"
        tenant.scheduled_deletion_at = None
        await self.session.flush()
        await self._append_lifecycle_audit(
            actor,
            tenant,
            TenantEventType.reactivated.value,
            {"status_before": previous_status, "status_after": tenant.status},
        )
        await self.session.commit()
        await self._publish_cache_invalidation(tenant)
        _log_tenant_event("tenant_reactivated", tenant, previous_status=previous_status)
        await publish_tenant_event(
            producer=self.producer,
            event_type=TenantEventType.reactivated,
            payload=TenantReactivatedPayload(tenant_id=tenant.id, previous_status=previous_status),
            correlation_ctx=CorrelationContext(correlation_id=uuid4()),
        )
        return tenant

    async def schedule_deletion(
        self,
        actor: dict[str, Any],
        tenant_id: UUID,
        request: TenantScheduleDeletion,
    ) -> Tenant:
        actor_id = _actor_id(actor)
        if actor_id is None:
            raise TwoPersonApprovalError(
                "TWO_PERSON_APPROVAL_ACTOR_REQUIRED",
                "A valid actor is required for tenant deletion",
            )
        tenant = await self._get_mutable_tenant(tenant_id)
        await self._consume_deletion_two_pa(actor_id, tenant_id, request.two_pa_token)
        previous_status = tenant.status
        scheduled_deletion_at = datetime.now(UTC) + timedelta(
            hours=self.settings.TENANT_DELETION_GRACE_HOURS
        )
        tenant.status = "pending_deletion"
        tenant.scheduled_deletion_at = scheduled_deletion_at
        await self.session.flush()
        await self._append_lifecycle_audit(
            actor,
            tenant,
            TenantEventType.scheduled_for_deletion.value,
            {
                "reason": request.reason,
                "status_before": previous_status,
                "status_after": tenant.status,
                "scheduled_deletion_at": scheduled_deletion_at.isoformat(),
            },
        )
        await self.session.commit()
        await self._publish_cache_invalidation(tenant)
        _log_tenant_event(
            "tenant_scheduled_for_deletion",
            tenant,
            scheduled_deletion_at=scheduled_deletion_at.isoformat(),
        )
        await publish_tenant_event(
            producer=self.producer,
            event_type=TenantEventType.scheduled_for_deletion,
            payload=TenantScheduledForDeletionPayload(
                tenant_id=tenant.id,
                reason=request.reason,
                scheduled_deletion_at=scheduled_deletion_at,
                grace_period_hours=self.settings.TENANT_DELETION_GRACE_HOURS,
            ),
            correlation_ctx=CorrelationContext(correlation_id=uuid4()),
        )
        return tenant

    async def cancel_deletion(self, actor: dict[str, Any], tenant_id: UUID) -> Tenant:
        tenant = await self._get_mutable_tenant(tenant_id)
        scheduled_deletion_at_was = tenant.scheduled_deletion_at
        tenant.status = "active"
        tenant.scheduled_deletion_at = None
        await self.session.flush()
        await self._append_lifecycle_audit(
            actor,
            tenant,
            TenantEventType.deletion_cancelled.value,
            {
                "scheduled_deletion_at_was": (
                    scheduled_deletion_at_was.isoformat() if scheduled_deletion_at_was else None
                ),
                "status_after": tenant.status,
            },
        )
        await self.session.commit()
        await self._publish_cache_invalidation(tenant)
        _log_tenant_event("tenant_deletion_cancelled", tenant)
        await publish_tenant_event(
            producer=self.producer,
            event_type=TenantEventType.deletion_cancelled,
            payload=TenantDeletionCancelledPayload(
                tenant_id=tenant.id,
                scheduled_deletion_at_was=scheduled_deletion_at_was,
            ),
            correlation_ctx=CorrelationContext(correlation_id=uuid4()),
        )
        return tenant

    async def complete_deletion(self, tenant_id: UUID) -> dict[str, int]:
        tenant = await self.repository.get_by_id(tenant_id)
        if tenant is None:
            raise TenantNotFoundError()
        self._guard_default_tenant(tenant)
        row_count_digest: dict[str, int] = {}
        for name, handler in tenant_cascade_handlers():
            row_count_digest[name] = await handler(self.session, tenant_id)
        tombstone_payload = {
            "tenant_id": str(tenant.id),
            "slug": tenant.slug,
            "cascade_complete": True,
            "row_count_digest": row_count_digest,
        }
        tombstone_sha256 = _stable_hash(tombstone_payload)
        await self._append_lifecycle_audit(
            {"id": None},
            tenant,
            TenantEventType.deleted.value,
            tombstone_payload | {"tombstone_sha256": tombstone_sha256},
        )
        await self.repository.delete(tenant)
        await self.session.commit()
        await self._publish_cache_invalidation(tenant)
        _log_tenant_event(
            "tenant_deleted",
            tenant,
            tombstone_sha256=tombstone_sha256,
            row_count_digest=row_count_digest,
        )
        await publish_tenant_event(
            producer=self.producer,
            event_type=TenantEventType.deleted,
            payload=TenantDeletedPayload(
                tenant_id=tenant_id,
                row_count_digest=row_count_digest,
                cascade_completed_at=datetime.now(UTC),
                tombstone_sha256=tombstone_sha256,
            ),
            correlation_ctx=CorrelationContext(correlation_id=uuid4()),
        )
        return row_count_digest

    async def _validate_create_request(self, request: TenantCreate) -> None:
        if not SLUG_RE.fullmatch(request.slug):
            raise SlugInvalidError(request.slug)
        if request.slug in RESERVED_SLUGS:
            raise ReservedSlugError(request.slug)
        if request.region not in ALLOWED_TENANT_REGIONS:
            raise RegionInvalidError(request.region)
        if await self.repository.get_by_slug(request.slug) is not None:
            raise SlugTakenError(request.slug)
        if await self.repository.get_by_subdomain(request.slug) is not None:
            raise SlugTakenError(request.slug)

    async def _finalize_dpa_artifact(self, request: TenantCreate) -> dict[str, str]:
        if self.object_storage is None:
            raise DPAMissingError()
        pending_key = f"pending/{request.dpa_artifact_id}"
        try:
            payload = await self.object_storage.download_object(TENANT_DPA_BUCKET, pending_key)
        except Exception as exc:
            raise DPAMissingError() from exc
        digest = hashlib.sha256(payload).hexdigest()
        safe_version = _safe_path_piece(request.dpa_version)
        final_key = f"{request.slug}/{safe_version}-signed-dpa.pdf"
        await self.object_storage.create_bucket_if_not_exists(TENANT_DPA_BUCKET)
        await self.object_storage.upload_object(
            TENANT_DPA_BUCKET,
            final_key,
            payload,
            content_type="application/pdf",
            metadata={"sha256": digest, "tenant_slug": request.slug},
        )
        await self.object_storage.delete_object(TENANT_DPA_BUCKET, pending_key)
        return {"uri": f"s3://{TENANT_DPA_BUCKET}/{final_key}", "sha256": digest}

    async def _append_created_audit(
        self,
        actor: dict[str, Any],
        tenant: Tenant,
        request: TenantCreate,
    ) -> None:
        if self.audit_chain is None:
            return
        payload: dict[str, object] = {
            "tenant_id": str(tenant.id),
            "slug": tenant.slug,
            "display_name": tenant.display_name,
            "kind": tenant.kind,
            "status_after": tenant.status,
            "dpa_version": request.dpa_version,
            "actor_user_id": str(_actor_id(actor)) if _actor_id(actor) is not None else None,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        await self.audit_chain.append(
            uuid4(),
            "tenants",
            canonical,
            event_type=TenantEventType.created.value,
            actor_role="super_admin",
            canonical_payload_json=payload,
            tenant_id=tenant.id,
        )

    def _guard_default_tenant(self, tenant: Tenant) -> None:
        if tenant.kind == "default":
            raise DefaultTenantImmutableError()

    async def _get_mutable_tenant(self, tenant_id: UUID) -> Tenant:
        tenant = await self.repository.get_by_id(tenant_id)
        if tenant is None:
            raise TenantNotFoundError()
        self._guard_default_tenant(tenant)
        return tenant

    async def _consume_deletion_two_pa(
        self,
        actor_id: UUID,
        tenant_id: UUID,
        token: str,
    ) -> None:
        challenge, payload = await TwoPersonApprovalService(
            self.session,
            self.redis_client,
        ).consume_challenge(challenge_id=UUID(str(token)), requester_id=actor_id)
        if str(payload.get("tenant_id")) != str(tenant_id):
            raise TwoPersonApprovalError(
                "TWO_PERSON_APPROVAL_TENANT_MISMATCH",
                "2PA token is not bound to this tenant",
            )
        if challenge.action_type not in {
            "tenant_schedule_deletion",
            "tenant_force_cascade_deletion",
        }:
            raise TwoPersonApprovalError(
                "TWO_PERSON_APPROVAL_ACTION_MISMATCH",
                "2PA token is not valid for tenant deletion",
            )

    async def _append_lifecycle_audit(
        self,
        actor: dict[str, Any],
        tenant: Tenant,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        if self.audit_chain is None:
            return
        actor_id = _actor_id(actor)
        canonical_payload = {
            "tenant_id": str(tenant.id),
            "slug": tenant.slug,
            "kind": tenant.kind,
            "actor_user_id": str(actor_id) if actor_id is not None else None,
            **payload,
        }
        canonical = json.dumps(
            canonical_payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        await self.audit_chain.append(
            uuid4(),
            "tenants",
            canonical,
            event_type=event_type,
            actor_role="super_admin",
            canonical_payload_json=canonical_payload,
            tenant_id=tenant.id,
        )

    async def _publish_cache_invalidation(self, tenant: Tenant) -> None:
        if self.redis_client is None:
            return
        hosts = _tenant_cache_hosts(tenant, self.settings.PLATFORM_DOMAIN)
        payload = json.dumps(
            {"tenant_id": str(tenant.id), "hosts": hosts},
            separators=(",", ":"),
        )
        for host in hosts:
            await self.redis_client.delete(f"tenants:resolve:{host}")
        try:
            await self.redis_client.initialize()
            client = self.redis_client.client
            if client is not None:
                await cast(Any, client).publish(TENANT_INVALIDATION_CHANNEL, payload)
        except Exception:
            return


def _actor_id(actor: dict[str, Any]) -> UUID | None:
    value = actor.get("sub") or actor.get("id") or actor.get("user_id")
    if value is None:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        return None


def _safe_path_piece(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-") or "dpa"


def _stable_hash(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _tenant_cache_hosts(tenant: Tenant, platform_domain: str) -> list[str]:
    domain = platform_domain.strip().lower().rstrip(".")
    if tenant.kind == "default":
        return [domain, f"app.{domain}", f"api.{domain}", f"grafana.{domain}"]
    return [
        f"{tenant.subdomain}.{domain}",
        f"{tenant.subdomain}.api.{domain}",
        f"{tenant.subdomain}.grafana.{domain}",
    ]


def _log_tenant_event(event: str, tenant: Tenant, **fields: object) -> None:
    LOGGER.info(
        event,
        tenant_id=str(tenant.id),
        tenant_slug=tenant.slug,
        tenant_kind=tenant.kind,
        **fields,
    )
