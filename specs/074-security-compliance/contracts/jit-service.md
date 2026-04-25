# JIT Credential Service Contract

**Feature**: 074-security-compliance
**Module**: `apps/control-plane/src/platform/security_compliance/services/jit_service.py`

## Grant lifecycle

```
pending ──[approver approves]──▶ approved ──[credential issued]──▶ active
pending ──[approver rejects]──▶ rejected (terminal)
active ──[expires_at reaches]──▶ expired (terminal)
active ──[admin revokes]──▶ revoked (terminal)
```

## Approver policy resolution (per D-010)

At `POST /jit-grants` time:

1. Look up matching policy from `jit_approver_policies` by
   `operation_pattern` (longest match wins; `*` fallback).
2. Reject if `requested_expiry_minutes > policy.max_expiry_minutes`.
3. Return `{grant_id, required_approvers, min_approvers,
   max_expiry_minutes}` so the UI shows the approval workflow.

At `POST /jit-grants/{id}/approve` time:

1. Verify approver != requester (rule 33; reject 403).
2. Verify approver carries at least one of `policy.required_roles`.
3. Verify `min_approvers` is met by this + prior approvals.
4. On final approver: issue short-lived JWT per D-009; set
   `status='approved'` + `issued_at` + `expires_at`.
5. Emit `security.jit.issued` + audit chain entry.

## JWT shape (per D-009)

```json
{
  "sub": "<requester_user_id>",
  "purpose": "<operation>:<free-text>",
  "jti": "<grant_id>",
  "exp": "<unix epoch>",
  "iss": "musematic"
}
```

Validators perform: `exp` check, then Redis lookup
`jit:revoked:{jti}` (revoked if key exists).

## REST endpoints

| Method + path | Purpose | Role |
|---|---|---|
| `POST /api/v1/security/jit-grants` | Request a grant | authenticated user |
| `GET /api/v1/security/jit-grants` | List (own + approver's pending) | authenticated user |
| `GET /api/v1/security/jit-grants/{id}` | Get grant | owner, approver, `auditor` |
| `POST /api/v1/security/jit-grants/{id}/approve` | Approve | per `required_roles` |
| `POST /api/v1/security/jit-grants/{id}/reject` | Reject with reason | per `required_roles` |
| `POST /api/v1/security/jit-grants/{id}/revoke` | Revoke active grant | `platform_admin`, `superadmin` |
| `POST /api/v1/security/jit-grants/{id}/usage` | Append usage record | grant holder (auto from downstream service) |
| `GET /api/v1/security/jit-approver-policies` | List policies | `auditor`, `superadmin` |

Usage audit (`POST .../usage`) appends `{timestamp, operation,
target, outcome}` to `jit_credential_grants.usage_audit` JSONB.

## Invariants

- Grants cannot be extended (FR-027); a new grant is required.
- A JIT JWT's `exp` is enforced by every validator; revocation
  enforced by Redis denylist.
- Every state transition emits Kafka event + audit chain entry.

## Test IDs

- **JT1** — request → approve → issued JWT valid.
- **JT2** — self-approval rejected with 403.
- **JT3** — wrong-role approval rejected with 403.
- **JT4** — post-expiry JWT rejected by downstream validator.
- **JT5** — revoked grant: Redis key set; validator rejects.
- **JT6** — usage audit populated with every action; visible to
  auditor.
- **JT7** — customer_data operation requires 2 approvers (per policy
  seed).
