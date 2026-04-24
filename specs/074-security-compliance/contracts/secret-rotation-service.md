# Secret Rotation Service Contract

**Feature**: 074-security-compliance
**Module**: `apps/control-plane/src/platform/security_compliance/services/secret_rotation_service.py`
**Scheduler**: `workers/rotation_scheduler.py` + `workers/overlap_expirer.py`

## State machine

```
idle ──[scheduler fires at next_rotation_at]──▶ rotating
rotating ──[new cred provisioned in Vault]──▶ overlap
overlap ──[overlap_expirer after overlap_window_hours]──▶ finalising
finalising ──[old cred revoked in Vault]──▶ idle (with new last_rotated_at, next_rotation_at)
{any} ──[unexpected error]──▶ failed
failed ──[operator reconciles]──▶ idle
```

## Vault state key

`secret/data/musematic/{env}/rotating/{secret_name}`:

```json
{
  "current": "...",
  "previous": "...",
  "overlap_ends_at": "<ISO8601>",
  "rotation_id": "<UUID>"
}
```

During `overlap`, both `current` and `previous` are valid. After
`finalising`, `previous` is removed.

## RotatableSecretProvider interface

```python
class RotatableSecretProvider:
    async def get_current(self, secret_name: str) -> str: ...
    async def get_previous(self, secret_name: str) -> str | None: ...  # None outside overlap
    async def validate_either(
        self,
        secret_name: str,
        presented: str,
    ) -> bool:
        """True if presented matches current OR (during overlap) previous."""
```

Downstream services (DB clients, JWT verifiers, OAuth validators)
MUST call `validate_either` during the overlap window.

## REST endpoints

| Method + path | Purpose | Role |
|---|---|---|
| `GET /api/v1/security/rotations` | List schedules + states | `auditor`, `superadmin` |
| `POST /api/v1/security/rotations` | Create schedule | `superadmin` |
| `PATCH /api/v1/security/rotations/{id}` | Update interval / overlap | `superadmin` |
| `POST /api/v1/security/rotations/{id}/trigger` | Manual rotation | `superadmin` (2PA for emergency no-overlap) |
| `GET /api/v1/security/rotations/{id}/history` | Rotation history (audit-chain entries) | `auditor`, `superadmin` |

Emergency rotation with `skip_overlap: true` requires a required
second approver (2PA; rule 33).

## Invariants

- Rotation response never echoes the new secret (rule 44) — returns
  `{status, next_rotation_at, overlap_ends_at, rotation_id}`.
- Every state transition emits a `security.secret.rotated` Kafka event
  AND an audit chain entry (FR-020).
- Failure to provision new credential in Vault → state `failed`,
  audit chain entry, notification to `superadmin`, scheduler does not
  retry automatically.

## Test IDs

- **SR1** — happy path: idle → rotating → overlap → finalising →
  idle.
- **SR2** — dual-cred validation: during overlap, both current and
  previous pass `validate_either`.
- **SR3** — post-overlap rejection: after `finalising`, previous
  rejected.
- **SR4** — emergency no-overlap: 2PA approval required, old cred
  revoked immediately.
- **SR5** — Vault partial failure: state → failed, audit entry, no
  silent advance.
- **SR6** — zero failures under 100 req/s load during rotation
  (SC-007).
