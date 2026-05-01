from __future__ import annotations

from platform.tenants.exceptions import DefaultTenantImmutableError
from platform.tenants.service import TenantsService
from types import SimpleNamespace
from uuid import UUID

import pytest

pytestmark = pytest.mark.integration


def test_application_guard_refuses_default_tenant_mutation() -> None:
    service = TenantsService.__new__(TenantsService)
    tenant = SimpleNamespace(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        kind="default",
        slug="default",
    )

    with pytest.raises(DefaultTenantImmutableError):
        service._guard_default_tenant(tenant)
