from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

import platform.tenants.service as service_module
from platform.common.config import PlatformSettings
from platform.tenants.exceptions import (
    DPAMissingError,
    RegionInvalidError,
    ReservedSlugError,
    SlugTakenError,
    TenantNotFoundError,
)
from platform.tenants.models import Tenant
from platform.tenants.schemas import (
    TenantBranding,
    TenantCreate,
    TenantScheduleDeletion,
    TenantUpdate,
)
from platform.tenants.service import TENANT_DPA_BUCKET, TenantsService
from tests.auth_support import RecordingProducer


class SessionStub:
    def __init__(self) -> None:
        self.commits = 0
        self.flushes = 0

    async def commit(self) -> None:
        self.commits += 1

    async def flush(self) -> None:
        self.flushes += 1


class RepositoryStub:
    def __init__(self) -> None:
        self.by_id: dict[UUID, Tenant] = {}
        self.by_slug: dict[str, Tenant] = {}
        self.by_subdomain: dict[str, Tenant] = {}
        self.created: list[Tenant] = []
        self.updated: list[tuple[Tenant, dict[str, object]]] = []
        self.deleted: list[Tenant] = []

    async def create(self, tenant: Tenant) -> Tenant:
        tenant.id = getattr(tenant, "id", None) or uuid4()
        tenant.created_at = getattr(tenant, "created_at", None) or datetime.now(UTC)
        tenant.updated_at = getattr(tenant, "updated_at", None) or tenant.created_at
        self.created.append(tenant)
        self.by_id[tenant.id] = tenant
        self.by_slug[tenant.slug] = tenant
        self.by_subdomain[tenant.subdomain] = tenant
        return tenant

    async def get_by_id(self, tenant_id: UUID) -> Tenant | None:
        return self.by_id.get(tenant_id)

    async def get_by_slug(self, slug: str) -> Tenant | None:
        return self.by_slug.get(slug)

    async def get_by_subdomain(self, subdomain: str) -> Tenant | None:
        return self.by_subdomain.get(subdomain)

    async def update(self, tenant: Tenant, **values: object) -> Tenant:
        self.updated.append((tenant, dict(values)))
        for key, value in values.items():
            setattr(tenant, key, value)
        return tenant

    async def delete(self, tenant: Tenant) -> None:
        self.deleted.append(tenant)
        self.by_id.pop(tenant.id, None)


class ObjectStorageStub:
    def __init__(self, payload: bytes = b"signed dpa") -> None:
        self.payload = payload
        self.uploads: list[tuple[str, str, bytes, str, dict[str, str] | None]] = []
        self.deleted: list[tuple[str, str]] = []
        self.buckets: list[str] = []

    async def create_bucket_if_not_exists(self, bucket: str) -> None:
        self.buckets.append(bucket)

    async def upload_object(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> None:
        self.uploads.append((bucket, key, data, content_type, metadata))

    async def download_object(self, bucket: str, key: str) -> bytes:
        if bucket != TENANT_DPA_BUCKET or not key.startswith("pending/"):
            raise FileNotFoundError(key)
        return self.payload

    async def delete_object(self, bucket: str, key: str) -> None:
        self.deleted.append((bucket, key))


class DnsStub:
    def __init__(self) -> None:
        self.requests: list[str] = []

    async def ensure_records(self, subdomain: str) -> None:
        self.requests.append(subdomain)


class NotificationsStub:
    def __init__(self) -> None:
        self.invites: list[tuple[str, str]] = []

    async def send_first_admin_invitation(self, tenant: Tenant, email: str) -> str:
        self.invites.append((tenant.slug, email))
        return "invite-token"


class AuditChainStub:
    def __init__(self) -> None:
        self.entries: list[dict[str, object]] = []

    async def append(self, *_args: object, **kwargs: object) -> None:
        self.entries.append(kwargs)


class RedisPubSubStub:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel: str, payload: str) -> None:
        self.published.append((channel, payload))


class RedisStub:
    def __init__(self) -> None:
        self.client = RedisPubSubStub()
        self.deleted: list[str] = []
        self.initialized = False

    async def delete(self, key: str) -> None:
        self.deleted.append(key)

    async def initialize(self) -> None:
        self.initialized = True


def _tenant(**overrides: object) -> Tenant:
    now = datetime.now(UTC)
    payload: dict[str, object] = {
        "id": uuid4(),
        "slug": "acme",
        "kind": "enterprise",
        "subdomain": "acme",
        "display_name": "Acme",
        "region": "eu-central",
        "data_isolation_mode": "pool",
        "branding_config_json": {},
        "status": "active",
        "created_at": now,
        "updated_at": now,
        "created_by_super_admin_id": uuid4(),
        "dpa_signed_at": now,
        "dpa_version": "v1",
        "dpa_artifact_uri": "s3://tenant-dpas/acme/v1-signed-dpa.pdf",
        "dpa_artifact_sha256": "abc123",
        "contract_metadata_json": {},
        "feature_flags_json": {},
    }
    payload.update(overrides)
    return Tenant(**payload)


def _create_request(slug: str = "acme") -> TenantCreate:
    return TenantCreate(
        slug=slug,
        display_name="Acme Corp",
        region="eu-central",
        first_admin_email="admin@example.com",
        dpa_artifact_id="pending-dpa.pdf",
        dpa_version="v 1/signed",
        contract_metadata={"msa": "2026"},
        branding_config=TenantBranding(accent_color_hex="#123456"),
    )


def _service(
    *,
    repo: RepositoryStub | None = None,
    session: SessionStub | None = None,
    object_storage: ObjectStorageStub | None = None,
    producer: RecordingProducer | None = None,
    audit: AuditChainStub | None = None,
    redis: RedisStub | None = None,
) -> tuple[TenantsService, RepositoryStub, SessionStub, RecordingProducer, AuditChainStub, RedisStub]:
    resolved_repo = repo or RepositoryStub()
    resolved_session = session or SessionStub()
    resolved_producer = producer or RecordingProducer()
    resolved_audit = audit or AuditChainStub()
    resolved_redis = redis or RedisStub()
    return (
        TenantsService(
            session=resolved_session,  # type: ignore[arg-type]
            repository=resolved_repo,  # type: ignore[arg-type]
            settings=PlatformSettings(),
            producer=resolved_producer,
            audit_chain=resolved_audit,  # type: ignore[arg-type]
            dns_automation=DnsStub(),
            notifications=NotificationsStub(),
            object_storage=object_storage or ObjectStorageStub(),
            redis_client=resolved_redis,  # type: ignore[arg-type]
        ),
        resolved_repo,
        resolved_session,
        resolved_producer,
        resolved_audit,
        resolved_redis,
    )


@pytest.mark.asyncio
async def test_provision_enterprise_tenant_finalizes_dpa_and_emits_audit() -> None:
    service, repo, session, producer, audit, _redis = _service()
    actor_id = uuid4()

    tenant = await service.provision_enterprise_tenant(
        {"sub": str(actor_id)},
        _create_request(),
    )

    assert tenant.slug == "acme"
    assert tenant.dpa_artifact_uri == "s3://tenant-dpas/acme/v-1-signed-signed-dpa.pdf"
    assert repo.created == [tenant]
    assert session.commits == 1
    assert audit.entries[0]["event_type"] == "tenants.created"
    assert producer.events[-1]["event_type"] == "tenants.created"


@pytest.mark.asyncio
async def test_provision_enterprise_tenant_rejects_invalid_inputs() -> None:
    repo = RepositoryStub()
    repo.by_slug["taken"] = _tenant(slug="taken", subdomain="taken")
    service, *_ = _service(repo=repo)

    with pytest.raises(ReservedSlugError):
        await service.provision_enterprise_tenant({"sub": str(uuid4())}, _create_request("admin"))
    with pytest.raises(RegionInvalidError):
        request = _create_request("newco")
        request.region = "antarctica"
        await service.provision_enterprise_tenant({"sub": str(uuid4())}, request)
    with pytest.raises(SlugTakenError):
        await service.provision_enterprise_tenant({"sub": str(uuid4())}, _create_request("taken"))

    service_without_storage, *_ = _service(object_storage=None)
    service_without_storage.object_storage = None
    with pytest.raises(DPAMissingError):
        await service_without_storage.provision_enterprise_tenant(
            {"sub": str(uuid4())},
            _create_request("nostorage"),
        )


@pytest.mark.asyncio
async def test_update_and_lifecycle_methods_emit_events_and_invalidate_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = _tenant(branding_config_json={"accent_color_hex": "#000000"})
    repo = RepositoryStub()
    repo.by_id[tenant.id] = tenant
    service, _repo, session, producer, audit, redis = _service(repo=repo)

    updated = await service.update_tenant(
        {"sub": str(uuid4())},
        tenant.id,
        TenantUpdate(
            display_name="Acme Updated",
            region="us-east",
            branding_config=TenantBranding(accent_color_hex="#ffffff"),
            contract_metadata={"msa": "updated"},
            feature_flags={"beta": True},
        ),
    )
    assert updated.display_name == "Acme Updated"
    assert repo.updated[-1][1]["region"] == "us-east"
    assert producer.events[-1]["event_type"] == "tenants.branding_updated"
    assert redis.deleted

    suspended = await service.suspend_tenant({"sub": str(uuid4())}, tenant.id, "billing")
    assert suspended.status == "suspended"
    reactivated = await service.reactivate_tenant({"sub": str(uuid4())}, tenant.id)
    assert reactivated.status == "active"

    class TwoPersonApprovalStub:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def consume_challenge(self, **_kwargs: object):
            return (
                SimpleNamespace(action_type="tenant_schedule_deletion"),
                {"tenant_id": str(tenant.id)},
            )

    monkeypatch.setattr(service_module, "TwoPersonApprovalService", TwoPersonApprovalStub)
    scheduled = await service.schedule_deletion(
        {"sub": str(uuid4())},
        tenant.id,
        TenantScheduleDeletion(reason="contract ended", two_pa_token=str(uuid4())),
    )
    assert scheduled.status == "pending_deletion"
    assert scheduled.scheduled_deletion_at is not None

    cancelled = await service.cancel_deletion({"sub": str(uuid4())}, tenant.id)
    assert cancelled.status == "active"
    assert cancelled.scheduled_deletion_at is None

    async def cascade_a(_session: object, _tenant_id: UUID) -> int:
        return 2

    async def cascade_b(_session: object, _tenant_id: UUID) -> int:
        return 3

    monkeypatch.setattr(
        service_module,
        "tenant_cascade_handlers",
        lambda: (("workspaces", cascade_a), ("users", cascade_b)),
    )
    digest = await service.complete_deletion(tenant.id)
    assert digest == {"workspaces": 2, "users": 3}
    assert repo.deleted == [tenant]
    assert audit.entries[-1]["event_type"] == "tenants.deleted"
    assert session.flushes == 4


@pytest.mark.asyncio
async def test_lifecycle_helpers_reject_missing_and_default_tenants() -> None:
    default = _tenant(kind="default", slug="default", subdomain="app")
    repo = RepositoryStub()
    repo.by_id[default.id] = default
    service, *_ = _service(repo=repo)

    with pytest.raises(TenantNotFoundError):
        await service.update_tenant({"sub": str(uuid4())}, uuid4(), TenantUpdate())
    with pytest.raises(Exception, match="default tenant"):
        await service.suspend_tenant({"sub": str(uuid4())}, default.id, "nope")


@pytest.mark.asyncio
async def test_update_noop_and_two_person_approval_error_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = _tenant()
    repo = RepositoryStub()
    repo.by_id[tenant.id] = tenant
    service, _repo, session, producer, _audit, _redis = _service(repo=repo)

    unchanged = await service.update_tenant({"sub": str(uuid4())}, tenant.id, TenantUpdate())
    assert unchanged is tenant
    assert repo.updated == []
    assert producer.events == []

    with pytest.raises(RegionInvalidError):
        await service.update_tenant(
            {"sub": str(uuid4())},
            tenant.id,
            TenantUpdate(region="antarctica"),
        )

    with pytest.raises(Exception, match="valid actor"):
        await service.schedule_deletion(
            {},
            tenant.id,
            TenantScheduleDeletion(reason="done", two_pa_token=str(uuid4())),
        )

    class MismatchTwoPersonApprovalStub:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def consume_challenge(self, **_kwargs: object):
            return (
                SimpleNamespace(action_type="workspace_delete"),
                {"tenant_id": str(uuid4())},
            )

    monkeypatch.setattr(
        service_module,
        "TwoPersonApprovalService",
        MismatchTwoPersonApprovalStub,
    )
    with pytest.raises(Exception, match="not bound"):
        await service.schedule_deletion(
            {"sub": str(uuid4())},
            tenant.id,
            TenantScheduleDeletion(reason="done", two_pa_token=str(uuid4())),
        )

    class WrongActionTwoPersonApprovalStub:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def consume_challenge(self, **_kwargs: object):
            return (
                SimpleNamespace(action_type="workspace_delete"),
                {"tenant_id": str(tenant.id)},
            )

    monkeypatch.setattr(
        service_module,
        "TwoPersonApprovalService",
        WrongActionTwoPersonApprovalStub,
    )
    with pytest.raises(Exception, match="not valid"):
        await service.schedule_deletion(
            {"sub": str(uuid4())},
            tenant.id,
            TenantScheduleDeletion(reason="done", two_pa_token=str(uuid4())),
        )

    assert session.commits == 1
