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
    3 subdomains (slug / slug.api / slug.grafana) x {A, AAAA}.
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
    async def _instant_sleep(*_a: Any, **_kw: Any) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _instant_sleep)

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


# --- UPD-053 (106) US3 audit / propagation / idempotency coverage --------


class _AuditChainSpy:
    """Records every ``append`` call so assertions can inspect emitted
    ``event_type`` and payload shape without standing up a DB.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def append(
        self,
        audit_event_id: Any,
        audit_event_source: str,
        canonical_payload: bytes,
        *,
        event_type: str | None = None,
        actor_role: str | None = None,
        severity: str = "info",
        canonical_payload_json: dict[str, object] | None = None,
        impersonation_user_id: Any | None = None,
        tenant_id: Any | None = None,
    ) -> None:
        self.calls.append(
            {
                "event_type": event_type,
                "audit_event_source": audit_event_source,
                "payload": canonical_payload_json,
                "tenant_id": tenant_id,
            }
        )


@pytest.mark.asyncio
async def test_mock_create_emits_audit_chain_records_created() -> None:
    """Each successful create_tenant_subdomain MUST emit one
    ``tenants.dns.records_created`` audit-chain entry whose payload carries
    the slug and the 6 records (without IP values).
    """
    audit = _AuditChainSpy()
    client = MockDnsAutomationClient(audit_chain=audit)  # type: ignore[arg-type]
    await client.create_tenant_subdomain(
        "acme",
        actor_id=uuid4(),
        correlation_ctx=CorrelationContext(correlation_id=uuid4()),
    )
    create_calls = [c for c in audit.calls if c["event_type"] == "tenants.dns.records_created"]
    assert len(create_calls) == 1
    payload = create_calls[0]["payload"]
    assert payload["slug"] == "acme"
    assert len(payload["records"]) == 6
    # No IPv4/IPv6 leakage in the audit row.
    for record in payload["records"]:
        assert "name" in record and "type" in record and "id" in record
        assert "value" not in record


@pytest.mark.asyncio
async def test_mock_remove_emits_audit_chain_records_removed() -> None:
    """remove_tenant_subdomain MUST emit ``tenants.dns.records_removed``
    with the deleted record ids and treat unknown slugs as a no-op success.
    """
    audit = _AuditChainSpy()
    client = MockDnsAutomationClient(audit_chain=audit)  # type: ignore[arg-type]
    await client.create_tenant_subdomain(
        "acme",
        correlation_ctx=CorrelationContext(correlation_id=uuid4()),
    )
    await client.remove_tenant_subdomain(
        "acme",
        correlation_ctx=CorrelationContext(correlation_id=uuid4()),
    )
    remove_calls = [c for c in audit.calls if c["event_type"] == "tenants.dns.records_removed"]
    assert len(remove_calls) == 1
    assert len(remove_calls[0]["payload"]["deleted_record_ids"]) == 6

    # Unknown slug — idempotent re-run yields an empty deletion set.
    await client.remove_tenant_subdomain(
        "ghost-tenant",
        correlation_ctx=CorrelationContext(correlation_id=uuid4()),
    )
    ghost_call = [
        c
        for c in audit.calls
        if c["event_type"] == "tenants.dns.records_removed"
        and c["payload"]["slug"] == "ghost-tenant"
    ]
    assert len(ghost_call) == 1
    assert ghost_call[0]["payload"]["deleted_record_ids"] == []


@pytest.mark.asyncio
async def test_hetzner_delete_404_treated_as_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 404 on ``DELETE /records/{id}`` is treated as success so
    remove_tenant_subdomain re-runs are idempotent (the operator may have
    already removed the records out-of-band).
    """
    settings = _MinimalSettingsShim()
    client = HetznerDnsAutomationClient(
        settings=settings,  # type: ignore[arg-type]
        api_token="dummy",
        zone_id="zone-x",
        ipv4_address="192.0.2.1",
    )

    async def _instant_sleep(*_a: Any, **_kw: Any) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _instant_sleep)

    class _FakeResponse:
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code

        def raise_for_status(self) -> None:
            return None

    class _FakeAsyncClient:
        async def delete(self, *_a: Any, **_kw: Any) -> _FakeResponse:
            return _FakeResponse(404)

    # Should NOT raise.
    await client._delete_record(_FakeAsyncClient(), "rec-doesnotexist")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_verify_propagation_returns_false_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the resolver never returns the expected IPv4 the call MUST
    return False after ``timeout_seconds`` without raising. Resolver errors
    are swallowed (logged at warning) so the create path is never crashed.
    """
    settings = _MinimalSettingsShim()
    client = HetznerDnsAutomationClient(
        settings=settings,  # type: ignore[arg-type]
        api_token="dummy",
        zone_id="zone-x",
        ipv4_address="192.0.2.1",
    )

    async def _instant_sleep(*_a: Any, **_kw: Any) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _instant_sleep)

    # Resolver always returns no addresses → loop until deadline → return False.
    monkeypatch.setattr(
        "platform.tenants.dns_automation._resolve_via",
        lambda host, resolver: [],
    )

    result = await client.verify_propagation(
        "acme.musematic.ai",
        expected_ipv4="192.0.2.1",
        timeout_seconds=1,
    )
    assert result is False


def _stub_async_client(monkeypatch: pytest.MonkeyPatch, fake: Any) -> None:
    """Make ``async with self._client() as client`` yield ``fake``."""

    class _Wrapper:
        def __init__(self, *_a: Any, **_kw: Any) -> None:
            pass

        async def __aenter__(self) -> Any:
            return fake

        async def __aexit__(self, *_a: Any) -> None:
            return None

    monkeypatch.setattr(
        "platform.tenants.dns_automation.httpx.AsyncClient",
        _Wrapper,
    )


@pytest.mark.asyncio
async def test_hetzner_create_tenant_subdomain_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end ``create_tenant_subdomain`` on the Hetzner client:
    6 records created (3 subdomains x A+AAAA), audit chain emitted,
    propagation verified, lock acquired and released.
    """
    settings = _MinimalSettingsShim()
    audit = _AuditChainSpy()
    client = HetznerDnsAutomationClient(
        settings=settings,  # type: ignore[arg-type]
        api_token="dummy",
        zone_id="zone-x",
        ipv4_address="192.0.2.1",
        ipv6_address="2001:db8::1",
        audit_chain=audit,  # type: ignore[arg-type]
    )

    async def _instant_sleep(*_a: Any, **_kw: Any) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _instant_sleep)
    monkeypatch.setattr(
        "platform.tenants.dns_automation._resolve_via",
        lambda host, resolver: ["192.0.2.1"],
    )

    # Fake httpx response factory
    class _R:
        def __init__(self, code: int, payload: dict[str, Any] | None = None) -> None:
            self.status_code = code
            self._p = payload or {}

        def json(self) -> dict[str, Any]:
            return self._p

        def raise_for_status(self) -> None:
            return None

    counter = {"n": 0}

    class _FakeAsyncClient:
        async def post(self, _url: str, **_kw: Any) -> _R:
            counter["n"] += 1
            return _R(200, {"record": {"id": f"rec-{counter['n']}"}})

    _stub_async_client(monkeypatch, _FakeAsyncClient())

    result = await client.create_tenant_subdomain(
        "acme",
        actor_id=uuid4(),
        correlation_ctx=CorrelationContext(correlation_id=uuid4()),
    )
    assert result.slug == "acme"
    assert len(result.records) == 6  # 3 subdomains x {A, AAAA}
    assert result.propagation_verified is True
    create_calls = [
        c for c in audit.calls if c["event_type"] == "tenants.dns.records_created"
    ]
    assert len(create_calls) == 1


@pytest.mark.asyncio
async def test_hetzner_create_emits_failed_audit_on_exhausted_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When all retries are exhausted, the Hetzner client MUST emit a
    ``tenants.dns.records_failed`` audit entry with the partial record
    set before raising ``DnsAutomationFailedError``.
    """
    settings = _MinimalSettingsShim()
    audit = _AuditChainSpy()
    client = HetznerDnsAutomationClient(
        settings=settings,  # type: ignore[arg-type]
        api_token="dummy",
        zone_id="zone-x",
        ipv4_address="192.0.2.1",
        audit_chain=audit,  # type: ignore[arg-type]
    )

    async def _instant_sleep(*_a: Any, **_kw: Any) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _instant_sleep)

    class _R:
        status_code = 503

        def json(self) -> dict[str, Any]:
            return {}

        def raise_for_status(self) -> None:
            return None

    class _FakeAsyncClient:
        async def post(self, *_a: Any, **_kw: Any) -> _R:
            return _R()

    _stub_async_client(monkeypatch, _FakeAsyncClient())

    with pytest.raises(DnsAutomationFailedError):
        await client.create_tenant_subdomain(
            "acme",
            correlation_ctx=CorrelationContext(correlation_id=uuid4()),
        )

    failed_calls = [
        c for c in audit.calls if c["event_type"] == "tenants.dns.records_failed"
    ]
    assert len(failed_calls) == 1
    assert failed_calls[0]["payload"]["slug"] == "acme"


@pytest.mark.asyncio
async def test_hetzner_remove_tenant_subdomain_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``remove_tenant_subdomain`` lists records, filters by the slug's
    expected subdomain set, deletes each match, and emits a
    ``tenants.dns.records_removed`` audit entry.
    """
    settings = _MinimalSettingsShim()
    audit = _AuditChainSpy()
    client = HetznerDnsAutomationClient(
        settings=settings,  # type: ignore[arg-type]
        api_token="dummy",
        zone_id="zone-x",
        ipv4_address="192.0.2.1",
        audit_chain=audit,  # type: ignore[arg-type]
    )

    async def _instant_sleep(*_a: Any, **_kw: Any) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _instant_sleep)

    class _R:
        def __init__(self, code: int, payload: dict[str, Any] | None = None) -> None:
            self.status_code = code
            self._p = payload or {}

        def json(self) -> dict[str, Any]:
            return self._p

        def raise_for_status(self) -> None:
            return None

    list_payload = {
        "records": [
            {"id": "rec-1", "name": "acme", "type": "A"},
            {"id": "rec-2", "name": "acme.api", "type": "A"},
            {"id": "rec-3", "name": "acme.grafana", "type": "A"},
            {"id": "rec-4", "name": "other.tenant", "type": "A"},  # ignored
        ]
    }

    class _FakeAsyncClient:
        async def get(self, *_a: Any, **_kw: Any) -> _R:
            return _R(200, list_payload)

        async def delete(self, *_a: Any, **_kw: Any) -> _R:
            return _R(200)

    _stub_async_client(monkeypatch, _FakeAsyncClient())

    await client.remove_tenant_subdomain(
        "acme",
        correlation_ctx=CorrelationContext(correlation_id=uuid4()),
    )
    remove_calls = [
        c for c in audit.calls if c["event_type"] == "tenants.dns.records_removed"
    ]
    assert len(remove_calls) == 1
    assert sorted(remove_calls[0]["payload"]["deleted_record_ids"]) == [
        "rec-1",
        "rec-2",
        "rec-3",
    ]


@pytest.mark.asyncio
async def test_base_ensure_records_facade_calls_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The deprecated ``ensure_records`` facade splits the input on ``.``
    and delegates to ``create_tenant_subdomain``. A ``DeprecationWarning``
    fires on call.
    """
    client = MockDnsAutomationClient()
    with pytest.warns(DeprecationWarning):
        await client.ensure_records("acme.musematic.ai")
    # The facade extracted the slug "acme" and recorded a create.
    assert client.actions[-1][0] == "create"
    assert client.actions[-1][1] == "acme"


@pytest.mark.asyncio
async def test_hetzner_base_ensure_records_facade(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise the inherited ``_DnsAutomationBase.ensure_records`` via
    a Hetzner client (the Mock overrides it). The facade calls
    ``create_tenant_subdomain``.
    """
    settings = _MinimalSettingsShim()
    client = HetznerDnsAutomationClient(
        settings=settings,  # type: ignore[arg-type]
        api_token="dummy",
        zone_id="zone-x",
        ipv4_address="192.0.2.1",
    )

    async def _instant_sleep(*_a: Any, **_kw: Any) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _instant_sleep)
    monkeypatch.setattr(
        "platform.tenants.dns_automation._resolve_via",
        lambda host, resolver: ["192.0.2.1"],
    )

    counter = {"n": 0}

    class _R:
        def __init__(self, code: int, payload: dict[str, Any] | None = None) -> None:
            self.status_code = code
            self._p = payload or {}

        def json(self) -> dict[str, Any]:
            return self._p

        def raise_for_status(self) -> None:
            return None

    class _FakeAsyncClient:
        async def post(self, *_a: Any, **_kw: Any) -> _R:
            counter["n"] += 1
            return _R(200, {"record": {"id": f"rec-{counter['n']}"}})

    _stub_async_client(monkeypatch, _FakeAsyncClient())

    with pytest.warns(DeprecationWarning):
        await client.ensure_records("acme.musematic.ai")
    assert counter["n"] >= 1


@pytest.mark.asyncio
async def test_hetzner_create_422_idempotent_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 422 "record already exists" on POST is treated as success: the
    client lists records and resolves the existing record id.
    """
    settings = _MinimalSettingsShim()
    client = HetznerDnsAutomationClient(
        settings=settings,  # type: ignore[arg-type]
        api_token="dummy",
        zone_id="zone-x",
        ipv4_address="192.0.2.1",
    )

    async def _instant_sleep(*_a: Any, **_kw: Any) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _instant_sleep)

    class _R:
        def __init__(self, code: int, payload: dict[str, Any] | None = None) -> None:
            self.status_code = code
            self._p = payload or {}

        def json(self) -> dict[str, Any]:
            return self._p

        def raise_for_status(self) -> None:
            return None

    class _FakeAsyncClient:
        async def post(self, *_a: Any, **_kw: Any) -> _R:
            return _R(422)

        async def get(self, *_a: Any, **_kw: Any) -> _R:
            return _R(
                200,
                {"records": [{"id": "rec-pre", "name": "acme", "type": "A"}]},
            )

    record = await client._create_record(
        _FakeAsyncClient(),  # type: ignore[arg-type]
        name="acme",
        rtype="A",
        value="192.0.2.1",
    )
    assert record.hetzner_record_id == "rec-pre"


@pytest.mark.asyncio
async def test_hetzner_remove_emits_failed_audit_on_exhausted_delete_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A persistent 5xx response on ``DELETE /records/{id}`` raises
    ``DnsAutomationFailedError`` and emits ``tenants.dns.records_failed``
    via the outer remove try/except.
    """
    settings = _MinimalSettingsShim()
    audit = _AuditChainSpy()
    client = HetznerDnsAutomationClient(
        settings=settings,  # type: ignore[arg-type]
        api_token="dummy",
        zone_id="zone-x",
        ipv4_address="192.0.2.1",
        audit_chain=audit,  # type: ignore[arg-type]
    )

    async def _instant_sleep(*_a: Any, **_kw: Any) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _instant_sleep)

    class _R:
        def __init__(self, code: int, payload: dict[str, Any] | None = None) -> None:
            self.status_code = code
            self._p = payload or {}

        def json(self) -> dict[str, Any]:
            return self._p

        def raise_for_status(self) -> None:
            return None

    list_payload = {"records": [{"id": "rec-1", "name": "acme", "type": "A"}]}

    class _FakeAsyncClient:
        async def get(self, *_a: Any, **_kw: Any) -> _R:
            return _R(200, list_payload)

        async def delete(self, *_a: Any, **_kw: Any) -> _R:
            return _R(503)

    _stub_async_client(monkeypatch, _FakeAsyncClient())

    with pytest.raises(DnsAutomationFailedError):
        await client.remove_tenant_subdomain(
            "acme",
            correlation_ctx=CorrelationContext(correlation_id=uuid4()),
        )
    failed = [c for c in audit.calls if c["event_type"] == "tenants.dns.records_failed"]
    assert len(failed) == 1
    assert failed[0]["payload"]["operation"] == "remove"


@pytest.mark.asyncio
async def test_hetzner_delete_request_error_retries_then_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``httpx.RequestError`` during DELETE should retry up to the budget
    and then raise ``DnsAutomationFailedError``.
    """
    settings = _MinimalSettingsShim()
    client = HetznerDnsAutomationClient(
        settings=settings,  # type: ignore[arg-type]
        api_token="dummy",
        zone_id="zone-x",
        ipv4_address="192.0.2.1",
    )

    async def _instant_sleep(*_a: Any, **_kw: Any) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _instant_sleep)

    class _AlwaysFailingClient:
        async def delete(self, *_a: Any, **_kw: Any) -> Any:
            raise httpx.RequestError("network down", request=None)  # type: ignore[arg-type]

    with pytest.raises(DnsAutomationFailedError):
        await client._delete_record(_AlwaysFailingClient(), "rec-1")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_emit_audit_no_op_when_audit_chain_unset() -> None:
    """``_emit_audit`` is a no-op when ``audit_chain`` is None — used by
    the dev profile where the mock has no audit-chain wiring.
    """
    client = MockDnsAutomationClient()  # audit_chain default None
    # Should not raise even though audit_chain is None.
    await client.create_tenant_subdomain(
        "acme",
        correlation_ctx=CorrelationContext(correlation_id=uuid4()),
    )


@pytest.mark.asyncio
async def test_hetzner_persistent_5xx_raises_after_retry_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A persistent 5xx response on ``POST /records`` must exhaust the
    4-attempt retry budget and raise ``DnsAutomationFailedError``.
    """
    settings = _MinimalSettingsShim()
    client = HetznerDnsAutomationClient(
        settings=settings,  # type: ignore[arg-type]
        api_token="dummy",
        zone_id="zone-x",
        ipv4_address="192.0.2.1",
    )

    async def _instant_sleep(*_a: Any, **_kw: Any) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _instant_sleep)

    call_count = {"n": 0}

    class _FakeResponse:
        status_code = 503

        def json(self) -> dict[str, Any]:
            return {}

        def raise_for_status(self) -> None:
            return None

    class _FakeAsyncClient:
        async def post(self, *_a: Any, **_kw: Any) -> _FakeResponse:
            call_count["n"] += 1
            return _FakeResponse()

    with pytest.raises(DnsAutomationFailedError):
        await client._create_record(
            _FakeAsyncClient(),  # type: ignore[arg-type]
            name="acme",
            rtype="A",
            value="192.0.2.1",
        )
    # 4 attempts exhausted, then raise.
    assert call_count["n"] == 4
