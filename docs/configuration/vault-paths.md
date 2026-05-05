# Vault Path Layout

> Canonical Vault paths used by the platform. Every secret read from these paths goes
> through the `SecretProvider` interface (constitution rules 11/39). No secrets reach
> code via `os.getenv` — see `apps/control-plane/src/platform/security_compliance/providers/`.

All paths use the KV v2 backend. The `secret/data/` prefix is implied by KV v2 — the
mount path is `secret/`. Operators read with `vault kv get secret/...` and write with
`vault kv put secret/...`.

## Path conventions

```text
secret/data/musematic/{env}/<bounded-context>/<resource>/<secret-name>
```

| Token | Values |
|---|---|
| `{env}` | `prod`, `dev`, `staging` |
| `<bounded-context>` | snake-cased BC name (e.g. `auth`, `billing`, `dns`, `cloudflare`) |
| `<resource>` | optional sub-grouping (e.g. `stripe` under `billing`) |
| `<secret-name>` | concrete secret (e.g. `api-key`, `webhook-secret`, `api-token`) |

## Active paths

### Auth / OAuth

| Path | Owner | Purpose |
|---|---|---|
| `secret/data/musematic/{env}/auth/jwt/private-key` | `auth/` | RS256 JWT signing key (rotated quarterly) |
| `secret/data/musematic/{env}/auth/oauth/google/client` | `auth/` | Google OAuth client id + secret |
| `secret/data/musematic/{env}/auth/oauth/github/client` | `auth/` | GitHub OAuth client id + secret |

### Billing (UPD-052)

| Path | Owner | Purpose |
|---|---|---|
| `secret/data/musematic/{env}/billing/stripe/api-key` | `billing/providers/stripe/` | Stripe API key (live or test mode per env) |
| `secret/data/musematic/{env}/billing/stripe/webhook-secret` | `billing/webhooks/` | Stripe webhook signing secret with `active` + `previous` keys for rotation |

### DNS automation (UPD-053)

| Path | Owner | Purpose |
|---|---|---|
| `secret/data/musematic/{env}/dns/hetzner/api-token` | `tenants/dns_automation.py`, cert-manager Hetzner DNS-01 webhook | Hetzner DNS API token scoped to the apex zone (`musematic.ai`). Used for per-tenant subdomain creation/removal AND for the cert-manager DNS-01 challenge. |

### Status page (UPD-053)

| Path | Owner | Purpose |
|---|---|---|
| `secret/data/musematic/{env}/cloudflare/pages-token` | `status_page/`, `templates/status-snapshot-cronjob.yaml` | Cloudflare Pages API token (scoped to the `status-musematic-ai` project + `DNS:Edit` for the apex zone for CNAME flattening). Production only — dev keeps the in-cluster status deployment per constitution rule 49 / UPD-053 research R6. |

### Database / Redis / Kafka

| Path | Owner | Purpose |
|---|---|---|
| `secret/data/musematic/{env}/postgres/dsn` | `common/database.py` | PostgreSQL DSN |
| `secret/data/musematic/{env}/redis/credentials` | `common/clients/redis.py` | Redis username + password |
| `secret/data/musematic/{env}/kafka/sasl` | `common/events/` | Kafka SASL credentials |

## Synced to Kubernetes Secrets

Some Vault paths are mirrored into Kubernetes Secrets via `external-secrets` operator
(installed by the `vault/` chart in UPD-040). The `ExternalSecret` resources are rendered
by the platform chart's `templates/vaultstaticsecret-*.yaml` files and reconcile every
hour by default.

| Vault path | Kubernetes Secret | Synced because |
|---|---|---|
| `dns/hetzner/api-token` | `hetzner-dns-token` | cert-manager Hetzner DNS-01 webhook reads from a Secret, not from Vault directly |
| `cloudflare/pages-token` | `cloudflare-pages-token` | The `wrangler` container in the status-page push CronJob reads from a Secret env-var |
| `billing/stripe/webhook-secret` | `stripe-webhook-secret` (UPD-052) | Webhook signature verification at request ingress |

## Rotation

Tokens marked rotation-capable rotate via `security_compliance/services/secret_rotation_service.py`
(constitution rule 10). Rotation flows write a new Vault version; the `external-secrets`
operator picks up the change within `refreshInterval` (1h ceiling). For the Hetzner DNS
token: the operator runs `vault kv put secret/musematic/prod/dns/hetzner/api-token token=$NEW`,
then forces a faster reconcile via
`kubectl annotate externalsecret hetzner-dns-token force-sync=$(date +%s) --overwrite`.

## See also

- `docs/configuration/environment-variables.md` — env-var settings that reference Vault paths.
- `docs/operator-guide/runbooks/vault-rotation.md` — rotation playbook.
- `docs/operator-guide/runbooks/vault-token-rotation.md` — Vault auth-token rotation.
- `docs/operator-guide/runbooks/vault-cache-flush.md` — cache flush after emergency rotation.
