# Tenant Provisioning Runbook

## Lenient to strict promotion

Keep `PLATFORM_TENANT_ENFORCEMENT_LEVEL=lenient` immediately after the tenant architecture migration. In lenient mode the control plane records rows in `tenant_enforcement_violations` when service-layer expectations and tenant-filtered reads diverge.

After seven consecutive days with zero rows in `tenant_enforcement_violations` under production traffic, promote to strict mode:

```bash
kubectl set env deployment/control-plane PLATFORM_TENANT_ENFORCEMENT_LEVEL=strict
kubectl rollout status deployment/control-plane
```

Verify the tenant Grafana dashboard shows normal resolver latency and zero RLS-enforcement violations after the rollout. If violations reappear, return to lenient mode, capture the offending query and bounded context, and keep strict promotion blocked until the owner fixes the tenant filter.

## OAuth callback provisioning

Enterprise tenants must register OAuth applications with callback URLs under their own subdomain, for example `https://acme.musematic.ai/auth/oauth/google/callback`. The default tenant uses `https://app.musematic.ai/auth/oauth/google/callback`.
