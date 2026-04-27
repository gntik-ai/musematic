# k3s Installation

The k3s path targets a single Ubuntu 22.04+ node for labs, edge deployments, and small demos per FR-607.

## Prerequisites

- Ubuntu 22.04 or newer.
- Root or sudo access.
- Public DNS if exposing the app.
- Helm 3.14+ and kubectl.

## Install k3s

```bash
curl -sfL https://get.k3s.io | sh -
sudo kubectl get nodes
```

k3s bundles Traefik by default. If you use a different ingress controller, disable Traefik during install and update Helm values accordingly.

## Add cert-manager

Install cert-manager and configure a DNS-01 issuer when using public TLS. For local-only labs, use a private CA and document trust-store requirements.

## Install Musematic

```bash
helm dependency update deploy/helm/platform
helm upgrade --install musematic deploy/helm/platform --namespace platform --create-namespace --wait
```

## Verify

Check pods, ingress, TLS, login, and a simple workflow execution. If data-store pods remain pending, inspect storage class and node disk pressure first.
