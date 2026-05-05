from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest

import platform.tenants.jobs.deletion_grace as deletion_grace
import platform.tenants.dns_automation as dns_automation
import platform.tenants.platform_router as platform_router
from platform.common.config import PlatformSettings
from platform.common.exceptions import PlatformError, ValidationError
from platform.tenants import admin_router
from platform.tenants.cascade import (
    delete_catalogued_rows,
    register_tenant_cascade_handler,
    tenant_cascade_handlers,
)
from platform.tenants.dns_automation import (
    HetznerDnsAutomationClient,
    MockDnsAutomationClient,
    build_dns_automation_client,
)
from platform.tenants.models import Tenant
from platform.tenants.service import TENANT_DPA_BUCKET
from platform.tenants.schemas import (
    TenantCreate,
    TenantScheduleDeletion,
    TenantSuspend,
    TenantUpdate,
)


def _request(state: object) -> SimpleNamespace:
    return SimpleNamespace(app=SimpleNamespace(state=state))


def _tenant() -> Tenant:
    now = datetime.now(UTC)
    return Tenant(
        id=uuid4(),
        slug="acme",
        kind="enterprise",
        subdomain="acme",
        display_name="Acme",
        region="eu-central",
        data_isolation_mode="pool",
        branding_config_json={"accent_color_hex": "#123456"},
        status="active",
        created_at=now,
        updated_at=now,
        dpa_signed_at=now,
        dpa_version="v1",
        dpa_artifact_uri="s3://tenant-dpas/acme/v1.pdf",
        dpa_artifact_sha256="abc",
        contract_metadata_json={"msa": "2026"},
        feature_flags_json={"beta": True},
    )


class UploadFileStub:
    filename = "signed.pdf"
    content_type = "application/pdf"

    async def read(self) -> bytes:
        return b"pdf"


class ObjectStorageStub:
    def __init__(self) -> None:
        self.buckets: list[str] = []
        self.uploads: list[tuple[str, str, bytes, str, dict[str, str] | None]] = []

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


def test_admin_helpers_render_tenant_and_validate_request_state() -> None:
    storage = ObjectStorageStub()
    state = SimpleNamespace(
        settings=PlatformSettings(),
        clients={"object_storage": storage},
    )
    request = _request(state)

    view = admin_router._admin_view(_tenant())

    assert view.slug == "acme"
    assert view.branding.accent_color_hex == "#123456"
    assert admin_router._settings(request).profile == "api"
    assert admin_router._object_storage(request) is storage
    assert admin_router._coerce_uuid(str(view.id)) == view.id
    with pytest.raises(ValidationError):
        admin_router._coerce_uuid("not-a-uuid")


@pytest.mark.asyncio
async def test_upload_dpa_stores_pending_artifact_and_rejects_missing_storage() -> None:
    storage = ObjectStorageStub()
    request = _request(SimpleNamespace(clients={"object_storage": storage}))

    response = await admin_router.upload_dpa(
        request,  # type: ignore[arg-type]
        file=UploadFileStub(),  # type: ignore[arg-type]
        _current_user={"roles": [{"role": "superadmin"}]},
    )

    assert response.dpa_artifact_id.endswith(".pdf")
    assert storage.buckets == [TENANT_DPA_BUCKET]
    assert storage.uploads[0][1].startswith("pending/")

    with pytest.raises(PlatformError):
        await admin_router.upload_dpa(
            _request(SimpleNamespace(clients={})),  # type: ignore[arg-type]
            file=UploadFileStub(),  # type: ignore[arg-type]
            _current_user={"roles": [{"role": "superadmin"}]},
        )


@pytest.mark.asyncio
async def test_admin_tenant_endpoints_delegate_to_repository_and_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = _tenant()

    class RepositoryStub:
        def __init__(self, _session: object) -> None:
            return None

        async def list_all(self, **kwargs: object):
            assert kwargs["kind"] == "enterprise"
            return [tenant]

        async def get_by_id(self, tenant_id: object):
            assert tenant_id == tenant.id
            return tenant

    class ServiceStub:
        async def provision_enterprise_tenant(self, _user: object, _payload: object):
            return tenant

        async def update_tenant(self, _user: object, _tenant_id: object, _payload: object):
            return tenant

        async def suspend_tenant(self, _user: object, _tenant_id: object, _reason: str):
            return tenant

        async def reactivate_tenant(self, _user: object, _tenant_id: object):
            return tenant

        async def schedule_deletion(self, _user: object, _tenant_id: object, _payload: object):
            return tenant

        async def cancel_deletion(self, _user: object, _tenant_id: object):
            return tenant

    request = _request(SimpleNamespace(settings=PlatformSettings(), clients={}))
    monkeypatch.setattr(admin_router, "TenantsRepository", RepositoryStub)
    monkeypatch.setattr(admin_router, "_service", lambda _request, _session: ServiceStub())

    listed = await admin_router.list_tenants(
        kind="enterprise",
        status=None,
        q=None,
        limit=10,
        _current_user={},
        session=object(),  # type: ignore[arg-type]
    )
    assert listed.items[0].slug == "acme"
    assert (await admin_router.get_tenant(str(tenant.id), {}, object())).slug == "acme"  # type: ignore[arg-type]

    provisioned = await admin_router.provision_tenant(
        TenantCreate(
            slug="acme",
            display_name="Acme",
            region="eu-central",
            first_admin_email="admin@example.com",
            dpa_artifact_id="artifact.pdf",
            dpa_version="v1",
        ),
        request,  # type: ignore[arg-type]
        {},
        object(),  # type: ignore[arg-type]
    )
    assert provisioned.first_admin_invite_sent_to == "admin@example.com"
    assert (await admin_router.update_tenant(str(tenant.id), TenantUpdate(), request, {}, object())).slug == "acme"  # type: ignore[arg-type]
    assert (await admin_router.suspend_tenant(str(tenant.id), TenantSuspend(reason="risk"), request, {}, object())).slug == "acme"  # type: ignore[arg-type]
    assert (await admin_router.reactivate_tenant(str(tenant.id), request, {}, object())).slug == "acme"  # type: ignore[arg-type]
    assert (
        await admin_router.schedule_tenant_deletion(
            str(tenant.id),
            TenantScheduleDeletion(reason="done", two_pa_token=str(uuid4())),
            request,  # type: ignore[arg-type]
            {},
            object(),  # type: ignore[arg-type]
        )
    ).slug == "acme"
    assert (await admin_router.cancel_tenant_deletion(str(tenant.id), request, {}, object())).slug == "acme"  # type: ignore[arg-type]


def test_dns_automation_builder_selects_provider_from_settings() -> None:
    assert isinstance(build_dns_automation_client(PlatformSettings()), MockDnsAutomationClient)

    settings = SimpleNamespace(
        profile="production",
        HETZNER_DNS_API_TOKEN="token",
        HETZNER_DNS_ZONE_ID="zone",
        TENANT_DNS_IPV4_ADDRESS="192.0.2.10",
        TENANT_DNS_IPV6_ADDRESS="2001:db8::10",
    )

    client = build_dns_automation_client(settings)

    assert isinstance(client, HetznerDnsAutomationClient)
    assert client.ipv6_address == "2001:db8::10"


@pytest.mark.asyncio
async def test_mock_dns_client_records_requests() -> None:
    client = MockDnsAutomationClient()

    await client.ensure_records("acme")

    assert client.requests == ["acme"]


@pytest.mark.asyncio
async def test_hetzner_dns_client_posts_a_and_aaaa_records(monkeypatch: pytest.MonkeyPatch) -> None:
    """UPD-053 (106) — ``ensure_records`` is now a thin facade for
    ``create_tenant_subdomain``, which posts the full 6-record bundle
    (3 subdomains x {A, AAAA}). The test asserts both record types are
    written and that the 6 calls land against the Hetzner DNS API.
    """
    posts: list[dict[str, object]] = []

    class ResponseStub:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"record": {"id": f"rec-{len(posts)}"}}

    class AsyncClientStub:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def __aenter__(self) -> "AsyncClientStub":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def post(self, url: str, **kwargs: object) -> ResponseStub:
            posts.append({"url": url, "json": kwargs.get("json", {})})
            return ResponseStub()

    monkeypatch.setattr(dns_automation.httpx, "AsyncClient", AsyncClientStub)
    monkeypatch.setattr(
        "platform.tenants.dns_automation._resolve_via",
        lambda host, resolver: ["192.0.2.10"],
    )
    client = HetznerDnsAutomationClient(
        settings=PlatformSettings(),
        api_token="token",
        zone_id="zone",
        ipv4_address="192.0.2.10",
        ipv6_address="2001:db8::10",
    )

    await client.ensure_records("acme")

    record_types = {cast("dict[str, object]", post["json"])["type"] for post in posts}
    assert record_types == {"A", "AAAA"}
    assert len(posts) == 6  # 3 subdomains x {A, AAAA}


def test_service_factories_build_with_request_state() -> None:
    storage = ObjectStorageStub()
    state = SimpleNamespace(
        settings=PlatformSettings(),
        clients={"object_storage": storage, "redis": object(), "kafka": object()},
    )
    request = _request(state)

    assert admin_router._service(request, object()).object_storage is storage  # type: ignore[arg-type]
    assert platform_router._service(request, object()).object_storage is storage  # type: ignore[arg-type]


class CascadeResult:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


class CascadeSessionStub:
    def __init__(self) -> None:
        self.scalar_calls = 0
        self.executed: list[str] = []

    async def scalar(self, *_args: object, **_kwargs: object) -> bool:
        self.scalar_calls += 1
        return self.scalar_calls % 2 == 1

    async def execute(self, statement: object, _params: object) -> CascadeResult:
        self.executed.append(str(statement))
        return CascadeResult(4)


@pytest.mark.asyncio
async def test_delete_catalogued_rows_skips_missing_tables_and_quotes_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "platform.tenants.cascade.TENANT_SCOPED_TABLES",
        ("missing_table", 'needs"quote'),
    )
    session = CascadeSessionStub()

    deleted = await delete_catalogued_rows(session, uuid4())  # type: ignore[arg-type]

    assert deleted == 4
    assert 'needs""quote' in session.executed[0]


def test_tenant_cascade_handler_registration_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    async def handler(_session: object, _tenant_id: object) -> int:
        return 0

    monkeypatch.setattr("platform.tenants.cascade._HANDLERS", [])

    register_tenant_cascade_handler("custom", handler)  # type: ignore[arg-type]
    register_tenant_cascade_handler("custom", handler)  # type: ignore[arg-type]

    assert tenant_cascade_handlers() == (("custom", handler),)


class GraceResult:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def scalars(self) -> GraceResult:
        return self

    def all(self) -> list[object]:
        return self.rows


class GraceSessionStub:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows
        self.rollbacks = 0

    async def __aenter__(self) -> GraceSessionStub:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def execute(self, *_args: object, **_kwargs: object) -> GraceResult:
        return GraceResult(self.rows)

    async def rollback(self) -> None:
        self.rollbacks += 1


@pytest.mark.asyncio
async def test_deletion_grace_scan_completes_rows_and_rolls_back_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_ok = uuid4()
    tenant_fail = uuid4()
    session = GraceSessionStub([tenant_ok, tenant_fail])
    completed: list[object] = []

    class ServiceStub:
        def __init__(self, **_kwargs: object) -> None:
            return None

        async def complete_deletion(self, tenant_id: object) -> None:
            if tenant_id == tenant_fail:
                raise RuntimeError("cascade failed")
            completed.append(tenant_id)

    monkeypatch.setattr(
        deletion_grace.database,
        "PlatformStaffAsyncSessionLocal",
        lambda: session,
    )
    monkeypatch.setattr(deletion_grace, "TenantsService", ServiceStub)

    count = await deletion_grace.run_tenant_deletion_grace_scan(
        SimpleNamespace(state=SimpleNamespace(settings=PlatformSettings(), clients={})),
    )

    assert count == 1
    assert completed == [tenant_ok]
    assert session.rollbacks == 1


@pytest.mark.asyncio
async def test_deletion_grace_scan_returns_zero_when_no_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        deletion_grace.database,
        "PlatformStaffAsyncSessionLocal",
        lambda: GraceSessionStub([]),
    )

    count = await deletion_grace.run_tenant_deletion_grace_scan(
        SimpleNamespace(state=SimpleNamespace(settings=PlatformSettings(), clients={})),
    )

    assert count == 0


def test_deletion_grace_scheduler_builds_job(monkeypatch: pytest.MonkeyPatch) -> None:
    jobs: list[tuple[object, str, dict[str, object]]] = []

    class SchedulerStub:
        def __init__(self, timezone: str) -> None:
            self.timezone = timezone

        def add_job(self, func: object, trigger: str, **kwargs: object) -> None:
            jobs.append((func, trigger, kwargs))

    monkeypatch.setitem(
        __import__("sys").modules,
        "apscheduler.schedulers.asyncio",
        SimpleNamespace(AsyncIOScheduler=SchedulerStub),
    )

    scheduler = deletion_grace.build_tenant_deletion_scheduler(SimpleNamespace())

    assert isinstance(scheduler, SchedulerStub)
    assert jobs[0][1] == "interval"
    assert jobs[0][2]["id"] == "tenants-deletion-grace-scan"
