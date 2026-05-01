from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from platform.audit.service import AuditChainService
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.tenants.dns_automation import DnsAutomationClient
from platform.tenants.events import (
    TenantCreatedPayload,
    TenantEventType,
    publish_tenant_event,
)
from platform.tenants.exceptions import (
    DPAMissingError,
    RegionInvalidError,
    ReservedSlugError,
    SlugInvalidError,
    SlugTakenError,
)
from platform.tenants.models import Tenant
from platform.tenants.repository import TenantsRepository
from platform.tenants.reserved_slugs import RESERVED_SLUGS
from platform.tenants.schemas import SLUG_RE, TenantCreate
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

TENANT_DPA_BUCKET = "tenant-dpas"
ALLOWED_TENANT_REGIONS = frozenset({"global", "eu-central", "us-east", "us-west"})


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
    ) -> None:
        self.session = session
        self.repository = repository
        self.settings = settings
        self.producer = producer
        self.audit_chain = audit_chain
        self.dns_automation = dns_automation
        self.notifications = notifications
        self.object_storage = object_storage

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
