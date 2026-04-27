# kind Installation

The kind path is the local development path for FR-606. Use it when you need a disposable Kubernetes cluster on a laptop or CI worker.

## Prerequisites

Install Docker, kind, kubectl, Helm, and Python 3.12. Give Docker enough memory for PostgreSQL, Redis, Kafka, MinIO, Qdrant, Neo4j, ClickHouse, OpenSearch, and the control-plane services.

## Install

```bash
git clone https://github.com/gntik-ai/musematic.git
cd musematic
make dev-up
```

The target creates the cluster, builds or loads images, installs charts, and waits for readiness. Cold-cache setup can exceed the 5-minute quick-start goal because images and dependencies need to download.

## Verify

```bash
kubectl get pods -A
kubectl get ingress -A
```

Open `http://localhost:8080`, sign in with the configured bootstrap credential, and run a small workflow.

## Observability and Seed Data

Install or port-forward observability services when debugging local issues. Seed data should be limited to local or anonymized records; never import production data into kind.
