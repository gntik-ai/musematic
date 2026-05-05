"""Tenant DNS automation client.

UPD-053 (106) extends this module from the original single-subdomain
``ensure_records`` Protocol (UPD-046) to a full lifecycle surface covering
the 6-record bundle per Enterprise tenant (3 subdomains × A/AAAA), idempotent
removal on the data-lifecycle phase-2 cascade, and propagation verification
against a public resolver before notifying admins.

The Protocol contract is documented at:
    specs/106-hetzner-clusters/contracts/dns-automation-service.md

Three concrete implementations:
    - HetznerDnsAutomationClient — talks to the Hetzner DNS API.
    - MockDnsAutomationClient — in-memory parity for unit tests.
    - The factory ``build_dns_automation_client(settings)`` returns the
      Hetzner client in production profile when all four config keys are
      populated, otherwise the mock.

Reserved-slug guard, audit chain emission, and structured logging are
applied identically across both concrete clients so unit-test parity holds.
"""
from __future__ import annotations

import asyncio
import json
import socket
import warnings
from dataclasses import dataclass
from platform.audit.service import AuditChainService
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.common.logging import get_logger
from platform.tenants.exceptions import (
    DnsAutomationFailedError,
    ReservedSlugError,
)
from platform.tenants.reserved_slugs import RESERVED_SLUGS
from typing import Any, Protocol
from uuid import UUID, uuid4

import httpx

LOGGER = get_logger(__name__)

DEFAULT_TTL = 300
RETRY_BACKOFF_SECONDS: tuple[float, ...] = (1.0, 2.0, 4.0, 8.0)
PROPAGATION_POLL_INTERVAL_SECONDS = 5
DEFAULT_PROPAGATION_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class DnsAutomationRecord:
    """One concrete DNS record returned by the Hetzner DNS API after creation.

    Stable identity is the ``hetzner_record_id`` returned by the API; the
    ``(name, record_type)`` pair is also unique per tenant slug.
    """

    name: str
    record_type: str  # "A" or "AAAA"
    value: str
    hetzner_record_id: str
    ttl: int = DEFAULT_TTL


@dataclass(frozen=True)
class DnsAutomationRecordSet:
    """Returned by ``create_tenant_subdomain`` — the 6-record bundle plus
    a propagation flag indicating whether a public resolver has observed
    the apex (``{slug}.musematic.ai``) record yet.
    """

    slug: str
    records: list[DnsAutomationRecord]
    propagation_verified: bool = False


def _subdomains_for(slug: str) -> list[str]:
    """Return the three logical subdomain names ``dns_automation`` manages
    per tenant slug. The names are zone-relative — the Hetzner DNS API
    expects bare subdomain labels, not FQDNs.
    """
    return [slug, f"{slug}.api", f"{slug}.grafana"]


def _check_reserved(slug: str) -> None:
    if slug in RESERVED_SLUGS:
        raise ReservedSlugError(slug)


class DnsAutomationClient(Protocol):
    """UPD-046 + UPD-053 (106) — extended Protocol surface.

    ``ensure_records`` is kept as a deprecated facade for one release; new
    callers should use ``create_tenant_subdomain``.
    """

    async def create_tenant_subdomain(
        self,
        slug: str,
        *,
        actor_id: UUID | None = None,
        correlation_ctx: CorrelationContext,
    ) -> DnsAutomationRecordSet: ...

    async def remove_tenant_subdomain(
        self,
        slug: str,
        *,
        actor_id: UUID | None = None,
        correlation_ctx: CorrelationContext,
    ) -> None: ...

    async def verify_propagation(
        self,
        subdomain: str,
        *,
        expected_ipv4: str,
        timeout_seconds: int = DEFAULT_PROPAGATION_TIMEOUT_SECONDS,
    ) -> bool: ...

    async def ensure_records(self, subdomain: str) -> None:
        """DEPRECATED — kept for one release. Use ``create_tenant_subdomain``."""


class _DnsAutomationBase:
    """Shared scaffolding for the concrete clients: per-(zone, slug) lock
    map, audit chain wiring, and the deprecated ``ensure_records`` facade.
    """

    def __init__(
        self,
        *,
        settings: PlatformSettings,
        audit_chain: AuditChainService | None = None,
    ) -> None:
        self.settings = settings
        self.audit_chain = audit_chain
        # Per-(zone_id, slug) locks keep concurrent calls for the same slug
        # serialised. Different slugs proceed in parallel.
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}

    def _lock_for(self, zone_id: str, slug: str) -> asyncio.Lock:
        key = (zone_id, slug)
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    async def _emit_audit(
        self,
        *,
        event_type: str,
        actor_id: UUID | None,
        slug: str,
        details: dict[str, Any],
        correlation_ctx: CorrelationContext,
        tenant_id: UUID | None = None,
    ) -> None:
        """Emit one audit-chain entry for a DNS lifecycle event.

        Mirrors the canonical ``tenants/`` BC pattern (see
        ``TenantsService._append_created_audit``): construct a JSON payload,
        canonicalize, hand to ``AuditChainService.append`` with
        ``audit_event_source="tenants"``. Failures are logged and swallowed
        so DNS lifecycle operations continue.
        """
        del correlation_ctx  # propagated via the audit chain's own context vars
        if self.audit_chain is None:
            return
        payload: dict[str, object] = {
            "slug": slug,
            "actor_user_id": str(actor_id) if actor_id is not None else None,
            **{k: v for k, v in details.items() if v is not None},
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        try:
            await self.audit_chain.append(
                uuid4(),
                "tenants",
                canonical,
                event_type=event_type,
                actor_role="super_admin",
                canonical_payload_json=payload,
                tenant_id=tenant_id,
            )
        except Exception:  # pragma: no cover — audit failures must not block DNS ops
            LOGGER.exception("tenants.dns.audit_emit_failed", event_type=event_type, slug=slug)

    async def ensure_records(self, subdomain: str) -> None:
        """Deprecated facade preserved for one release.

        Calls ``create_tenant_subdomain(<slug>)`` where ``<slug>`` is the
        first label of ``subdomain``. Emits a DeprecationWarning.
        """
        warnings.warn(
            "ensure_records is deprecated; call create_tenant_subdomain instead",
            DeprecationWarning,
            stacklevel=2,
        )
        slug = subdomain.split(".")[0]
        LOGGER.info("tenants.dns.deprecated_ensure_records", subdomain=subdomain, slug=slug)
        await self.create_tenant_subdomain(  # type: ignore[attr-defined]
            slug,
            correlation_ctx=CorrelationContext(correlation_id=uuid4()),
        )

    async def verify_propagation(  # noqa: D401
        self,
        subdomain: str,
        *,
        expected_ipv4: str,
        timeout_seconds: int = DEFAULT_PROPAGATION_TIMEOUT_SECONDS,
    ) -> bool:
        """Resolve ``subdomain`` against a public resolver until it returns
        ``expected_ipv4`` or ``timeout_seconds`` elapses.

        Resolver errors are logged at warning level and treated as "not yet
        propagated"; they never crash the create path.
        """
        resolver = getattr(self.settings, "DNS_PROPAGATION_RESOLVER", "1.1.1.1")
        deadline = asyncio.get_event_loop().time() + timeout_seconds
        while asyncio.get_event_loop().time() < deadline:
            try:
                addresses = await asyncio.to_thread(_resolve_via, subdomain, resolver)
            except Exception:  # pragma: no cover — defensive
                LOGGER.warning(
                    "tenants.dns.resolver_error",
                    subdomain=subdomain,
                    resolver=resolver,
                )
                await asyncio.sleep(PROPAGATION_POLL_INTERVAL_SECONDS)
                continue
            if expected_ipv4 in addresses:
                return True
            await asyncio.sleep(PROPAGATION_POLL_INTERVAL_SECONDS)
        return False


def _resolve_via(host: str, resolver: str) -> list[str]:  # pragma: no cover — uses stdlib socket
    """Best-effort host → A-record resolver. The ``resolver`` argument is
    informational; the stdlib ``getaddrinfo`` consults the system resolver
    config. Production runs typically configure ``/etc/resolv.conf`` to
    point at the desired resolver, or DNS-over-HTTPS fronts the call.
    """
    del resolver
    try:
        infos = socket.getaddrinfo(host, None, family=socket.AF_INET)
    except socket.gaierror:
        return []
    return [info[4][0] for info in infos]


class HetznerDnsAutomationClient(_DnsAutomationBase):
    """Production implementation backed by the Hetzner DNS API.

    Concrete method bodies (`create_tenant_subdomain`, `remove_tenant_subdomain`)
    land in Phase 5 / US3 (T040–T044). The Phase 2 widening only declares the
    Protocol surface so other phases can import the dataclasses.
    """

    BASE_URL = "https://dns.hetzner.com/api/v1"

    def __init__(
        self,
        *,
        settings: PlatformSettings,
        api_token: str,
        zone_id: str,
        ipv4_address: str,
        ipv6_address: str | None = None,
        audit_chain: AuditChainService | None = None,
    ) -> None:
        super().__init__(settings=settings, audit_chain=audit_chain)
        self.api_token = api_token
        self.zone_id = zone_id
        self.ipv4_address = ipv4_address
        self.ipv6_address = ipv6_address

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=30.0,
            headers={"Auth-API-Token": self.api_token},
        )

    async def create_tenant_subdomain(
        self,
        slug: str,
        *,
        actor_id: UUID | None = None,
        correlation_ctx: CorrelationContext,
    ) -> DnsAutomationRecordSet:
        _check_reserved(slug)
        async with self._lock_for(self.zone_id, slug):
            records: list[DnsAutomationRecord] = []
            try:
                async with self._client() as client:
                    for sub in _subdomains_for(slug):
                        records.append(
                            await self._create_record(client, sub, "A", self.ipv4_address)
                        )
                        if self.ipv6_address:
                            records.append(
                                await self._create_record(
                                    client, sub, "AAAA", self.ipv6_address
                                )
                            )
            except Exception as exc:
                await self._emit_audit(
                    event_type="tenants.dns.records_failed",
                    actor_id=actor_id,
                    slug=slug,
                    details={
                        "partial_records": [
                            {"name": r.name, "type": r.record_type, "id": r.hetzner_record_id}
                            for r in records
                        ],
                        "reason": str(exc),
                    },
                    correlation_ctx=correlation_ctx,
                )
                raise DnsAutomationFailedError(str(exc)) from exc

            apex = f"{slug}.{self.settings.PLATFORM_DOMAIN}"
            propagated = await self.verify_propagation(
                apex,
                expected_ipv4=self.ipv4_address,
            )
            await self._emit_audit(
                event_type="tenants.dns.records_created",
                actor_id=actor_id,
                slug=slug,
                details={
                    "records": [
                        {"name": r.name, "type": r.record_type, "id": r.hetzner_record_id}
                        for r in records
                    ],
                    "propagation_verified": propagated,
                },
                correlation_ctx=correlation_ctx,
            )
            LOGGER.info(
                "tenants.dns.records_created",
                slug=slug,
                record_count=len(records),
                propagation_verified=propagated,
            )
            return DnsAutomationRecordSet(
                slug=slug,
                records=records,
                propagation_verified=propagated,
            )

    async def remove_tenant_subdomain(
        self,
        slug: str,
        *,
        actor_id: UUID | None = None,
        correlation_ctx: CorrelationContext,
    ) -> None:
        async with self._lock_for(self.zone_id, slug):
            deleted_ids: list[str] = []
            try:
                async with self._client() as client:
                    listed = await self._list_records(client)
                    targets = set(_subdomains_for(slug))
                    for record in listed:
                        if record.get("name") in targets:
                            await self._delete_record(client, record["id"])
                            deleted_ids.append(record["id"])
            except Exception as exc:
                await self._emit_audit(
                    event_type="tenants.dns.records_failed",
                    actor_id=actor_id,
                    slug=slug,
                    details={
                        "operation": "remove",
                        "deleted_record_ids": deleted_ids,
                        "reason": str(exc),
                    },
                    correlation_ctx=correlation_ctx,
                )
                raise DnsAutomationFailedError(str(exc)) from exc
            await self._emit_audit(
                event_type="tenants.dns.records_removed",
                actor_id=actor_id,
                slug=slug,
                details={"deleted_record_ids": deleted_ids},
                correlation_ctx=correlation_ctx,
            )
            LOGGER.info(
                "tenants.dns.records_removed",
                slug=slug,
                deleted_count=len(deleted_ids),
            )

    async def _create_record(
        self,
        client: httpx.AsyncClient,
        name: str,
        rtype: str,
        value: str,
    ) -> DnsAutomationRecord:
        body = {
            "zone_id": self.zone_id,
            "type": rtype,
            "name": name,
            "value": value,
            "ttl": DEFAULT_TTL,
        }
        for attempt, backoff in enumerate(RETRY_BACKOFF_SECONDS):
            try:
                response = await client.post(f"{self.BASE_URL}/records", json=body)
            except httpx.RequestError as exc:
                if attempt + 1 == len(RETRY_BACKOFF_SECONDS):
                    raise DnsAutomationFailedError(str(exc)) from exc
                await asyncio.sleep(backoff)
                continue
            if response.status_code == 422:
                # "record already exists" — idempotent re-run; look it up.
                listed = await self._list_records(client)
                for record in listed:
                    if record.get("name") == name and record.get("type") == rtype:
                        return DnsAutomationRecord(
                            name=name,
                            record_type=rtype,
                            value=value,
                            hetzner_record_id=str(record["id"]),
                        )
                raise DnsAutomationFailedError(
                    f"422 on create but record {name}/{rtype} not found in list"
                )
            if response.status_code >= 500:
                if attempt + 1 == len(RETRY_BACKOFF_SECONDS):
                    raise DnsAutomationFailedError(
                        f"persistent {response.status_code} on POST /records"
                    )
                await asyncio.sleep(backoff)
                continue
            response.raise_for_status()
            payload = response.json()
            record_id = str(payload["record"]["id"])
            return DnsAutomationRecord(
                name=name,
                record_type=rtype,
                value=value,
                hetzner_record_id=record_id,
            )
        raise DnsAutomationFailedError("retry budget exhausted on create")

    async def _list_records(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        response = await client.get(
            f"{self.BASE_URL}/records",
            params={"zone_id": self.zone_id},
        )
        response.raise_for_status()
        records = response.json().get("records", [])
        return [r for r in records if isinstance(r, dict)]

    async def _delete_record(self, client: httpx.AsyncClient, record_id: str) -> None:
        for attempt, backoff in enumerate(RETRY_BACKOFF_SECONDS):
            try:
                response = await client.delete(f"{self.BASE_URL}/records/{record_id}")
            except httpx.RequestError as exc:
                if attempt + 1 == len(RETRY_BACKOFF_SECONDS):
                    raise DnsAutomationFailedError(str(exc)) from exc
                await asyncio.sleep(backoff)
                continue
            if response.status_code == 404:
                return  # idempotent
            if response.status_code >= 500:
                if attempt + 1 == len(RETRY_BACKOFF_SECONDS):
                    raise DnsAutomationFailedError(
                        f"persistent {response.status_code} on DELETE"
                    )
                await asyncio.sleep(backoff)
                continue
            response.raise_for_status()
            return


class MockDnsAutomationClient(_DnsAutomationBase):
    """In-memory parity client used by unit tests and dev profiles."""

    def __init__(
        self,
        *,
        settings: PlatformSettings | None = None,
        audit_chain: AuditChainService | None = None,
    ) -> None:
        # Allow construction with no settings for the simplest test cases.
        super().__init__(
            settings=settings or _MinimalSettingsShim(),
            audit_chain=audit_chain,
        )
        self.actions: list[tuple[str, str, list[DnsAutomationRecord]]] = []
        self.requests: list[str] = []  # backwards-compat with the original UPD-046 client
        self.propagation_should_succeed: bool = True
        self._fake_records: dict[str, list[DnsAutomationRecord]] = {}
        self._next_record_id: int = 1

    async def create_tenant_subdomain(
        self,
        slug: str,
        *,
        actor_id: UUID | None = None,
        correlation_ctx: CorrelationContext,
    ) -> DnsAutomationRecordSet:
        _check_reserved(slug)
        records: list[DnsAutomationRecord] = []
        for sub in _subdomains_for(slug):
            for rtype, value in (("A", "192.0.2.1"), ("AAAA", "2001:db8::1")):
                record = DnsAutomationRecord(
                    name=sub,
                    record_type=rtype,
                    value=value,
                    hetzner_record_id=f"mock-{self._next_record_id}",
                )
                self._next_record_id += 1
                records.append(record)
        self._fake_records[slug] = records
        self.actions.append(("create", slug, records))
        self.requests.append(slug)
        await self._emit_audit(
            event_type="tenants.dns.records_created",
            actor_id=actor_id,
            slug=slug,
            details={
                "records": [
                    {"name": r.name, "type": r.record_type, "id": r.hetzner_record_id}
                    for r in records
                ],
                "propagation_verified": self.propagation_should_succeed,
            },
            correlation_ctx=correlation_ctx,
        )
        return DnsAutomationRecordSet(
            slug=slug,
            records=records,
            propagation_verified=self.propagation_should_succeed,
        )

    async def remove_tenant_subdomain(
        self,
        slug: str,
        *,
        actor_id: UUID | None = None,
        correlation_ctx: CorrelationContext,
    ) -> None:
        records = self._fake_records.pop(slug, [])
        deleted_ids = [r.hetzner_record_id for r in records]
        self.actions.append(("remove", slug, records))
        await self._emit_audit(
            event_type="tenants.dns.records_removed",
            actor_id=actor_id,
            slug=slug,
            details={"deleted_record_ids": deleted_ids},
            correlation_ctx=correlation_ctx,
        )

    async def verify_propagation(
        self,
        subdomain: str,
        *,
        expected_ipv4: str,
        timeout_seconds: int = DEFAULT_PROPAGATION_TIMEOUT_SECONDS,
    ) -> bool:
        del subdomain, expected_ipv4, timeout_seconds
        return self.propagation_should_succeed

    # Backwards-compatible facade used by older code paths and existing tests.
    async def ensure_records(self, subdomain: str) -> None:
        warnings.warn(
            "ensure_records is deprecated; call create_tenant_subdomain instead",
            DeprecationWarning,
            stacklevel=2,
        )
        slug = subdomain.split(".")[0]
        self.requests.append(subdomain)
        LOGGER.info("tenants.dns.mock_records_ready", tenant_subdomain=subdomain)
        await self.create_tenant_subdomain(slug, correlation_ctx=CorrelationContext())


@dataclass
class _MinimalSettingsShim:
    """Lightweight stand-in for ``PlatformSettings`` so ``MockDnsAutomationClient``
    can be constructed in tests without wiring the full settings tree.
    """

    DNS_PROPAGATION_RESOLVER: str = "1.1.1.1"
    PLATFORM_DOMAIN: str = "musematic.ai"


def build_dns_automation_client(
    settings: PlatformSettings,
    *,
    audit_chain: AuditChainService | None = None,
) -> DnsAutomationClient:
    """Factory used by the BC's dependency-injection wiring.

    Returns the Hetzner client only when (a) the runtime profile is
    production AND (b) all four config keys are populated. Otherwise the
    mock client is returned so dev/test profiles never reach the live
    Hetzner API.
    """
    if settings.profile in {"production", "prod"}:
        token = getattr(settings, "HETZNER_DNS_API_TOKEN", "")
        zone_id = getattr(settings, "HETZNER_DNS_ZONE_ID", "")
        ipv4 = getattr(settings, "TENANT_DNS_IPV4_ADDRESS", "")
        ipv6 = getattr(settings, "TENANT_DNS_IPV6_ADDRESS", "")
        if token and zone_id and ipv4:
            return HetznerDnsAutomationClient(
                settings=settings,
                api_token=str(token),
                zone_id=str(zone_id),
                ipv4_address=str(ipv4),
                ipv6_address=str(ipv6) or None,
                audit_chain=audit_chain,
            )
    return MockDnsAutomationClient(settings=settings, audit_chain=audit_chain)


__all__ = [
    "DnsAutomationClient",
    "DnsAutomationRecord",
    "DnsAutomationRecordSet",
    "HetznerDnsAutomationClient",
    "MockDnsAutomationClient",
    "build_dns_automation_client",
]
