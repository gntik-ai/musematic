from __future__ import annotations

from platform.audit.repository import AuditChainRepository
from platform.audit.service import AuditChainService
from platform.common.config import PlatformSettings
from platform.tenants.dns_automation import MockDnsAutomationClient
from platform.tenants.repository import TenantsRepository
from platform.tenants.schemas import TenantCreate
from platform.tenants.seeder import DEFAULT_TENANT_ID
from platform.tenants.service import TenantsService

from sqlalchemy import text


class FakeProducer:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    async def publish(self, **payload: object) -> None:
        self.messages.append(payload)


class FakeObjectStorage:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    async def create_bucket_if_not_exists(self, bucket: str) -> None:
        self.objects.setdefault((bucket, ".bucket"), b"")

    async def upload_object(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> None:
        del content_type, metadata
        self.objects[(bucket, key)] = data

    async def download_object(self, bucket: str, key: str) -> bytes:
        return self.objects[(bucket, key)]

    async def delete_object(self, bucket: str, key: str) -> None:
        self.objects.pop((bucket, key), None)


class FakeNotifications:
    def __init__(self) -> None:
        self.invites: list[tuple[str, str]] = []

    async def send_first_admin_invitation(self, tenant, email: str) -> str:
        self.invites.append((tenant.slug, email))
        return f"https://{tenant.subdomain}.musematic.ai/setup?token=fake"


async def test_provision_enterprise_happy_path(integration_session) -> None:
    actor_id = "00000000-0000-0000-0000-000000000111"
    await integration_session.execute(
        text(
            """
            INSERT INTO users (id, email, display_name, status, tenant_id)
            VALUES (
                :actor_id,
                'superadmin@example.com',
                'Super Admin',
                'active',
                :tenant_id
            )
            """
        ),
        {"actor_id": actor_id, "tenant_id": DEFAULT_TENANT_ID},
    )
    storage = FakeObjectStorage()
    await storage.upload_object("tenant-dpas", "pending/dpa-acme.pdf", b"signed dpa")
    producer = FakeProducer()
    notifications = FakeNotifications()
    dns = MockDnsAutomationClient()
    service = TenantsService(
        session=integration_session,
        repository=TenantsRepository(integration_session),
        settings=PlatformSettings(PLATFORM_DOMAIN="musematic.ai"),
        producer=producer,  # type: ignore[arg-type]
        audit_chain=AuditChainService(
            AuditChainRepository(integration_session),
            PlatformSettings(),
            producer=None,
        ),
        dns_automation=dns,
        notifications=notifications,
        object_storage=storage,  # type: ignore[arg-type]
    )

    tenant = await service.provision_enterprise_tenant(
        {"sub": actor_id, "roles": ["superadmin"]},
        TenantCreate(
            slug="acme",
            display_name="Acme Corp",
            region="eu-central",
            first_admin_email="cto@acme.com",
            dpa_artifact_id="dpa-acme.pdf",
            dpa_version="v3-2026-01",
            contract_metadata={"contract_number": "ACME-2026-001"},
            branding_config={"accent_color_hex": "#0078d4"},
        ),
    )

    assert tenant.slug == "acme"
    assert tenant.status == "active"
    assert tenant.dpa_artifact_sha256 is not None
    assert ("tenant-dpas", "pending/dpa-acme.pdf") not in storage.objects
    assert ("tenant-dpas", f"acme/{tenant.dpa_version}-signed-dpa.pdf") in storage.objects
    assert dns.requests == ["acme"]
    assert notifications.invites == [("acme", "cto@acme.com")]
    assert producer.messages[0]["topic"] == "tenants.lifecycle"
    assert producer.messages[0]["event_type"] == "tenants.created"

    audit_count = await integration_session.scalar(
        text(
            """
            SELECT COUNT(*)
            FROM audit_chain_entries
            WHERE tenant_id = :tenant_id
              AND event_type = 'tenants.created'
            """
        ),
        {"tenant_id": tenant.id},
    )
    assert audit_count == 1
