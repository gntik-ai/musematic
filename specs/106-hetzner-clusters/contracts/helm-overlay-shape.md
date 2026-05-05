# Contract — Helm overlay shape (`values.prod.yaml`, `values.dev.yaml`)

The platform chart at `deploy/helm/platform/` already ships with `values.yaml` (defaults), `values.prod.yaml` (extended by this feature), `values.dev.yaml` (extended by this feature), and `values-multi-region.yaml` (untouched). UPD-053 adds five new top-level blocks and extends two existing ones.

## NEW top-level blocks

### `hetzner`

```yaml
hetzner:
  loadBalancer:
    location: nbg1                  # Hetzner DC; eu-central zone is the default
    networkZone: eu-central
    usePrivateIp: true
    proxyProtocol: true             # prod only; dev sets false
    name: musematic-prod-lb         # dev: musematic-dev-lb
    type: lb21                      # dev: lb11
  dns:
    provider: hetzner
    apiTokenSecretRef:
      name: hetzner-dns-token       # synced from Vault by VaultStaticSecret
      key: token
    zone: musematic.ai              # dev shares the zone, operates on dev.* subtree
```

Consumed by:
- `templates/service-loadbalancer.yaml` (NEW): renders the Service-of-type-LoadBalancer for the ingress controller with `load-balancer.hetzner.cloud/*` annotations from `hetzner.loadBalancer`.
- `templates/certmanager-clusterissuer.yaml` (NEW): the DNS-01 webhook config block reads `hetzner.dns.zone` and `hetzner.dns.apiTokenSecretRef`.
- `tenants/dns_automation.py` (existing): reads `HETZNER_DNS_API_TOKEN`, `HETZNER_DNS_ZONE_ID`, `TENANT_DNS_IPV4_ADDRESS`, `TENANT_DNS_IPV6_ADDRESS` from settings, populated via Helm env vars.

### `certManager`

```yaml
certManager:
  enabled: true
  clusterIssuer:
    name: letsencrypt-prod          # MUST match the existing webStatus.tls.clusterIssuer
    email: ops@musematic.ai
    server: https://acme-v02.api.letsencrypt.org/directory
  hetznerDnsWebhook:
    enabled: true
    image: ghcr.io/vadimkim/cert-manager-webhook-hetzner:1.4.0
    groupName: acme.musematic.ai
  certificates:
    - name: wildcard-musematic-ai   # dev: wildcard-dev-musematic-ai
      secretName: wildcard-musematic-ai
      dnsNames:
        - "*.musematic.ai"          # dev: *.dev.musematic.ai
        - musematic.ai              # dev: dev.musematic.ai
      renewBefore: 720h             # 30 days
```

Consumed by:
- `templates/certmanager-clusterissuer.yaml` (NEW)
- `templates/certmanager-certificate-wildcard.yaml` (NEW; rendered once per entry in `certificates`)
- `Chart.yaml` `dependencies:` — `cert-manager` and `cert-manager-webhook-hetzner` charts are installed conditionally on `certManager.enabled`.

### `webStatus.deployedHere` / `webStatus.pushDestination` / `webStatus.pushIntervalSeconds`

EXTEND the existing `webStatus` block:

```yaml
webStatus:
  enabled: true
  # NEW: choose between in-cluster (dev) and external (prod)
  deployedHere: false             # prod: false (Cloudflare Pages); dev: true
  pushDestination: cloudflare-pages   # prod: cloudflare-pages; dev: none
  pushIntervalSeconds: 30         # prod: 30; dev: 60
  cloudflarePages:
    accountId: ""                  # set per-env in values.{prod,dev}.yaml
    projectName: status-musematic-ai
    apiTokenSecretRef:
      name: cloudflare-pages-token
      key: token
  host: status.musematic.ai       # dev: status.dev.musematic.ai
  # ... existing fields unchanged
```

Consumed by:
- `templates/web-status-deployment.yaml`, `templates/web-status-ingress.yaml` (existing): conditionally rendered when `deployedHere=true`.
- `templates/status-snapshot-cronjob.yaml` (EXTEND): on `deployedHere=false` and `pushDestination=cloudflare-pages`, the CronJob runs the push-to-Cloudflare-Pages flow instead of the in-cluster regenerate path.

### `ingress.wildcardHosts`

EXTEND the existing `ingress` block:

```yaml
ingress:
  className: nginx
  hosts: [...]                    # existing apex/app/api/grafana entries — unchanged
  wildcardHosts:                  # NEW
    - "*.musematic.ai"            # dev: *.dev.musematic.ai
  tls:
    - secretName: wildcard-musematic-ai     # dev: wildcard-dev-musematic-ai
      hosts:
        - "*.musematic.ai"
        - musematic.ai
```

Consumed by:
- `templates/ingress-platform.yaml` (EXTEND): adds a wildcard rule that routes `/api/*` to the control-plane Service and `/*` to the frontend Service. The hostname-extraction middleware (UPD-046) extracts the tenant slug from the request `Host:`.

### `billing.stripe.webhookUrl`

EXTEND the existing UPD-052 `billingStripe` block:

```yaml
billingStripe:
  provider: stripe
  stripeMode: live              # dev: test
  stripeApiVersion: "2024-06-20"
  webhookUrl: https://api.musematic.ai/api/webhooks/stripe   # dev: https://dev.api.musematic.ai/api/webhooks/stripe
```

Consumed by:
- `deployment-control-plane.yaml` (existing): exports `BILLING_STRIPE_WEBHOOK_URL` as an env var; control-plane registers the URL with Stripe at startup.

## What `values.prod.yaml` ends with (post-merge)

```yaml
# preserved from UPD-046/047/052 (do not remove):
tenancy: { ... }                # UPD-046 (096) — unchanged
billing: { ... }                # UPD-047 (097) — unchanged
billingStripe:                  # UPD-052 (105) — webhookUrl ADDED
  provider: stripe
  stripeMode: live
  stripeApiVersion: "2024-06-20"
  webhookUrl: https://api.musematic.ai/api/webhooks/stripe
signup: { ... }
marketplace: { ... }
publicPages: { enabled: true }

# NEW from UPD-053 (106):
hetzner:
  loadBalancer: { location: nbg1, networkZone: eu-central, usePrivateIp: true, proxyProtocol: true, name: musematic-prod-lb, type: lb21 }
  dns: { provider: hetzner, apiTokenSecretRef: { name: hetzner-dns-token, key: token }, zone: musematic.ai }
certManager:
  enabled: true
  clusterIssuer: { name: letsencrypt-prod, email: ops@musematic.ai, server: https://acme-v02.api.letsencrypt.org/directory }
  hetznerDnsWebhook: { enabled: true, image: ghcr.io/vadimkim/cert-manager-webhook-hetzner:1.4.0, groupName: acme.musematic.ai }
  certificates:
    - { name: wildcard-musematic-ai, secretName: wildcard-musematic-ai, dnsNames: ["*.musematic.ai", "musematic.ai"], renewBefore: 720h }
ingress:
  wildcardHosts: ["*.musematic.ai"]
  tls: [{ secretName: wildcard-musematic-ai, hosts: ["*.musematic.ai", "musematic.ai"] }]
webStatus:
  deployedHere: false
  pushDestination: cloudflare-pages
  pushIntervalSeconds: 30
  cloudflarePages: { accountId: "", projectName: status-musematic-ai, apiTokenSecretRef: { name: cloudflare-pages-token, key: token } }
  host: status.musematic.ai
```

`values.dev.yaml` mirrors with the dev variants per the spec's US2.
