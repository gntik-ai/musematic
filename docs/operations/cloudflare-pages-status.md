# Cloudflare Pages Status Page — Operator Runbook

**Owner**: Platform / SRE
**Feature**: UPD-053 (106) — constitution rule 49 (status page operational independence)
**Last updated**: 2026-05-05

The production status page (`status.musematic.ai`) is deployed on
**Cloudflare Pages** rather than inside the platform Kubernetes cluster.
A `CronJob` inside the cluster pushes a snapshot of the status content to
Cloudflare Pages every 30 seconds (configurable via
`webStatus.pushIntervalSeconds`). When the cluster is fully down, the
LAST PUSHED CONTENT remains served by Cloudflare Pages with a
"last updated X minutes ago" badge — which is the user-visible
behaviour rule 49 requires.

Dev keeps the legacy in-cluster `web-status-deployment.yaml` for cost
(research R6).

---

## 1. Out-of-band setup (one-time, before `helm install` for prod)

### 1.1 Create the Cloudflare Pages project

1. Sign in to [Cloudflare Dashboard](https://dash.cloudflare.com).
2. **Workers & Pages → Create → Pages → Direct Upload**.
3. Project name: `status-musematic-ai`.
4. **Custom domains** → add `status.musematic.ai`. Cloudflare will walk
   you through the CNAME flattening for the apex subdomain.

### 1.2 Issue a Cloudflare API token

1. **My Profile → API Tokens → Create Token → Custom token**.
2. Permissions:
   - **Pages → Edit** — scope to the `status-musematic-ai` project.
   - **DNS → Edit** — scope to `musematic.ai` (only required for the
     initial CNAME flattening; can be downgraded after).
3. Copy the token to your password manager.

### 1.3 Seed Vault

```sh
vault kv put secret/musematic/prod/cloudflare/pages-token \
  token="$CF_PAGES_TOKEN"
```

The chart's `vaultstaticsecret-cloudflare-pages-token.yaml` template
syncs the token into a Kubernetes Secret named `cloudflare-pages-token`
(or whatever `webStatus.cloudflarePages.apiTokenSecretRef.name` is set
to in `values.prod.yaml`).

### 1.4 Provision the apex DNS

The apex `status.musematic.ai` is owned by Hetzner DNS (managed by
`terraform/modules/hetzner-dns-zone/`). The terraform variable
`cloudflare_pages_ipv4` should point to the Cloudflare Pages
A-record IPv4 returned by the custom-domain wizard. After
`terraform apply`, dig `status.musematic.ai` and confirm it resolves
to that IPv4 within ~5 minutes.

---

## 2. Routine verification

```sh
# CronJob ticks
kubectl -n platform-edge get cronjob | grep status-pages-push
kubectl -n platform-edge get jobs -l app.kubernetes.io/name=status-snapshot

# Logs of the most recent push
kubectl -n platform-edge logs --tail=200 \
  -l app.kubernetes.io/name=status-snapshot

# External reachability — should always work, even during cluster outages.
curl -I https://status.musematic.ai/
```

The "last updated" badge embedded in the rendered HTML reports the
push age. Healthy state: badge says < 2 × `pushIntervalSeconds`.

---

## 3. StatusPagePushStuck fired — what to check

The alert fires after **10 consecutive failed Job runs** in the last
15 minutes. The Cloudflare Pages deployment continues to serve the last
successful snapshot, so the page stays reachable; the concern is staleness.

### 3.1 Cloudflare API token expired or rotated out-of-band

```sh
kubectl -n platform-edge logs --tail=200 \
  -l app.kubernetes.io/name=status-snapshot | grep -i "401\|403\|unauthorized"

# Confirm the ExternalSecret synced the latest token:
kubectl -n platform-edge get externalsecret cloudflare-pages-token
kubectl -n platform-edge get secret cloudflare-pages-token \
  -o jsonpath='{.metadata.annotations.reconcile\.external-secrets\.io/data-hash}{"\n"}'
```

If the token rotated, `vault kv put` again per § 1.3 and wait for
`refreshInterval: 1h` to propagate (or `kubectl annotate` the
ExternalSecret to force-refresh).

### 3.2 Cloudflare API status

Check [www.cloudflarestatus.com](https://www.cloudflarestatus.com).
A degraded Cloudflare Pages region can stall `wrangler pages deploy`
without an authentication error.

### 3.3 The status renderer endpoint is unhealthy

```sh
# From inside the cluster:
kubectl -n platform exec deploy/control-plane -- \
  curl -fsS "${STATUS_API_INTERNAL_URL}/api/v1/internal/status_page/render" -o /tmp/probe.html
# Check size — if zero or HTML-error-page, the renderer is the problem.
```

If the renderer is sick, fall back to the dedicated VM (§ 4) until the
control plane is healthy again.

---

## 4. Fallback — dedicated Hetzner VM running nginx

Documented as the rule-49 backup posture: if Cloudflare Pages is in
extended outage AND the cluster is also down, switching DNS to a
pre-provisioned `nginx`-on-Hetzner VM keeps the page reachable.

```sh
# 4.1 Provision the VM (one-time; from terraform/environments/production):
terraform apply -target=module.status_fallback

# 4.2 Verify the fallback VM serves a saved snapshot:
curl -I http://<fallback-ipv4>/

# 4.3 DNS swap — in Hetzner DNS, edit the `status` A-record to point at
#     the fallback VM IPv4 (record value previously held by the
#     Cloudflare Pages apex; recorded in
#     terraform/environments/production/terraform.tfvars.example).
```

Revert when Cloudflare Pages recovers — `terraform apply` against
`production/main.tf` restores the canonical record.

---

## 5. References

- [Hetzner Cluster Provisioning runbook](./hetzner-cluster-provisioning.md)
- [Wildcard TLS Renewal runbook](./wildcard-tls-renewal.md)
- Cloudflare Pages docs: https://developers.cloudflare.com/pages/
- Wrangler CLI: https://developers.cloudflare.com/workers/wrangler/
