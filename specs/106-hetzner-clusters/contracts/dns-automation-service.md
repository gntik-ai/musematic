# Contract — `DnsAutomationClient` Protocol (extended)

**Owner**: `apps/control-plane/src/platform/tenants/dns_automation.py` (existing file; this is an in-place extension).

**Brownfield baseline**: the file currently exposes `class DnsAutomationClient(Protocol)` with a single method `async def ensure_records(self, subdomain: str) -> None`. UPD-053 extends the Protocol with three new methods. The existing `ensure_records` becomes a thin facade for one release window so callers in older code paths continue to work.

## Protocol

```python
class DnsAutomationClient(Protocol):
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
        timeout_seconds: int = 60,
    ) -> bool: ...

    # DEPRECATED — kept for one release; calls create_tenant_subdomain(<basename>).
    async def ensure_records(self, subdomain: str) -> None: ...
```

## `DnsAutomationRecordSet` (returned by create)

```python
@dataclass(frozen=True)
class DnsAutomationRecordSet:
    slug: str
    records: list[DnsAutomationRecord]  # length 6 on success: 3 subdomains × {A, AAAA}
    propagation_verified: bool

@dataclass(frozen=True)
class DnsAutomationRecord:
    name: str          # e.g. "acme", "acme.api", "acme.grafana"
    record_type: str   # "A" | "AAAA"
    value: str         # IPv4 or IPv6
    hetzner_record_id: str
    ttl: int           # 300
```

## Behaviour

### `create_tenant_subdomain(slug, *, actor_id, correlation_ctx)`

1. **Reserved-slug guard**: if `slug` is in `tenants/reserved_slugs.RESERVED_SLUGS`, raise `ReservedSlugError`. (FR-786.)
2. **Per-(zone, slug) lock**: acquire an in-process `asyncio.Lock` keyed by `(zone_id, slug)` to serialise concurrent calls for the same slug. Concurrent calls for different slugs proceed in parallel.
3. **For each of `["{slug}", "{slug}.api", "{slug}.grafana"]` × `["A", "AAAA"]`**: `POST /records` to the Hetzner DNS API with the LB IPv4/IPv6 from settings, retrying on 5xx with exponential backoff (`1s → 2s → 4s → 8s`, ceiling 4 attempts; on permanent failure raise `DnsAutomationFailedError` with the partial record set so caller can persist a `degraded_dns` state). 422 "record already exists" is treated as success (idempotent re-run).
4. **Propagation check**: call `verify_propagation("{slug}.musematic.ai", expected_ipv4=settings.TENANT_DNS_IPV4_ADDRESS, timeout_seconds=60)`. On false, raise `DnsAutomationPropagationTimeoutError` (the records exist but resolvers haven't seen them yet — caller decides whether to surface a "DNS may take up to 5 minutes" warning or block).
5. **Audit chain**: emit one `tenants.dns.records_created` entry via `AuditChainService.append` carrying `{ slug, records: [{ name, type, hetzner_record_id }, ...], correlation_id, actor_id }`. No IPv4/IPv6 values in the audit row.
6. **Structured log**: emit `tenants.dns.records_created` (info) with the same fields plus duration.
7. **Return** the `DnsAutomationRecordSet` with `propagation_verified=True` (or False if step 4 timed out and the caller chose to swallow the exception).

### `remove_tenant_subdomain(slug, *, actor_id, correlation_ctx)`

1. **Per-(zone, slug) lock** (same as create).
2. **List + filter**: `GET /records?zone_id={settings.HETZNER_DNS_ZONE_ID}` and filter for `record.name in {slug, slug.api, slug.grafana}`.
3. **For each match**: `DELETE /records/{id}`, retrying on 5xx with the same backoff. 404 "record not found" is treated as success (idempotent re-run).
4. **Audit chain**: emit one `tenants.dns.records_removed` entry with `{ slug, deleted_record_ids, correlation_id, actor_id }`.
5. **Structured log**: emit `tenants.dns.records_removed`.
6. **Return** `None`.

### `verify_propagation(subdomain, *, expected_ipv4, timeout_seconds)`

1. Resolve `subdomain` against a public resolver (`1.1.1.1` by default; configurable via `settings.DNS_PROPAGATION_RESOLVER`) — NOT the Hetzner authoritative resolver, so we don't get fooled by Hetzner's own caches.
2. Poll every 5 seconds up to `timeout_seconds`.
3. Return `True` on first match of `expected_ipv4` in the answer; `False` on timeout.
4. On resolver error, log a warning and return `False` (don't crash the create path).

### `ensure_records(subdomain)` (deprecated)

Legacy single-record method. Implementation: call `create_tenant_subdomain(slug=subdomain.split('.')[0], correlation_ctx=CorrelationContext.empty())`. Logs a deprecation warning. Removed after one release.

## Failure modes & exceptions

| Exception | When | Handler expectation |
|---|---|---|
| `ReservedSlugError` (existing) | Slug in `RESERVED_SLUGS` | Caller (TenantsService) should refuse tenant creation upstream; raised here as defense-in-depth. |
| `DnsAutomationFailedError` (existing) | API call exhausts retry budget | Caller persists `degraded_dns` state; admin alert emitted via the existing notifications pipeline. |
| `DnsAutomationPropagationTimeoutError` (NEW) | Records created but resolver doesn't see them within `timeout_seconds` | Caller can either (a) accept and tell the user "DNS may take up to 5 minutes" or (b) block tenant `active` flip until next retry tick. Default policy: accept + warn. |

## Implementation reference

- The existing `HetznerDnsAutomationClient` and `MockDnsAutomationClient` get parity implementations of all three new methods. The mock stores `(slug, action)` tuples for assertion in unit tests.
- `dns_automation.py` ships with no LLM-bound serialization (the `__repr__` of the client redacts `api_token` to `***`).
- Settings reads (`HETZNER_DNS_API_TOKEN`, `HETZNER_DNS_ZONE_ID`, `TENANT_DNS_IPV4_ADDRESS`, `TENANT_DNS_IPV6_ADDRESS`) go through the existing `SecretProvider` for the token and through `PlatformSettings` for the rest.
- The factory `build_dns_automation_client(settings)` keeps its current behaviour: returns `MockDnsAutomationClient` for non-prod profiles unless all four config keys are populated.
