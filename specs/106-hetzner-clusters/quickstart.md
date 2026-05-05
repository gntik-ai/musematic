# UPD-053 — Quickstart (operator runbook)

End-to-end provisioning of `musematic-prod` from an empty Hetzner Cloud project. Total wall-clock target: **≤ 30 minutes** (SC-001). Dev provisioning follows the same shape with the dev tfvars; differences are noted inline.

## Prerequisites

- Hetzner Cloud account with billing enabled.
- Hetzner DNS account with the apex zone `musematic.ai` registered (one-time; production cluster bootstrap will own the zone records).
- Vault deployed and reachable from the operator workstation.
- Cloudflare Pages project `status-musematic-ai` created (per `docs/operations/cloudflare-pages-status.md`).
- Operator workstation: `terraform >= 1.6`, `helm >= 3.14`, `kubectl >= 1.29`, `vault` CLI, `gh` CLI.

## 1. Seed Vault

```bash
# Hetzner Cloud API token (server provisioning) — used by terraform via env var, not Vault
export HCLOUD_TOKEN=$(read -s 'Hetzner Cloud API token: ')

# Hetzner DNS API token (zone management) — stored in Vault, scoped to musematic.ai
vault kv put secret/musematic/prod/dns/hetzner/api-token \
  token="$(read -s 'Hetzner DNS API token: ')"

# Cloudflare Pages API token (status page push) — stored in Vault
vault kv put secret/musematic/prod/cloudflare/pages-token \
  token="$(read -s 'Cloudflare Pages API token: ')"

# Stripe API key + webhook signing secret (UPD-052 — already in place if you ran UPD-052; re-paste if not)
vault kv put secret/musematic/prod/billing/stripe/api-key \
  key="$(read -s 'Stripe live API key sk_live_*: ')"
vault kv put secret/musematic/prod/billing/stripe/webhook-secret \
  active="$(read -s 'Stripe webhook signing secret whsec_*: ')" \
  previous=""
```

## 2. Provision infrastructure (Terraform)

```bash
cd terraform/environments/production
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars: cluster_name, location, network_zone, ssh_public_key_file, firewall_allowed_cidrs

terraform init
terraform apply -var-file=terraform.tfvars
# wall-clock: ~5 min for servers + LB; another ~30s for DNS records
```

Terraform output yields:

```text
lb_ipv4 = "5.161.x.x"
lb_ipv6 = "2a01:4ff:..."
zone_id = "abc123..."
```

Record these values — they feed the Helm install in step 4.

For dev: `cd terraform/environments/dev` and apply with the dev tfvars. Different LB, different IPs, dev.* records under the shared zone.

## 3. Bootstrap the Kubernetes cluster

The hetzner-cluster module provisions the control plane and worker servers but does NOT bootstrap Kubernetes — that's a separate operator step. See [`docs/operations/hetzner-cluster-provisioning.md`](../../docs/operations/hetzner-cluster-provisioning.md) § "Bootstrap Kubernetes" for the two supported paths:

- **Option A — kubeadm by hand**: ssh to the control plane, `kubeadm init`, copy the join command to each worker, scp `admin.conf` back as `~/.kube/musematic-prod-config`. Wall-clock: ~10 min.
- **Option B — `hetzner-k3s`**: single-command k3s cluster bootstrap. Wall-clock: ~3 min.

Either path: install the Hetzner Cloud Controller Manager (CCM) and CSI driver after the cluster comes up — they read `HCLOUD_TOKEN` from a Secret synced from Vault. ingress-nginx is installed in step 4 below as part of the platform Helm release.

```bash
export KUBECONFIG=~/.kube/musematic-prod-config
kubectl get nodes   # 1 control plane + 3 workers, all Ready
```

## 4. Install the platform

```bash
cd deploy/helm/platform
helm dependency update
helm install platform . \
  -f values.prod.yaml \
  --set hetzner.dns.zone=musematic.ai \
  --set environment=prod \
  --create-namespace --namespace platform
# wall-clock: ~3 min for resource creation; another ~5 min for cert-manager to issue the wildcard cert
```

For dev: `helm install platform . -f values.dev.yaml --set environment=dev`.

## 5. Wait for cert + verify

```bash
# Watch the wildcard cert reach Ready
kubectl wait certificate/wildcard-musematic-ai \
  --for=condition=Ready --timeout=600s

# Verify ingress
curl -fsSL https://app.musematic.ai/healthz   # → 200 OK with valid cert chain
curl -fsSL https://api.musematic.ai/healthz   # → 200 OK
curl -fsSL https://grafana.musematic.ai/api/health   # → 200 OK
```

If the cert never reaches Ready: check `kubectl describe certificate wildcard-musematic-ai` for the `Order` / `Challenge` failure. The most common cause is the Hetzner DNS API token in Vault not having `DNS:Edit` scope on the zone.

## 6. Provision the first Enterprise tenant

```bash
# Via the admin workbench (preferred):
open https://app.musematic.ai/admin/tenants/new

# Or via the API:
curl -X POST https://api.musematic.ai/api/v1/admin/tenants \
  -H "Authorization: Bearer $SUPERADMIN_JWT" \
  -d '{"slug":"acme","display_name":"Acme Corp","region":"eu-central", ...}'
```

Within 5 minutes:

```bash
dig +short acme.musematic.ai @1.1.1.1        # → LB IPv4
dig +short acme.api.musematic.ai @1.1.1.1
dig +short acme.grafana.musematic.ai @1.1.1.1
curl -fsSL https://acme.musematic.ai/healthz # → 200 OK with the wildcard cert
```

## 7. Verify status page is independent

```bash
# Scale ingress to 0 to simulate a cluster-edge outage
kubectl -n ingress-nginx scale deployment/ingress-nginx-controller --replicas=0

# Status page should remain reachable from outside the cluster
curl -fsSL https://status.musematic.ai/  # → 200 OK with stale-but-reachable content

# Restore
kubectl -n ingress-nginx scale deployment/ingress-nginx-controller --replicas=2
```

## Smoke tests

`tests/e2e/journeys/test_j29_hetzner_topology.py` (NEW under this feature) packages the full provisioning flow into an automated smoke test runnable against a freshly created Hetzner project:

```bash
pytest tests/e2e/journeys/test_j29_hetzner_topology.py -v
```

The journey is `skip-marked` by default — operators opt in by setting `RUN_J29=1` after seeding Hetzner credentials. Skipped in CI; runnable on operator laptops or a dedicated provisioning runner.

## Common pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| `helm install` hangs at `cert-manager-webhook-hetzner` not reaching Ready | Vault → ExternalSecret not synced yet | Check `kubectl get externalsecret hetzner-dns-token`; manually trigger `kubectl annotate externalsecret hetzner-dns-token force-sync=$(date +%s) --overwrite` |
| Wildcard cert stuck in `Pending` for >10 min | Hetzner DNS-01 challenge can't reach the API (token scoped wrong) | Re-issue the token with both `Zones:Read` and `Records:Edit` on `musematic.ai`; rotate via `vault kv put` |
| `acme.musematic.ai` doesn't resolve after tenant creation | Hetzner DNS API rate limit or transient 5xx | Check `tools/verify_audit_chain.py --tenant acme` for `tenants.dns.records_failed` entries; retry via `POST /api/v1/admin/tenants/acme/redo-dns` |
| `helm install --dry-run` in CI fails with `no matches for kind Certificate` | kind cluster missing cert-manager CRDs | The e2e job's prerequisite step installs `cert-manager.yaml`; verify the step is present |

## Tear-down

```bash
helm uninstall platform --namespace platform
kubectl delete namespace platform ingress-nginx
cd terraform/environments/production && terraform destroy -var-file=terraform.tfvars
# Cloudflare Pages project is operator-managed; delete via dashboard if no longer needed.
# Vault paths persist by default — operator decides whether to delete.
```
