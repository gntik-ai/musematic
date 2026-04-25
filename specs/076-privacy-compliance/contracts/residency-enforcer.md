# Residency Enforcer Contract

**Feature**: 076-privacy-compliance
**Module**: `apps/control-plane/src/platform/privacy_compliance/services/residency_service.py`

## Enforcement point

`policies/gateway.py` visibility resolution (lines 45–68) — BEFORE FQN
pattern matching:

```python
async def resolve_effective_visibility(
    self,
    workspace_id: UUID,
    request_context: RequestContext,
) -> EffectiveVisibility:
    # NEW — residency gate
    residency = await self._residency.get_cached(workspace_id)
    if residency is not None:
        origin_region = request_context.origin_region or "unknown"
        if origin_region != residency.region_code and origin_region not in residency.allowed_transfer_regions:
            await self._audit_chain.append(
                audit_event_id=uuid4(),
                audit_event_source="privacy_compliance",
                canonical_payload=_residency_violation_payload(
                    workspace_id, origin_region, residency
                ),
            )
            raise ResidencyViolation(
                workspace_id=workspace_id,
                origin_region=origin_region,
                required_region=residency.region_code,
                allowed_transfer_regions=residency.allowed_transfer_regions,
            )
    # Existing visibility resolution proceeds unchanged
    return await self._resolve_existing(workspace_id, request_context)
```

## `origin_region` resolution

Priority (first non-empty wins):
1. `X-Origin-Region` header (set by ingress / sidecar in multi-region
   deployments).
2. `request.state.user["region_hint"]` (service-account calls can carry
   a region hint in their token claim).
3. `"unknown"` (fail-closed — unknown regions are treated as
   disallowed when residency is configured).

## Residency service API

```python
class ResidencyService:
    async def get_config(self, workspace_id: UUID) -> ResidencyConfig | None:
        """Returns None when unconfigured (backward compat, no restriction)."""

    async def get_cached(self, workspace_id: UUID) -> ResidencyConfig | None:
        """Read-through cache via Redis (60 s TTL)."""

    async def set_config(
        self,
        workspace_id: UUID,
        region_code: str,
        allowed_transfer_regions: list[str],
        *,
        actor: UUID,
    ) -> ResidencyConfig:
        """Set or update config; invalidates cache; audits."""

    async def delete_config(
        self,
        workspace_id: UUID,
        *,
        actor: UUID,
    ) -> None:
        """Remove restriction; invalidates cache; audits."""
```

## Valid region codes

Platform seed uses the AWS / Hetzner / GCP shorthand: `eu-central-1`,
`eu-west-1`, `us-east-1`, `us-west-2`, `ap-southeast-1`, etc. The
platform does NOT validate the exact region code against a known
list; operators declare their regions. Future work can ship a seeded
catalog (UPD-025 multi-region-ops).

## REST endpoints

Under `/api/v1/privacy/residency/*`:

| Method + path | Purpose | Role |
|---|---|---|
| `GET /api/v1/privacy/residency/{workspace_id}` | Get config | `platform_admin`, `superadmin`, `auditor`, `compliance_officer` |
| `PUT /api/v1/privacy/residency/{workspace_id}` | Set config | `platform_admin`, `superadmin` |
| `DELETE /api/v1/privacy/residency/{workspace_id}` | Remove restriction | `superadmin` (requires 2PA — residency removal is significant) |

## Audit chain + Kafka events

Every config change and every violation produces:
- Audit chain entry via UPD-024.
- Kafka event `privacy.residency.configured` / `privacy.residency.removed` / `privacy.residency.violated`.

## Unit-test contract

- **RE1** — no config → all regions pass.
- **RE2** — config `region_code=eu-central-1`, empty transfer list;
  query from `us-east-1` → `ResidencyViolation`.
- **RE3** — same config, query from `eu-central-1` → passes.
- **RE4** — config allows `eu-west-1`; query from `eu-west-1` passes.
- **RE5** — unknown region `X-Origin-Region: unknown` → fails.
- **RE6** — config change propagates within 60 s (cache TTL).
- **RE7** — delete config requires 2PA; single-approver rejected.
- **RE8** — violation produces audit chain entry + Kafka event.
