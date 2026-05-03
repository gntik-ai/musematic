# Cold-storage retention restore

## When to use this runbook

A regulator or auditor requests the audit-chain history of a deleted tenant. The data was purged from the live system, but the encrypted tombstone + cold-storage chain (S3 Object Lock COMPLIANCE mode, 7-year retention) holds the proof.

## Pre-checks

```bash
# Confirm the cold-storage bucket exists and has Object Lock enabled.
aws s3api get-bucket-versioning --bucket platform-audit-cold-storage \
  --endpoint-url $S3_ENDPOINT_URL
aws s3api get-object-lock-configuration --bucket platform-audit-cold-storage \
  --endpoint-url $S3_ENDPOINT_URL
```

Expected: `Versioning: Enabled`, `ObjectLockEnabled: Enabled`, `Mode: COMPLIANCE`, `Years: 7`.

## Locate the tenant tombstone

The cascade writes one tombstone JSON object per deleted tenant under
`tenant/<TENANT_ID>/tombstone-<UNIX_TS>.json`. List them:

```bash
aws s3 ls s3://platform-audit-cold-storage/tenant/<TENANT_ID>/ \
  --endpoint-url $S3_ENDPOINT_URL
```

If the tenant has multiple tombstones (operator extended grace, rolled back, then redid the deletion), the last one is the canonical proof of final purge.

## Download

```bash
mkdir -p /tmp/regulatory-restore-$(date +%s)
cd /tmp/regulatory-restore-*
aws s3 cp s3://platform-audit-cold-storage/tenant/<TENANT_ID>/ ./ --recursive \
  --endpoint-url $S3_ENDPOINT_URL
```

The objects are encrypted with the cold-storage KMS key (separate from the live audit chain key). Decrypt:

```bash
# Each object's KMS key id is in the object metadata.
aws s3api head-object --bucket platform-audit-cold-storage \
  --key tenant/<TENANT_ID>/tombstone-<TS>.json \
  --endpoint-url $S3_ENDPOINT_URL
```

The platform writes objects with SSE-KMS using the dedicated cold-storage key. Operators with KMS Decrypt permission on that key can read the object via the standard `aws s3 cp` flow without additional steps; the platform handles decryption transparently.

## Verify the chain

The tombstone payload is canonical JSON with:

```json
{
  "tenant_id": "...",
  "subject_user_id_hash": "sha256:...",
  "salt_version": 1,
  "entities_deleted": { "postgresql": 12345, "qdrant": 800, ... },
  "cascade_log": [ ... ],
  "created_at_iso": "...",
  "proof_hash": "sha256:..."
}
```

Verify integrity:

```bash
python -c "
import hashlib, json, sys
data = json.load(open(sys.argv[1]))
expected = data.pop('proof_hash')
canonical = json.dumps(data, sort_keys=True, separators=(',', ':'))
computed = 'sha256:' + hashlib.sha256(canonical.encode()).hexdigest()
print('VERIFIED' if computed == expected else f'MISMATCH (expected {expected}, got {computed})')
" tombstone-<TS>.json
```

## Restore live audit chain (if requested)

A regulator may request the full audit chain be re-loaded into a sandboxed inspection environment. **Never re-load into production.** Spin up an isolated control-plane instance against an empty PostgreSQL, then:

```bash
# The cascade log includes per-store-affected counts but NOT the deleted
# row data — that's the GDPR right-to-be-forgotten contract. Only the
# tombstone hashes prove deletion happened. Audit-chain entries that
# referenced the deleted tenant are intact in the cold-storage chain
# under a separate key prefix:
aws s3 ls s3://platform-audit-cold-storage/audit-chain/<TENANT_ID>/ \
  --endpoint-url $S3_ENDPOINT_URL

# Replay into the isolated instance:
python -m tools.replay_audit_chain --source-prefix tenant/<TENANT_ID> --target $TARGET_DB
```

## Compliance reporting

Append a final audit entry to the active chain documenting that the cold-storage data has been accessed:

```bash
kubectl exec -n platform deploy/control-plane -- python -c "
# ... AuditChainService.append('data_lifecycle.cold_storage_accessed', { ... }) ...
"
```

This entry is itself NOT covered by Object Lock retention (it's in the live chain), so it can be compared against the cold-storage entries to detect any read-without-record discrepancies.

## Prevention

- Object Lock COMPLIANCE mode prevents accidental deletion. There is no recovery from a manual `s3 rm` against a Compliance object.
- KMS keys backing the cold-storage bucket are separate from the live audit-chain keys (see `data_lifecycle.audit_cold_bucket` setting). Rotation of the live key MUST NOT cascade to cold-storage objects.
- The 7-year default retention is a legal baseline; some regimes require 10. Bump `dataLifecycle.coldStorage.retentionYears` in Helm values BEFORE the first prod release if your contract differs — Object Lock retention can only be extended after the fact, never reduced.
