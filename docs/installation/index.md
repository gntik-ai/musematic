# Installation

Musematic supports four primary deployment paths plus an air-gapped pattern.

| Path | Target | Time Target | Use When |
| --- | --- | --- | --- |
| [kind](kind.md) | Local laptop | 15 minutes after prerequisites | Development, demos, CI reproduction. |
| [k3s](k3s.md) | Single Ubuntu node | 30 minutes | Small labs and edge environments. |
| [Hetzner](hetzner.md) | Production Kubernetes on Hetzner Cloud | 3 hours | Cost-conscious production with owned cluster operations. |
| [Managed Kubernetes](managed-k8s.md) | GKE, EKS, or AKS | Cloud-dependent | Teams that prefer managed control planes. |
| [Air-Gapped](air-gapped.md) | Offline Kubernetes | Environment-dependent | Regulated or disconnected networks. |

All paths install the same platform Helm chart and should end with the same smoke tests: login, workspace load, agent registry access, simple workflow execution, and observability checks.
