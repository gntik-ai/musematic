# Quick Start

The fastest local path is the kind-based developer environment driven by `make dev-up`. The steady-state target is about 5 minutes after images and dependencies are cached; a first cold-cache run can take longer while Docker images, Helm dependencies, and local build artifacts are pulled.

## Prerequisites

| Tool | Minimum | Notes |
| --- | --- | --- |
| Docker | 24.x | Docker Desktop or Linux Docker Engine with enough memory for the data stack. |
| kind | 0.23 | Used for the local Kubernetes cluster. |
| kubectl | 1.28 | Should match or be within one minor version of the kind node image. |
| Helm | 3.14 | Used by `make dev-up` to install platform charts. |
| Python | 3.12 | Needed for control-plane local tooling and scripts. |

## Run

```bash
git clone https://github.com/gntik-ai/musematic.git
cd musematic
make dev-up
```

The target creates the local cluster, loads or builds images, installs data services, deploys the platform chart, and waits for the main services to become available.

## Verify

```bash
kubectl get pods -A
kubectl get svc -A
```

Open the local app at `http://localhost:8080` when the UI service is exposed. If the control plane is still starting, wait for migrations and data-service readiness before retrying.

## Next

After the local environment is running, complete the [First Tutorial](first-tutorial.md) or read the full [kind installation guide](../installation/kind.md) for seed data, observability, and troubleshooting details. FR-606 tracks the kind installation target.
