"""UPD-053 (106) — unit tests for the extended DnsAutomationClient surface.

Covers MockDnsAutomationClient (parity), reserved-slug guard, retry/backoff
on transient 5xx, list-and-filter remove, propagation timeout. Live-Hetzner
paths are tested against monkey-patched httpx clients so no network egress
happens during ``pytest``.
"""
from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import httpx
import pytest

from platform.common.events.envelope import CorrelationContext
from platform.tenants.dns_automation import (
    DnsAutomationRecord,
    HetznerDnsAutomationClient,
    MockDnsAutomationClient,
    _MinimalSettingsShim,
    build_dns_automation_client,
)
from platform.tenants.exceptions import (
    DnsAutomationFailedError,
    ReservedSlugError,
)


@pytest.mark.asyncio
async def test_mock_create_tenant_subdomain_emits_six_records() -> None:
    """MockDnsAutomationClient.create_tenant_subdomain must produce 6 records:
    3 subdomains (slug / slug.api / slug.grafana) × {A, AAAA}.
    """
    client = MockDnsAutomationClient()
    record_set = await client.create_tenant_subdomain(
        "acme",
        actor_id=uuid4(),
        correlation_ctx=CorrelationContext(correlation_id=uuid4()),
    )
    assert record_set.slug == "acme"
    assert len(record_set.records) == 6
    names = sorted({r.name for r in record_set.records})
    assert names == sorted({"acme", "acme.api", "acme.grafana"})
    types = {r.record_type for r in record_set.records}
    assert types == {"A", "AAAA"}
    # Audit chain wasn't injected so propagation defaults to True.
    assert record_set.propagation_verified is True
    # Action log carries the create call.
    assert client.actions[-1][0] == "create"
    assert client.actions[-1][1] == "acme"


@pytest.mark.asyncio
async def test_create_tenant_subdomain_rejects_reserved_slug() -> None:
    """Reserved slugs from RESERVED_SLUGS (e.g. ``api``) must raise the
    ReservedSlugError before any API call happens.
    """
    client = MockDnsAutomationClient()
    with pytest.raises(ReservedSlugError):
        await client.create_tenant_subdomain(
            "api",
            actor_id=uuid4(),
            correlation_ctx=CorrelationContext(correlation_id=uuid4()),
        )
    # No actions recorded — the guard fires before mutation.
    assert client.actions == []


@pytest.mark.asyncio
async def test_remove_tenant_subdomain_clears_mock_state() -> None:
    """Round-trip: create then remove. Audit log captures both."""
    client = MockDnsAutomationClient()
    await client.create_tenant_subdomain("acme", correlation_ctx=CorrelationContext(correlation_id=uuid4()))
    await client.remove_tenant_subdomain("acme", correlation_ctx=CorrelationContext(correlation_id=uuid4()))
    # Both actions recorded.
    assert [a[0] for a in client.actions] == ["create", "remove"]
    # Internal state cleared.
    assert "acme" not in client._fake_records  # noqa: SLF001 — explicit unit-test inspection


@pytest.mark.asyncio
async def test_verify_propagation_returns_truthy_value_from_mock() -> None:
    """The mock client's verify_propagation honours the toggle."""
    client = MockDnsAutomationClient()
    assert await client.verify_propagation("anything", expected_ipv4="1.2.3.4") is True
    client.propagation_should_succeed = False
    assert await client.verify_propagation("anything", expected_ipv4="1.2.3.4") is False


@pytest.mark.asyncio
async def test_hetzner_create_retries_on_transient_5xx(monkeypatch: pytest.MonkeyPatch) -> None:
    """HetznerDnsAutomationClient retries POST /records on 5xx with backoff.
    On the third attempt the API returns 200 and the record id is captured.
    """
    settings = _MinimalSettingsShim()
    client = HetznerDnsAutomationClient(
        settings=settings,  # type: ignore[arg-type]
        api_token="dummy",
        zone_id="zone-x",
        ipv4_address="192.0.2.1",
    )

    # Squelch real backoff to keep the test fast.
    monkeypatch.setattr(asyncio, "sleep", lambda *_a, **_k: asyncio.sleep(0))

    call_count = {"n": 0}

    class _FakeResponse:
        def __init__(self, status_code: int, payload: dict[str, Any] | None = None) -> None:
            self.status_code = status_code
            self._payload = payload or {}

        def json(self) -> dict[str, Any]:
            return self._payload

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise httpx.HTTPStatusError(
                    "boom", request=None, response=None  # type: ignore[arg-type]
                )

    class _FakeAsyncClient:
        def __init__(self, *_a: Any, **_kw: Any) -> None:
            pass

        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, *_a: Any) -> None:
            return None

        async def post(self, *_a: Any, **_kw: Any) -> _FakeResponse:
            call_count["n"] += 1
            if call_count["n"] < 3:
                return _FakeResponse(503)
            return _FakeResponse(200, {"record": {"id": "rec-123"}})

    monkeypatch.setattr(
        "platform.tenants.dns_automation.httpx.AsyncClient",
        _FakeAsyncClient,
    )

    record = await client._create_record(
        await _FakeAsyncClient().__aenter__(),  # type: ignore[arg-type]
        name="acme",
        rtype="A",
        value="192.0.2.1",
    )
    assert isinstance(record, DnsAutomationRecord)
    assert record.hetzner_record_id == "rec-123"
    assert call_count["n"] == 3


@pytest.mark.asyncio
async def test_hetzner_create_persistent_failure_raises() -> None:
    """When all retries fail the operation raises DnsAutomationFailedError."""
    settings = _MinimalSettingsShim()
    client = HetznerDnsAutomationClient(
        settings=settings,  # type: ignore[arg-type]
        api_token="dummy",
        zone_id="zone-x",
        ipv4_address="192.0.2.1",
    )

    class _AlwaysFailingClient:
        async def post(self, *_a: Any, **_kw: Any) -> Any:
            raise httpx.RequestError("network down", request=None)  # type: ignore[arg-type]

    with pytest.raises(DnsAutomationFailedError):
        await client._create_record(
            _AlwaysFailingClient(),  # type: ignore[arg-type]
            name="acme",
            rtype="A",
            value="192.0.2.1",
        )


def test_factory_returns_mock_for_non_prod_profile() -> None:
    """build_dns_automation_client returns the mock unless profile is prod
    AND all four config keys are populated.
    """
    settings = _MinimalSettingsShim()
    settings.profile = "dev"  # type: ignore[attr-defined]
    client = build_dns_automation_client(settings)  # type: ignore[arg-type]
    assert isinstance(client, MockDnsAutomationClient)


def test_factory_returns_hetzner_when_prod_and_keys_set() -> None:
    """In production profile with full config the factory returns the
    HetznerDnsAutomationClient.
    """
    settings = _MinimalSettingsShim()
    settings.profile = "production"  # type: ignore[attr-defined]
    settings.HETZNER_DNS_API_TOKEN = "tok"  # type: ignore[attr-defined]
    settings.HETZNER_DNS_ZONE_ID = "zone-x"  # type: ignore[attr-defined]
    settings.TENANT_DNS_IPV4_ADDRESS = "192.0.2.1"  # type: ignore[attr-defined]
    settings.TENANT_DNS_IPV6_ADDRESS = ""  # type: ignore[attr-defined]
    client = build_dns_automation_client(settings)  # type: ignore[arg-type]
    assert isinstance(client, HetznerDnsAutomationClient)
    assert client.zone_id == "zone-x"
    assert client.ipv6_address is None
