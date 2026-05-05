# Hetzner Cluster Provisioning Runbook

> UPD-053 (106) — operator-facing runbook for taking an empty Hetzner Cloud
> project to a healthy production or development musematic cluster.
> Target wall-clock: ≤ 30 minutes (SC-001) for production from a freshly
> cloned repo.

The full step-by-step is in
`specs/106-hetzner-clusters/quickstart.md` (in the repo root, outside
the docs site); this runbook adds operator-specific notes and rollback
procedures that the spec quickstart intentionally omits.

## Prerequisites (one-time per Hetzner account)

1. **Hetzner Cloud account** with billing enabled. Generate a Cloud API
   token under *Security → API tokens* (full read/write scope).
2. **Hetzner DNS** with the apex zone `musematic.ai` registered (production
   uses the apex; dev shares it via the `dev.*` subtree). Generate a DNS
   API token under *DNS Console → API tokens* with **DNS Edit** scope on
   the zone.
3. **Vault** deployed and reachable from the operator workstation. Seed
   the Hetzner DNS token under
   `secret/data/musematic/{prod,dev}/dns/hetzner/api-token` (path layout:
   [`docs/configuration/vault-paths.md`](../configuration/vault-paths.md)).
4. **Cloudflare Pages** project `status-musematic-ai` created (production
   only — see [`cloudflare-pages-status.md`](./cloudflare-pages-status.md)).
5. **Operator workstation tools**: terraform ≥ 1.6, helm ≥ 3.14,
   kubectl ≥ 1.29, vault CLI, gh CLI.

## Production cluster (`musematic-prod`)

Sized 1× CCX33 control plane + 3× CCX53 workers + 1× lb21 LB
(eu-central / nbg1).

### 1. Provision infrastructure

```bash
cd terraform/environments/production
cp terraform.tfvars.example terraform.tfvars
# edit firewall_allowed_cidrs, ssh_public_key_file, cloudflare_pages_ipv4

export HCLOUD_TOKEN=$(vault kv get -field=token secret/musematic/prod/hcloud/api-token)
export HETZNER_DNS_API_TOKEN=$(vault kv get -field=token secret/musematic/prod/dns/hetzner/api-token)

terraform init
terraform apply -var-file=terraform.tfvars
```

Expected outputs:

```text
lb_ipv4 = "5.161.x.x"
lb_ipv6 = "2a01:4ff:..."
zone_id = "abc123..."
```

Record these — they feed `helm install` (`HETZNER_DNS_ZONE_ID`,
`TENANT_DNS_IPV4_ADDRESS`, `TENANT_DNS_IPV6_ADDRESS` env vars).

### 2. Bootstrap Kubernetes

The cluster nodes provisioned by Terraform need kubeadm bootstrap. There
are two supported paths; pick whichever fits your operator workflow:

**Option A — kubeadm by hand** (no extra tooling):

```bash
# On the control-plane server
ssh root@$(terraform output -raw control_plane_ipv4) <<'BOOT'
kubeadm init \
  --apiserver-advertise-address=10.0.0.2 \
  --pod-network-cidr=10.244.0.0/16 \
  --upload-certs
mkdir -p /root/.kube && cp /etc/kubernetes/admin.conf /root/.kube/config
kubectl apply -f https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml
BOOT

# Capture the join command emitted by kubeadm init
JOIN=$(ssh root@$(terraform output -raw control_plane_ipv4) \
  "kubeadm token create --print-join-command")

# Run JOIN on each worker
for IP in $(terraform output -json worker_ipv4s | jq -r '.[]'); do
  ssh root@$IP "$JOIN"
done

# Pull kubeconfig back to the operator workstation
mkdir -p ~/.kube
scp root@$(terraform output -raw control_plane_ipv4):/etc/kubernetes/admin.conf \
  ~/.kube/musematic-prod-config
sed -i "s|server: https://10.0.0.2:6443|server: https://$(terraform output -raw lb_ipv4):6443|" \
  ~/.kube/musematic-prod-config
export KUBECONFIG=~/.kube/musematic-prod-config
```

**Option B — `hetzner-k3s`** (fastest; ~3 minutes):

```bash
# https://github.com/vitobotta/hetzner-k3s
brew install hetzner-k3s   # or: docker run vitobotta/hetzner-k3s
hetzner-k3s create-cluster --config terraform/environments/production/cluster-config.yaml
```

Either path: confirm with `kubectl get nodes` showing 1 control plane +
3 workers `Ready`.

> NOTE: An Ansible playbook at `deploy/ansible/cluster-bootstrap/` was
> originally planned to wrap option A; the playbook is tracked
> separately and is NOT required for this feature. Use option A directly
> until the playbook lands.

### 3. Install cluster prerequisites (one-time per cluster)

cert-manager and the Hetzner DNS-01 webhook are NOT platform-chart
sub-dependencies (they install cluster-wide CRDs); install them first:

```bash
helm repo add jetstack https://charts.jetstack.io
helm repo update
helm install cert-manager jetstack/cert-manager \
  --version v1.16.0 \
  --namespace cert-manager --create-namespace \
  --set installCRDs=true

helm repo add cert-manager-webhook-hetzner \
  https://vadimkim.github.io/cert-manager-webhook-hetzner
helm install cert-manager-webhook-hetzner \
  cert-manager-webhook-hetzner/cert-manager-webhook-hetzner \
  --version 0.6.0 --namespace cert-manager
```

### 4. Install the platform

```bash
cd ../../deploy/helm/platform
helm install platform . \
  -f values.prod.yaml \
  --create-namespace --namespace platform \
  --set hetzner.dns.zone=musematic.ai \
  --set environment=prod
```

### 5. Wait for the wildcard cert

```bash
kubectl wait certificate/wildcard-musematic-ai \
  --namespace platform \
  --for=condition=Ready --timeout=600s
```

If the cert hangs in `Pending`:

- Check `kubectl describe certificate wildcard-musematic-ai` — look at the
  `Order` and `Challenge` events for the failure reason.
- Most common cause: the Hetzner DNS API token in Vault doesn't have
  **DNS Edit** scope. Rotate via `vault kv put secret/musematic/prod/dns/hetzner/api-token token=$NEW`
  then `kubectl annotate externalsecret hetzner-dns-token force-sync=$(date +%s) --overwrite`.

### 6. Smoke-test

```bash
curl -fsSL https://app.musematic.ai/healthz       # → 200 OK
curl -fsSL https://api.musematic.ai/healthz       # → 200 OK
curl -fsSL https://grafana.musematic.ai/api/health # → 200 OK
```

## Development cluster (`musematic-dev`)

Sized 1× CCX21 control plane + 1× CCX21 worker + 1× lb11 LB. Co-exists with
prod on the same Hetzner account in a physically separate cluster.

### Differences vs prod

| Aspect | Prod | Dev |
|---|---|---|
| Vault path prefix | `secret/data/musematic/prod/...` | `secret/data/musematic/dev/...` |
| Helm overlay | `values.prod.yaml` | `values.dev.yaml` |
| Hetzner zone | apex (musematic.ai) — created | apex shared, dev.* subtree only |
| LB type | `lb21` | `lb11` |
| Stripe | live mode | test mode |
| Status page | Cloudflare Pages | in-cluster (`webStatus.deployedHere=true`) |
| Expected monthly Hetzner spend | ~100% baseline | ~50% of prod (SC-002) |

The dev `terraform/environments/dev/main.tf` does NOT call `hetznerdns_zone`
(zone already exists from prod). Operator passes the prod zone id via
`-var shared_zone_id=...` so dev's `hetznerdns_record` resources land in
the existing zone:

```bash
cd terraform/environments/dev
cp terraform.tfvars.example terraform.tfvars
SHARED_ZONE_ID=$(cd ../production && terraform output -raw zone_id)
terraform apply -var="shared_zone_id=$SHARED_ZONE_ID" -var-file=terraform.tfvars
```

The remaining steps mirror production with the dev paths.

### Validating physical isolation

After both clusters are up, confirm a dev pod cannot reach prod:

```bash
kubectl --context=musematic-dev run isolation-check \
  --image=curlimages/curl --rm -it --restart=Never -- \
  curl -m 5 musematic-postgres-rw.platform-data.svc.cluster.local
# Expected: connection timeout (no shared private network)
```

This is also asserted automatically by
`tests/e2e/suites/hetzner_topology/test_dev_isolation.py` (skip-marked
journey; gated on `RUN_J29=1` to avoid CI accidental execution).

## Rollback

If `helm install` fails partway:

```bash
helm uninstall platform --namespace platform
kubectl delete namespace platform                # async; takes ~2 min
```

If terraform apply created infra you want to discard:

```bash
cd terraform/environments/{production,dev}
terraform destroy -var-file=terraform.tfvars
```

This deletes Hetzner resources but does NOT touch:

- Cloudflare Pages projects (manual cleanup).
- Vault secrets (operator decides whether to rotate).
- The apex zone if `create_zone=true` was used (dev's `create_zone=false`
  prevents accidental zone deletion; production's terraform destroy WILL
  delete the apex zone — *this is destructive of all DNS records*; export
  the zone first via the Hetzner DNS UI if a soft rollback is desired).

## Related runbooks

- [`wildcard-tls-renewal.md`](./wildcard-tls-renewal.md) — what to do when the
  cert-manager renewal alert fires.
- [`cloudflare-pages-status.md`](./cloudflare-pages-status.md) — status page
  push pipeline troubleshooting.
- [`helm-snapshot.md`](./helm-snapshot.md) — regenerating the CI snapshot
  fixtures after intentional chart changes.
