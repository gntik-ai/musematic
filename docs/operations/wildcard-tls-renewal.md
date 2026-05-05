# Wildcard TLS Renewal — Operator Runbook

**Owner**: Platform / On-call
**Feature**: UPD-053 (106) — Hetzner Production+Dev Clusters
**Last updated**: 2026-05-05

The wildcard certificates `wildcard-musematic-ai` (prod) and
`wildcard-dev-musematic-ai` (dev) are issued and auto-renewed by
[cert-manager](https://cert-manager.io) via the Hetzner DNS-01 webhook
(`cert-manager-webhook-hetzner`). Renewal is fully automatic; this
runbook is for the cases where the alert
`WildcardCertRenewalFailing` fires, where on-call needs to verify cert
health, or where a manual emergency renewal is required.

---

## 1. Verify cert health (everyday operation)

```sh
# Cert state and timestamps
kubectl get certificate -A
kubectl describe certificate wildcard-musematic-ai -n platform-edge

# When does it expire? (notAfter)
kubectl get certificate wildcard-musematic-ai -n platform-edge \
  -o jsonpath='{.status.notAfter}{"\n"}'

# When will cert-manager trigger renewal? (= notAfter - renewBefore)
kubectl get certificate wildcard-musematic-ai -n platform-edge \
  -o jsonpath='{.status.renewalTime}{"\n"}'
```

Healthy state: `Ready=True`, `notAfter` ≥ 30 days in the future,
`renewalTime` ≥ 1 day in the future.

The `tenants.yaml` Grafana dashboard ("Wildcard Cert Days-Until-Expiry"
panel) shows the same data graphically; alerts fire from the
`certmanager_certificate_expiration_timestamp_seconds` metric.

---

## 2. WildcardCertRenewalFailing fired — what to check

The alert fires after **2 consecutive failed renewal attempts** in the
last 15 minutes. Triage in the order below — the first three issues
account for ~95% of past failures.

### 2.1 Vault token rotation

The Hetzner DNS API token is read from Vault at
`secret/data/musematic/{env}/dns/hetzner/api-token` and synced into the
`hetzner-dns-token` Kubernetes Secret by the `external-secrets`
operator (UPD-040). If the Vault token rotated and the
`external-secrets` ServiceAccount lost access, sync stops and the
webhook can't authenticate.

```sh
# Check the ExternalSecret status:
kubectl get externalsecret hetzner-dns-token -n cert-manager
# Look for SecretSynced=True. If False, check:
kubectl describe externalsecret hetzner-dns-token -n cert-manager
# And the underlying SecretStore / ClusterSecretStore reachability.
```

If the token has rotated out-of-band:

```sh
vault kv put secret/musematic/prod/dns/hetzner/api-token \
  token="$NEW_HETZNER_TOKEN"
# external-secrets will pick it up within the configured refreshInterval.
```

### 2.2 Hetzner DNS API status

cert-manager submits a `_acme-challenge.musematic.ai` TXT record to
Hetzner DNS to prove zone ownership. Check Hetzner status at
[status.hetzner.com](https://status.hetzner.com) and the webhook logs:

```sh
kubectl logs -n cert-manager -l app.kubernetes.io/name=cert-manager-webhook-hetzner --tail=200
```

Common errors: `401 Unauthorized` (token rotated, see 2.1) or
`429 Too Many Requests` (rate-limited; back off 60s and retry).

### 2.3 Let's Encrypt rate-limit headroom

Let's Encrypt enforces 50 certs/registered-domain/week. The wildcard
collapses every per-tenant subdomain into a single cert so we should
have plenty of headroom, but a `failedValidations` storm during
incident response can chew through it. Check:

```sh
# cert-manager logs include the LE response headers when rate-limited.
kubectl logs -n cert-manager -l app.kubernetes.io/name=cert-manager --tail=500 | grep -i "rateLimit\|429"
```

If rate-limited: switch the issuer to the LE staging endpoint
(`https://acme-staging-v02.api.letsencrypt.org/directory`) until the
weekly window resets, then switch back. The staging issuer is fine for
dev; for prod, page the platform lead before flipping.

---

## 3. Manual emergency renewal

Only run this if cert-manager isn't auto-renewing AND the cert is < 7
days from expiry. It forces a re-issuance through the same webhook.

```sh
cmctl renew wildcard-musematic-ai -n platform-edge
# Watch progress:
kubectl get certificaterequests -n platform-edge -w
```

Expected wall-clock: ≤ 10 minutes (DNS-01 propagation dominates).
If it doesn't complete in 15 minutes, escalate to the platform lead.

---

## 4. Staging-issuer fallback for rate-limit recovery

When LE prod has rate-limited the registered domain:

```sh
# Edit the ClusterIssuer to point at the staging endpoint:
kubectl patch clusterissuer letsencrypt-prod --type='merge' -p '
spec:
  acme:
    server: https://acme-staging-v02.api.letsencrypt.org/directory
'
# Trigger renewal — this issues a staging cert (browsers will warn).
cmctl renew wildcard-musematic-ai -n platform-edge
# After the weekly LE window resets, flip back:
kubectl patch clusterissuer letsencrypt-prod --type='merge' -p '
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
'
cmctl renew wildcard-musematic-ai -n platform-edge
```

A staging cert briefly serving prod is preferable to having NO cert
at all when the existing one expires.

---

## 5. References

- [Hetzner Cluster Provisioning runbook](./hetzner-cluster-provisioning.md)
  (US1 + US2 — cluster bootstrap)
- [Cloudflare Pages status runbook](./cloudflare-pages-status.md)
  (US5 — status page outage independence)
- cert-manager docs: https://cert-manager.io/docs/usage/certificate/
- Hetzner DNS API docs: https://dns.hetzner.com/api-docs
