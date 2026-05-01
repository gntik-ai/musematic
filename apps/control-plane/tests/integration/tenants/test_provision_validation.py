from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.tenants.dns_automation import MockDnsAutomationClient
from platform.tenants.exceptions import (
    DPAMissingError,
    RegionInvalidError,
    ReservedSlugError,
    SlugTakenError,
)
from platform.tenants.repository import TenantsRepository
from platform.tenants.schemas import TenantCreate
from platform.tenants.service import TenantsService

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from tests.integration.tenants.test_provision_enterprise import (
    FakeNotifications,
    FakeObjectStorage,
    FakeProducer,
)


def _request(slug: str = "acme", region: str = "eu-central") -> TenantCreate:
    return TenantCreate(
        slug=slug,
        display_name="Acme Corp",
        region=region,
        first_admin_email="cto@acme.com",
        dpa_artifact_id=f"{slug}.pdf",
        dpa_version="v3",
    )


async def _service(integration_session, storage: FakeObjectStorage) -> TenantsService:
    return TenantsService(
        session=integration_session,
        repository=TenantsRepository(integration_session),
        settings=PlatformSettings(PLATFORM_DOMAIN="musematic.ai"),
        producer=FakeProducer(),  # type: ignore[arg-type]
        audit_chain=None,
        dns_automation=MockDnsAutomationClient(),
        notifications=FakeNotifications(),
        object_storage=storage,  # type: ignore[arg-type]
    )


async def test_reserved_slug_rejected_by_service_and_database_trigger(
    integration_session,
) -> None:
    storage = FakeObjectStorage()
    await storage.upload_object("tenant-dpas", "pending/admin.pdf", b"signed dpa")
    service = await _service(integration_session, storage)

    with pytest.raises(ReservedSlugError):
        await service.provision_enterprise_tenant({"sub": "actor"}, _request(slug="admin"))

    with pytest.raises(IntegrityError):
        await _insert_reserved_slug_directly(integration_session)
    await integration_session.rollback()


async def test_duplicate_slug_returns_conflict(integration_session) -> None:
    storage = FakeObjectStorage()
    await storage.upload_object("tenant-dpas", "pending/acme.pdf", b"signed dpa")
    await storage.upload_object("tenant-dpas", "pending/acme-2.pdf", b"signed dpa")
    service = await _service(integration_session, storage)
    await service.provision_enterprise_tenant({"sub": "actor"}, _request())

    duplicate = _request()
    duplicate.dpa_artifact_id = "acme-2.pdf"
    with pytest.raises(SlugTakenError):
        await service.provision_enterprise_tenant({"sub": "actor"}, duplicate)


async def test_invalid_region_returns_validation_error(integration_session) -> None:
    storage = FakeObjectStorage()
    await storage.upload_object("tenant-dpas", "pending/acme.pdf", b"signed dpa")
    service = await _service(integration_session, storage)

    with pytest.raises(RegionInvalidError):
        await service.provision_enterprise_tenant(
            {"sub": "actor"},
            _request(region="moon-base"),
        )


async def test_missing_dpa_returns_validation_error(integration_session) -> None:
    service = await _service(integration_session, FakeObjectStorage())

    with pytest.raises(DPAMissingError):
        await service.provision_enterprise_tenant({"sub": "actor"}, _request())


async def _insert_reserved_slug_directly(integration_session) -> None:
    await integration_session.execute(
        text(
            """
            INSERT INTO tenants (
                slug,
                kind,
                subdomain,
                display_name,
                region
            )
            VALUES ('admin', 'enterprise', 'admin-direct', 'Admin Direct', 'eu-central')
            """
        )
    )
    await integration_session.flush()
