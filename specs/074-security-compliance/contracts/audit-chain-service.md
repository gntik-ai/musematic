# Audit Chain Service Contract

**Feature**: 074-security-compliance
**Module**: `apps/control-plane/src/platform/audit/service.py`

## Interface

```python
class AuditChainService:
    async def append(
        self,
        audit_event_id: UUID,
        audit_event_source: str,       # 'auth' | 'a2a_gateway' | 'registry' | 'mcp' | 'security_compliance'
        canonical_payload: bytes,      # UTF-8 JSON with sorted keys
    ) -> AuditChainEntry:
        """Append one chain entry; returns entry with assigned sequence_number."""

    async def verify(
        self,
        start_seq: int | None = None,   # None → from genesis
        end_seq: int | None = None,     # None → to latest
    ) -> VerifyResult:
        """Walk entries, recompute each hash, return {valid, broken_at?, entries_checked}."""

    async def export_attestation(
        self,
        start_seq: int,
        end_seq: int,
    ) -> SignedAttestation:
        """Run verify(); sign attestation doc with Ed25519 key; return signed JSON."""

    async def get_public_verifying_key(self) -> str:
        """Return hex-encoded 32-byte Ed25519 public key for external verification."""
```

## Invariants

- **Append is synchronous** with the caller's transaction; failure of
  `append` fails the originating audit write (constitution rule 9).
- **Sequence numbers are monotonic** even under concurrent writers;
  enforced by `BIGSERIAL` + `UNIQUE` constraint (DB serialises on
  conflict; retry within 50 ms).
- **Previous hash lookup** uses `ORDER BY sequence_number DESC LIMIT 1`
  within the same transaction; cache on `chain:last_seq` Redis key
  with 5 s TTL as read-through optimisation (DB is authority).
- **Canonical payload hashing**: caller provides bytes; service
  hashes into `canonical_payload_hash` column and combines that immutable
  hash into `entry_hash` per data-model.md §1.1 formula.
- **RTBF cascade**: if the producing BC's audit row is deleted
  (tombstone), chain entry `audit_event_id` is set to NULL; chain
  remains intact because `audit_event_id` is not an `entry_hash`
  component. Tombstone replacement at payload-hash time is the producing
  BC's responsibility.

## REST endpoints (admin)

| Method + path | Purpose | Role |
|---|---|---|
| `GET /api/v1/security/audit-chain/verify` | Full-chain integrity check | `superadmin`, `auditor` |
| `GET /api/v1/security/audit-chain/verify?start_seq=&end_seq=` | Range check | `superadmin`, `auditor` |
| `POST /api/v1/security/audit-chain/attestations` | Export signed attestation for range | `superadmin`, `auditor` |
| `GET /api/v1/security/audit-chain/public-key` | Public verifying key (unauthenticated — rule 49 public) | none |

## Test IDs

- **AC1** — append: one entry, verify hash matches formula.
- **AC2** — append: three sequential entries, chain intact.
- **AC3** — verify: manually corrupt row → `{valid: false, broken_at: N}`.
- **AC4** — RTBF: delete source audit row → chain still valid.
- **AC5** — attestation signature: verify with external Ed25519 library.
- **AC6** — concurrent append: 1,000 parallel writes produce 1,000
  sequential rows with unique sequence numbers.
- **AC7** — performance: verify 1M entries in ≤ 60 s (SC-005).
