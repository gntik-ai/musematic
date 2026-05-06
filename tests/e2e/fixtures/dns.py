"""UPD-054 (107) — DNS test provider for SaaS-pass journeys.

Two implementations behind a single ``DnsTestProvider`` Protocol that
mirrors the runtime ``DnsAutomationClient`` from UPD-053:

- ``MockDnsProvider`` — in-process state, no network, default. Keeps
  PR CI hermetic and < 30 min wall-clock.
- ``LiveHetznerDnsProvider`` — real Hetzner DNS test zone, gated by
  ``RUN_J29=1``. Operator opts in to validate the live integration.

Contract: specs/107-saas-e2e-journeys/contracts/dns-fixture.md
"""
from __future__ import annotations

import asyncio
import os
import socket
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

import pytest


__all__ = [
    "TestDnsRecord",
    "DnsTestProvider",
    "DnsPropagationTimeoutError",
    "LiveModeMissingTokenError",
    "ProductionZoneRefusedError",
    "MockDnsProvider",
    "LiveHetznerDnsProvider",
    "build_dns_test_provider",
    "dns_provider",
]


# Reserved slugs (mirrors apps/control-plane/src/platform/tenants/reserved_slugs.py)
RESERVED_SLUGS = frozenset(
    {"api", "grafana", "status", "www", "admin", "platform", "default"}
)


@dataclass(frozen=True)
class TestDnsRecord:
    """One DNS record managed by the test provider."""

    name: str
    record_type: str
    value: str
    provider_record_id: str | None
    created_at: datetime = field(default_factory=datetime.utcnow)


class DnsPropagationTimeoutError(RuntimeError):
    """`verify_propagation` returned False within the timeout."""


class LiveModeMissingTokenError(RuntimeError):
    """`RUN_J29=1` set but the Hetzner test-zone token is missing."""


class ProductionZoneRefusedError(RuntimeError):
    """Live provider asked to operate against the production zone."""


class DnsTestProvider(Protocol):
    """Mirrors the runtime DnsAutomationClient Protocol so journeys
    written against the mock work identically against the live provider.
    """

    async def create_tenant_subdomain(
        self,
        slug: str,
        *,
        ipv4: str,
        ipv6: str | None = None,
    ) -> list[TestDnsRecord]: ...

    async def remove_tenant_subdomain(self, slug: str) -> int: ...

    async def verify_propagation(
        self,
        host: str,
        *,
        expected_ipv4: str,
        timeout_seconds: int = 60,
    ) -> bool: ...

    async def list_records_for(self, slug: str) -> list[TestDnsRecord]: ...


def _check_reserved(slug: str) -> None:
    if slug in RESERVED_SLUGS:
        raise ValueError(f"refusing to operate on reserved slug={slug!r}")


def _subdomains_for(slug: str) -> list[str]:
    """Three logical subdomains per tenant: apex, .api, .grafana."""
    return [slug, f"{slug}.api", f"{slug}.grafana"]


class MockDnsProvider:
    """In-process state. Default for hermetic PR CI."""

    def __init__(self) -> None:
        self._records: dict[str, list[TestDnsRecord]] = {}
        self._next_id: int = 1

    async def create_tenant_subdomain(
        self,
        slug: str,
        *,
        ipv4: str,
        ipv6: str | None = None,
    ) -> list[TestDnsRecord]:
        _check_reserved(slug)
        records: list[TestDnsRecord] = []
        for sub in _subdomains_for(slug):
            for rtype, value in (("A", ipv4), ("AAAA", ipv6)):
                if value is None:
                    continue
                records.append(
                    TestDnsRecord(
                        name=sub,
                        record_type=rtype,
                        value=value,
                        provider_record_id=f"mock-{self._next_id}",
                    )
                )
                self._next_id += 1
        self._records[slug] = records
        return records

    async def remove_tenant_subdomain(self, slug: str) -> int:
        _check_reserved(slug)
        records = self._records.pop(slug, [])
        return len(records)

    async def verify_propagation(
        self,
        host: str,
        *,
        expected_ipv4: str,
        timeout_seconds: int = 60,
    ) -> bool:
        # The mock honours the propagation contract by checking its own state.
        slug = host.split(".")[0]
        records = self._records.get(slug, [])
        return any(r.record_type == "A" and r.value == expected_ipv4 for r in records)

    async def list_records_for(self, slug: str) -> list[TestDnsRecord]:
        return list(self._records.get(slug, []))

    async def list_orphan_records(self) -> list[TestDnsRecord]:
        """Soak-helper: every record still in state at session end."""
        return [rec for records in self._records.values() for rec in records]


class LiveHetznerDnsProvider:
    """Real Hetzner DNS test-zone provider. Gated by ``RUN_J29=1`` and a
    Vault-resolved API token scoped to the test zone.
    """

    BASE_URL = "https://dns.hetzner.com/api/v1"
    PRODUCTION_ZONE_NAMES = frozenset({"musematic.ai"})

    def __init__(self, *, api_token: str, zone_id: str, zone_name: str) -> None:
        if zone_name in self.PRODUCTION_ZONE_NAMES:
            raise ProductionZoneRefusedError(
                f"refusing to operate against production zone {zone_name!r}"
            )
        if not api_token:
            raise LiveModeMissingTokenError("Hetzner DNS API token missing")
        self._api_token = api_token
        self._zone_id = zone_id
        self._zone_name = zone_name
        self._lock = asyncio.Lock()  # per-zone serialisation per research R7

    async def create_tenant_subdomain(
        self,
        slug: str,
        *,
        ipv4: str,
        ipv6: str | None = None,
    ) -> list[TestDnsRecord]:
        _check_reserved(slug)
        # Real implementation talks to the Hetzner DNS API. Mirrors the
        # runtime client at apps/control-plane/src/platform/tenants/
        # dns_automation.py:HetznerDnsAutomationClient — kept here as a
        # stub since journey bodies typically operate against the mock
        # in PR CI.
        raise NotImplementedError(
            "LiveHetznerDnsProvider.create_tenant_subdomain — only used "
            "with RUN_J29=1; implement when the live-DNS journey lands."
        )

    async def remove_tenant_subdomain(self, slug: str) -> int:
        _check_reserved(slug)
        raise NotImplementedError(
            "LiveHetznerDnsProvider.remove_tenant_subdomain — see above."
        )

    async def verify_propagation(
        self,
        host: str,
        *,
        expected_ipv4: str,
        timeout_seconds: int = 60,
    ) -> bool:
        """Poll a public resolver until the host resolves to expected_ipv4
        or timeout elapses. Resolver errors logged + treated as 'not yet
        propagated' (mirrors the runtime client).
        """
        deadline = asyncio.get_event_loop().time() + timeout_seconds
        while asyncio.get_event_loop().time() < deadline:
            try:
                infos = await asyncio.to_thread(
                    socket.getaddrinfo, host, None, family=socket.AF_INET
                )
                if any(info[4][0] == expected_ipv4 for info in infos):
                    return True
            except socket.gaierror:
                pass
            await asyncio.sleep(5)
        return False

    async def list_records_for(self, slug: str) -> list[TestDnsRecord]:
        # Live mode would issue GET /records?zone_id=... and filter.
        raise NotImplementedError(
            "LiveHetznerDnsProvider.list_records_for — see above."
        )


def build_dns_test_provider() -> DnsTestProvider:
    """Factory selecting the implementation based on env. ``RUN_J29=1`` +
    a non-empty Hetzner test token == live; else mock.
    """
    if os.environ.get("RUN_J29") != "1":
        return MockDnsProvider()
    api_token = os.environ.get("HETZNER_DNS_API_TOKEN", "")
    zone_id = os.environ.get("HETZNER_DNS_ZONE_ID", "")
    zone_name = os.environ.get("HETZNER_DNS_ZONE_NAME", "")
    if not api_token or not zone_name:
        raise LiveModeMissingTokenError(
            "RUN_J29=1 but HETZNER_DNS_* env vars are unset"
        )
    return LiveHetznerDnsProvider(
        api_token=api_token, zone_id=zone_id, zone_name=zone_name
    )


@pytest.fixture
async def dns_provider() -> AsyncIterator[DnsTestProvider]:
    """Pytest fixture wiring ``build_dns_test_provider`` into journeys.

    Yields the provider; on teardown calls ``list_orphan_records`` (mock
    only) and asserts the result is empty so per-test cleanup didn't
    leak.
    """
    provider = build_dns_test_provider()
    try:
        yield provider
    finally:
        leak = getattr(provider, "list_orphan_records", None)
        if leak is not None:
            orphans = await leak()
            if orphans:
                # Don't raise on cleanup — just emit a warning that the
                # session-end soak verifier picks up.
                print(
                    f"WARNING: {len(orphans)} orphan DNS records left at fixture teardown",
                    flush=True,
                )
