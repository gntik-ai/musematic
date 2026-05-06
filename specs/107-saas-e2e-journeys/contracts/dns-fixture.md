# Contract — `tests/e2e/fixtures/dns.py`

## Purpose

Provide a journey-test view of DNS records consistent with the runtime `DnsAutomationClient` Protocol from UPD-053. Two implementations behind a single interface; the default (mock) keeps PR CI hermetic, the opt-in (live) gives operators a way to validate the real Hetzner integration.

## Mode selection

| Mode | Trigger | Backed by |
|---|---|---|
| Mock (default) | No env var set | In-process state held inside `MockDnsProvider` |
| Live | `RUN_J29=1` | Real Hetzner DNS test zone (NEVER production `musematic.ai`) — fixture asserts the resolved zone id is the test zone before any call |

## Public surface

```python
from typing import Protocol

class DnsTestProvider(Protocol):
    """Mirrors apps/control-plane/src/platform/tenants/dns_automation.DnsAutomationClient
    so the journey assertions look identical against both modes.
    """

    async def create_tenant_subdomain(
        self,
        slug: str,
        *,
        ipv4: str,
        ipv6: str | None = None,
    ) -> list[TestDnsRecord]: ...

    async def remove_tenant_subdomain(self, slug: str) -> int:
        """Returns the count of records removed."""

    async def verify_propagation(
        self,
        host: str,
        *,
        expected_ipv4: str,
        timeout_seconds: int = 60,
    ) -> bool: ...

    async def list_records_for(self, slug: str) -> list[TestDnsRecord]:
        """SC-006 helper. Used by the orphan-detection step."""


def build_dns_test_provider(
    *,
    settings: PlatformSettings,
) -> DnsTestProvider:
    """Factory consulted by the journey conftest. Returns LiveHetznerDnsProvider
    when RUN_J29=1 AND the test-zone token is present in Vault; otherwise
    MockDnsProvider.
    """
```

## Implementations

### `MockDnsProvider`

- Pure in-process state (`dict[slug, list[TestDnsRecord]]`).
- `verify_propagation` consults the in-process dict and returns True when the requested host resolves; never sleeps.
- Side-effect: emits a deterministic `TestDnsRecord` set so journey assertions are stable across runs.

### `LiveHetznerDnsProvider`

- Uses `httpx.AsyncClient` against `dns.hetzner.com/api/v1` with the `Auth-API-Token` header populated from `secret/data/musematic/dev/dns/hetzner/api-token`.
- Per-zone serialisation via a `pytest-xdist` `filelock` keyed on the zone id; respects Hetzner's 1 req/s burst limit.
- `verify_propagation` polls a public resolver (default `1.1.1.1`, configurable via `DNS_PROPAGATION_RESOLVER`) every 5 seconds up to `timeout_seconds`; resolver errors are swallowed and treated as "not yet propagated" (mirrors the runtime client's behaviour).

## Hard guarantees

- **Production zone is forbidden.** Both providers refuse calls where `slug` is in the canonical reserved-slug set (mirrors the runtime `RESERVED_SLUGS` list).
- **Cross-mode parity.** A journey written against the Mock MUST behave identically against Live — the only diff is wall-clock latency. CI's nightly soak runs the suite in both modes; mismatched assertions cause a flake report.
- **Idempotent teardown.** `remove_tenant_subdomain` returns 0 (not raises) when the slug has no records.

## Failure modes & exceptions

| Exception | When | Handler expectation |
|---|---|---|
| `ProductionZoneRefusedError` | Live provider is asked to operate against `musematic.ai` instead of the test zone | Fixture refuses; the run aborts with a clear message and a pointer to the env-var setting |
| `LiveModeMissingTokenError` | `RUN_J29=1` set but Vault token is missing | Fixture refuses; the journey skips with a clear reason |
| `DnsPropagationTimeoutError` | `verify_propagation` returned False after `timeout_seconds` | Journey treats as a setup failure and bundles the resolver state |

## Cross-references

- Runtime Protocol: `apps/control-plane/src/platform/tenants/dns_automation.py:DnsAutomationClient` (UPD-053).
- Reserved-slug list: `apps/control-plane/src/platform/tenants/reserved_slugs.py`.
- The factory pattern mirrors `apps/control-plane/src/platform/tenants/dns_automation.build_dns_automation_client` so it stays familiar to anyone who's worked on the runtime DNS automation.
