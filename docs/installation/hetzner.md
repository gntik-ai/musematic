# Hetzner Installation

The Hetzner path is the flagship production guide for FR-608. It provisions infrastructure with Terraform, bootstraps Kubernetes with kubeadm, installs cluster add-ons, configures DNS and TLS, installs observability, deploys Musematic, bootstraps the super admin, and verifies production readiness.

## Prerequisites

- Hetzner Cloud project and API token.
- DNS control for the production domain.
- Terraform 1.6+.
- kubectl and Helm 3.14+.
- SSH key pair for operators.
- A workstation allowed by `firewall_allowed_cidrs`.

## Step 1: Terraform

Copy `terraform/environments/production/terraform.tfvars.example` to a local `terraform.tfvars`, set allowed CIDRs and SSH key path, then run:

```bash
cd terraform/environments/production
terraform init
terraform plan
terraform apply
```

Record the load balancer IPv4/IPv6 outputs. They become the DNS targets for the canonical URLs.

## Step 2: kubeadm Bootstrap

SSH to the control-plane node, install container runtime packages, disable swap, configure kernel modules, and run `kubeadm init`. Join worker nodes using the generated join command. Store kubeconfig at the module output path.

## Step 3: Addons

Install CNI, ingress controller, metrics-server, cert-manager, and storage components. Verify every node is `Ready` before installing data services.

## Step 4: DNS Records

Create records for:

- `app.musematic.ai`
- `api.musematic.ai`
- `grafana.musematic.ai`

Point records at the Hetzner load balancer and wait for propagation. Development environments should use the `dev.*.musematic.ai` pattern from the [URL Scheme](../configuration/url-scheme.md).

## Step 5: TLS

Configure cert-manager DNS-01 wildcard issuance. See [TLS Strategy](../configuration/tls-strategy.md). Do not proceed to production traffic until the certificate chain is valid for all canonical hosts.

## Step 6: Observability

Install the observability chart:

```bash
helm dependency update deploy/helm/observability
helm upgrade --install musematic-observability deploy/helm/observability --namespace platform-observability --create-namespace --wait
```

Verify Prometheus, Grafana, Loki, Promtail, and Jaeger pods.

## Step 7: Platform Helm Install

Create production values with real secret references and DNS settings, then install:

```bash
helm dependency update deploy/helm/platform
helm upgrade --install musematic deploy/helm/platform --namespace platform --create-namespace --wait
```

## Step 8: Super Admin Bootstrap

Set `PLATFORM_SUPERADMIN_PASSWORD_FILE` through a Kubernetes secret reference such as `superadmin.passwordSecretRef`. The bootstrap path creates or updates the super admin and records audit events.

## Step 9: Verification

Verify:

- `https://app.musematic.ai` loads.
- `https://api.musematic.ai` returns health.
- Grafana is reachable.
- Login works with super admin MFA enrollment.
- A workspace can run a simple workflow.
- Metrics, logs, traces, and audit events contain correlation IDs.

## Step 10: Production Hardening

- Enable NetworkPolicy defaults.
- Configure backups to Hetzner Storage Box or compatible object storage.
- Keep logs for 14 days hot and 90 days cold when required by policy.
- Route alerts to the on-call channel.
- Document node replacement and auto-recovery.
- Schedule periodic failover exercises if multi-region is enabled.

## Troubleshooting

| Issue | Diagnostic Steps | Remediation |
| --- | --- | --- |
| DNS propagation delay | Query authoritative nameservers and public resolvers. | Wait for TTL or fix records. |
| Let's Encrypt rate limit | Check cert-manager challenges and issuer events. | Use staging issuer while testing; wait for production limit reset. |
| Load balancer IP conflict | Compare DNS, service status, and Hetzner LB targets. | Reattach targets and update records. |
| Persistent volume pending | Inspect storage class, node disk, and PVC events. | Fix storage class or add node capacity. |
| kubeadm certificate expiry | Run certificate check on control-plane node. | Renew certs and restart affected components. |
| Worker time drift | Compare NTP status across nodes. | Restore time sync before retrying TLS or Kafka operations. |
