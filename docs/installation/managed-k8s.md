# Managed Kubernetes

Use this guide for GKE, EKS, or AKS when you want a managed control plane per FR-609. The platform chart is the same; cloud-specific work is identity, networking, storage, ingress, and DNS.

## Shared Steps

1. Create a regional cluster with at least one system node pool and one worker node pool.
2. Configure cloud IAM for image pulls, DNS automation, load balancers, and object storage as needed.
3. Install ingress-nginx or the cloud-native ingress controller.
4. Install cert-manager with DNS-01 credentials.
5. Create storage classes suitable for data services.
6. Install observability and the platform Helm chart.
7. Bootstrap the super admin and run smoke tests.

## GKE

Use Workload Identity for DNS and storage integrations. Prefer regional clusters for production and choose storage classes with snapshot support.

## EKS

Use IAM Roles for Service Accounts, the AWS Load Balancer Controller if needed, and EBS CSI for persistent volumes. Keep security groups scoped to ingress and operator CIDRs.

## AKS

Use managed identities for DNS and storage, Azure Disk CSI for persistent volumes, and Azure-native load balancer integration where appropriate.

## Verification

Confirm canonical URLs, TLS, login, workflow execution, dashboards, backup target access, and alert delivery.
