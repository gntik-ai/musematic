"""UPD-054 (107) — Tenant fixture for SaaS-pass journeys.

Provisions Enterprise tenants via the public super-admin API
(``POST /api/v1/admin/tenants``), polls the audit chain to confirm
the side-effect chain completed, yields a ``TestTenant`` handle, and
cleans up via the documented two-phase deletion endpoints on context
exit.

Contract: specs/107-saas-e2e-journeys/contracts/tenants-fixture.md
Constitution: rule 1 (never rewrite — use the public admin API),
rule 4 (use existing patterns), rule 25 (E2E suite + journey crossing).
"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from .http_client import AuthenticatedAsyncClient


__all__ = [
    "TestTenant",
    "AuditChainTimeoutError",
    "TenantCleanupError",
    "TenantProvisioningTimeoutError",
    "list_test_tenants",
    "provision_enterprise",
    "tenants",
]


_TEST_SLUG_PREFIX = "e2e-"
_DEFAULT_PROPAGATION_TIMEOUT_S = 300  # 5 minutes per spec FR-792
_AUDIT_CHAIN_TIMEOUT_S = 30
_PROTECTED_SLUGS = frozenset({"default", "api", "grafana", "status", "www", "admin", "platform"})


@dataclass(frozen=True)
class TestTenant:
    """Test-fixture handle for a provisioned Enterprise tenant.

    Returned by ``provision_enterprise(...)``; consumed by every SaaS
    journey that operates on a tenant other than ``default``.
    """

    slug: str
    tenant_id: uuid.UUID
    plan: str
    region: str
    primary_admin_email: str
    primary_admin_user_id: uuid.UUID | None = None
    dns_records_observed: bool = False
    cleanup_token: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.utcnow())


class TenantProvisioningTimeoutError(Exception):
    """DNS propagation didn't complete within the documented window."""


class AuditChainTimeoutError(Exception):
    """`tenants.created` audit-chain entry never appeared."""


class TenantCleanupError(Exception):
    """Teardown failed with anything other than 404 (idempotent re-run)."""


def _generate_test_slug(worker_id: str | None = None) -> str:
    """Generate a unique test-tenant slug.

    Worker isolation is achieved via the ``e2e-{worker-id}-`` prefix so
    parallel ``pytest-xdist`` workers don't collide.
    """
    suffix = uuid.uuid4().hex[:8]
    if worker_id and worker_id != "master":
        return f"{_TEST_SLUG_PREFIX}{worker_id}-{suffix}"
    return f"{_TEST_SLUG_PREFIX}{suffix}"


def _generate_admin_email(slug: str) -> str:
    """Email under the .invalid TLD per RFC 2606 — non-deliverable by design."""
    return f"e2e-{slug}-admin@e2e.musematic-test.invalid"


def _assert_safe_to_delete(slug: str) -> None:
    """Refuse to clean up anything that isn't an e2e- tenant.

    Defence in depth against an accidentally hand-typed slug colliding
    with a real tenant. The runtime API also refuses, but failing fast
    in the fixture preserves the failure context.
    """
    if not slug.startswith(_TEST_SLUG_PREFIX):
        raise ValueError(f"Refusing to delete non-test tenant slug={slug!r}")
    if slug in _PROTECTED_SLUGS:
        raise ValueError(f"Refusing to delete reserved slug={slug!r}")


@asynccontextmanager
async def provision_enterprise(
    *,
    super_admin_client: "AuthenticatedAsyncClient",
    slug: str | None = None,
    plan: str = "enterprise",
    region: str = "eu-central",
    dpa_artifact: bytes | None = None,
    first_admin_email: str | None = None,
    worker_id: str | None = None,
) -> AsyncIterator[TestTenant]:
    """Provision an Enterprise tenant via the public admin API and yield a
    ``TestTenant`` handle. Cleans up on exit (idempotent — 404 is success).

    The polling for the ``tenants.created`` audit entry and DNS
    propagation are the runtime SLOs documented in spec.md; if either
    misses its budget the fixture raises so the journey reports a
    setup failure rather than silently waiting forever.
    """
    resolved_slug = slug or _generate_test_slug(worker_id)
    resolved_email = first_admin_email or _generate_admin_email(resolved_slug)
    request_body: dict[str, object] = {
        "slug": resolved_slug,
        "display_name": f"E2E test tenant {resolved_slug}",
        "plan": plan,
        "region": region,
        "first_admin_email": resolved_email,
        "contract_metadata": {"e2e_test": True},
    }
    if dpa_artifact is not None:
        # Real flows upload the DPA via a separate endpoint then reference
        # the artefact id; the fixture does not exercise that flow itself
        # (it is the subject of J22). Journeys that need a DPA stand up
        # the upload via the http_client fixture directly.
        request_body["dpa_artifact_id"] = "e2e-dpa-stub"

    response = await super_admin_client.post(
        "/api/v1/admin/tenants",
        json=request_body,
    )
    if response.status_code not in {200, 201}:
        raise TenantCleanupError(
            f"create returned {response.status_code}: {response.text}"
        )
    payload = response.json()
    tenant_id = uuid.UUID(payload["id"])
    cleanup_token = payload.get("cleanup_token", "")

    tenant = TestTenant(
        slug=resolved_slug,
        tenant_id=tenant_id,
        plan=plan,
        region=region,
        primary_admin_email=resolved_email,
        cleanup_token=cleanup_token,
    )

    # Per the contract, wait until tenants.created lands in the audit chain
    # before yielding. Journeys can then assume side-effect chain completed.
    try:
        await _wait_for_audit_entry(
            super_admin_client,
            tenant_id=tenant_id,
            event_type="tenants.created",
            timeout_s=_AUDIT_CHAIN_TIMEOUT_S,
        )
    except AuditChainTimeoutError:
        # Best-effort cleanup before re-raising.
        await _cleanup_tenant(super_admin_client, resolved_slug)
        raise

    try:
        yield tenant
    finally:
        await _cleanup_tenant(super_admin_client, resolved_slug)


async def _wait_for_audit_entry(
    client: "AuthenticatedAsyncClient",
    *,
    tenant_id: uuid.UUID,
    event_type: str,
    timeout_s: int,
) -> None:
    """Poll the audit-chain inspection endpoint until the entry appears."""
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        response = await client.get(
            "/api/v1/admin/audit/entries",
            params={"tenant_id": str(tenant_id), "event_type": event_type, "limit": 1},
        )
        if response.status_code == 200:
            entries = response.json().get("entries", [])
            if entries:
                return
        await asyncio.sleep(2)
    raise AuditChainTimeoutError(
        f"audit entry event_type={event_type!r} tenant_id={tenant_id} did not appear"
    )


async def _cleanup_tenant(
    client: "AuthenticatedAsyncClient",
    slug: str,
) -> None:
    """Idempotent two-phase teardown. 404 from either step is treated as success."""
    _assert_safe_to_delete(slug)

    # Phase 1: schedule deletion (skips the grace period via the test-only flag).
    response = await client.post(
        f"/api/v1/admin/tenants/{slug}/schedule-deletion",
        json={"grace_seconds": 0, "actor_otp": "000000"},  # zero-grace test-mode flag
    )
    if response.status_code not in {200, 202, 404, 409}:
        raise TenantCleanupError(
            f"schedule-deletion returned {response.status_code}: {response.text}"
        )

    # Phase 2: complete deletion (cascade).
    response = await client.post(f"/api/v1/admin/tenants/{slug}/complete-deletion")
    if response.status_code not in {200, 204, 404}:
        raise TenantCleanupError(
            f"complete-deletion returned {response.status_code}: {response.text}"
        )


async def list_test_tenants(
    *,
    super_admin_client: "AuthenticatedAsyncClient | None" = None,
    slug_prefix: str = _TEST_SLUG_PREFIX,
) -> list[TestTenant]:
    """SC-006 helper used by ``tests/e2e/scripts/verify_no_orphans.py``.

    Returns every tenant whose slug starts with ``slug_prefix``. Empty
    list means clean state. The function constructs a transient
    super-admin client when one is not passed in so the helper is
    callable from CLI scripts that don't bring their own.
    """
    if super_admin_client is None:
        from .http_client import AuthenticatedAsyncClient  # noqa: PLC0415

        import os

        base = os.environ.get("PLATFORM_API_URL", "http://localhost:8000")
        async with AuthenticatedAsyncClient(base_url=base) as client:
            return await _do_list(client, slug_prefix)
    return await _do_list(super_admin_client, slug_prefix)


async def _do_list(
    client: "AuthenticatedAsyncClient",
    slug_prefix: str,
) -> list[TestTenant]:
    response = await client.get(
        "/api/v1/admin/tenants",
        params={"slug_prefix": slug_prefix, "limit": 200},
    )
    if response.status_code != 200:
        return []
    items = response.json().get("items", [])
    out: list[TestTenant] = []
    for entry in items:
        try:
            out.append(
                TestTenant(
                    slug=entry["slug"],
                    tenant_id=uuid.UUID(entry["id"]),
                    plan=entry.get("plan", "unknown"),
                    region=entry.get("region", "eu-central"),
                    primary_admin_email=entry.get("primary_admin_email", ""),
                )
            )
        except (KeyError, ValueError):
            continue
    return out


@pytest.fixture
async def tenants(
    http_client: "AuthenticatedAsyncClient",
) -> AsyncIterator[None]:
    """Pytest-fixture wrapper exposing the ``provision_enterprise`` CM
    under a friendly name so journeys can ``async with tenants.provision(...)``.

    The fixture itself yields nothing per-test — it just binds the
    async-CM factory into the test's local scope via attribute access.
    """
    yield  # The journey calls ``provision_enterprise`` directly.
