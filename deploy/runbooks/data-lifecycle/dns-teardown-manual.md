# DNS teardown - manual cleanup procedure

## When to use this runbook

A tenant cascade has completed (`data_lifecycle.tenant_deletion_completed` audit entry exists) but the cascade log shows `dns_teardown` with status `skipped` or `failed`. The tenant subdomain still resolves and/or the TLS certificate has not been revoked.

This is the documented manual fallback when:

- `FEATURE_UPD053_DNS_TEARDOWN=false` (UPD-053 has not landed yet), OR
- The UPD-053 service was unreachable at cascade time, OR
- The DNS provider rejected the teardown call.

## Pre-checks

Before manually tearing down DNS, confirm the cascade itself completed:

```sql
SELECT phase, cascade_started_at, cascade_completed_at
FROM deletion_jobs
WHERE id = '<JOB_ID>';
```

`phase = 'completed'` is required. If not, run `tenant-deletion-failed-cascade.md` first.

## DNS record removal

Identify the tenant subdomain pattern. The default convention is `<slug>.musematic.ai` for production and `<slug>.dev.musematic.local` for kind dev clusters.

### Cloudflare (production default)

```bash
TENANT_SLUG=acme
ZONE_ID=$(curl -s -H "Authorization: Bearer $CF_TOKEN" \
  "https://api.cloudflare.com/client/v4/zones?name=musematic.ai" | jq -r '.result[0].id')

# Find the A and CNAME records matching the tenant subdomain.
curl -s -H "Authorization: Bearer $CF_TOKEN" \
  "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records?name=${TENANT_SLUG}.musematic.ai" \
  | jq -r '.result[] | "\(.id) \(.type) \(.name) -> \(.content)"'

# Delete each record:
RECORD_ID=<id-from-above>
curl -X DELETE -H "Authorization: Bearer $CF_TOKEN" \
  "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records/$RECORD_ID"
```

### AWS Route 53

```bash
HOSTED_ZONE_ID=$(aws route53 list-hosted-zones-by-name --dns-name musematic.ai. \
  --query 'HostedZones[0].Id' --output text)
aws route53 list-resource-record-sets --hosted-zone-id $HOSTED_ZONE_ID \
  --query "ResourceRecordSets[?starts_with(Name, '${TENANT_SLUG}.')]"
# Use a change batch with action DELETE for each entry.
```

### kind dev cluster

```bash
# Edit the local CoreDNS configmap or /etc/hosts mapping the slug.
kubectl edit configmap -n kube-system coredns
# Remove the tenant slug entries from the rewrite block.
```

## TLS certificate revocation

If the platform issues per-tenant TLS certificates via cert-manager:

```bash
kubectl get certificate -n platform -l "tenant-slug=$TENANT_SLUG"
kubectl delete certificate -n platform <certificate-name>
kubectl delete secret -n platform <secret-name>  # corresponding TLS secret
```

If certificates are issued by an external CA (e.g., Let's Encrypt without cert-manager), use that CA's revocation endpoint with the tenant's certificate serial number.

## Audit trail

After completing manual cleanup, append an audit-chain entry documenting it. From the control-plane pod:

```bash
kubectl exec -n platform deploy/control-plane -- python -c "
import asyncio
from platform.audit.dependencies import _build_audit_chain_service
async def emit():
    svc = await _build_audit_chain_service()
    await svc.append_with_payload(
        event_type='data_lifecycle.dns_teardown_manual_completed',
        payload={
            'tenant_id': '<TENANT_ID>',
            'tenant_slug': '$TENANT_SLUG',
            'operator': '<your-username>',
            'completed_at_iso': '$(date -u +%Y-%m-%dT%H:%M:%SZ)',
        },
    )
asyncio.run(emit())
"
```

## Verify

- `dig <tenant_slug>.musematic.ai` returns NXDOMAIN.
- The cert-manager `Certificate` resource is gone.
- The audit chain has the manual-teardown entry.

## Prevention

This runbook exists because the DNS leg is *intentionally* feature-flagged (R8). Once UPD-053 is live, switch `FEATURE_UPD053_DNS_TEARDOWN=true` in production Helm values. The platform will then run the teardown automatically and the manual procedure is reserved for the residual edge case where the DNS provider itself fails.
