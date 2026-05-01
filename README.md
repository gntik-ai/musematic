# Musematic - Agentic Mesh Platform

[![Build](https://img.shields.io/github/actions/workflow/status/gntik-ai/musematic/ci.yml)](https://github.com/gntik-ai/musematic/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/gntik-ai/musematic)](./LICENSE)
[![Kubernetes](https://img.shields.io/badge/kubernetes-1.28%2B-blue)](https://kubernetes.io/releases/)
[![Version](https://img.shields.io/github/v/release/gntik-ai/musematic)](https://github.com/gntik-ai/musematic/releases)

> **Read this in other languages**: [English](./README.md) · [Español](./README.es.md) · [Italiano](./README.it.md) · [Deutsch](./README.de.md) · [Français](./README.fr.md) · [简体中文](./README.zh.md)

Musematic is an open platform for operating fleets of AI agents with production-grade governance, observability, evaluation, and cost control. It gives platform teams a Kubernetes-native control plane for registering agents, orchestrating multi-agent work, enforcing policy, measuring quality, tracing decisions, and moving workloads across local, lab, and managed-cluster environments.

## What is Musematic?

Musematic is a workflow engine and agent operations platform for teams building with autonomous and semi-autonomous AI systems. It provides the shared control plane around agents: identity, lifecycle, policy enforcement, runtime orchestration, context engineering, memory, evaluation, incident response, logs, metrics, traces, and budget governance.

The platform is built for engineering, product, security, and operations teams that need AI agents to run as accountable production workloads rather than one-off scripts. A workspace can register agents, compose workflows, run simulations, certify trust properties, observe reasoning traces, compare evaluation results, and enforce cost or safety policies before work reaches users or external systems.

Musematic is intentionally portable. The same system can run in local kind clusters, small k3s labs, Hetzner-backed production deployments, or managed Kubernetes environments. Its architecture separates a Python control plane from Go satellite services so operators can scale hot execution paths while keeping governance and audit behavior centralized.

Musematic now runs as a default-plus-Enterprise multi-tenant SaaS platform. Hostname resolution establishes tenant context before authentication, PostgreSQL RLS enforces tenant isolation, and platform-staff operations are separated under audited `/api/v1/platform/*` endpoints. See the [tenant architecture](./docs/saas/tenant-architecture.md) documentation and [tenant provisioning runbook](./deploy/runbooks/tenant-provisioning.md).

## Core capabilities

- **Agent lifecycle management**: register, revise, certify, decommission, and discover agents by fully qualified namespace.
- **Multi-agent orchestration**: coordinate workspace goals, workflows, fleets, approvals, retries, and hot-path execution.
- **Trust and compliance**: enforce policies through observers, judges, enforcers, audit trails, privacy controls, and evidence capture.
- **Reasoning**: run chain-of-thought, tree-of-thought, ReAct, debate, self-correction, and scaling-inference modes through the reasoning engine.
- **Evaluation**: score trajectories, run semantic tests, compare experiments, and track fairness or drift indicators.
- **Observability**: inspect metrics, logs, traces, dashboards, alerts, and audit-chain events across the platform.
- **Cost governance**: attribute spend per execution, enforce budgets, forecast usage, detect anomalies, and support chargeback.
- **Portability**: deploy on kind, k3s, Hetzner, managed Kubernetes, or bare metal with standard Helm workflows.

## Quick start

Five minutes to a local development install on a warm cache:

```bash
git clone https://github.com/gntik-ai/musematic.git
cd musematic
make dev-up
open http://localhost:8080
```

`make dev-up` creates or reuses the local kind-based environment, installs Helm charts, and seeds the test data used by the end-to-end harness. First runs may take longer while Docker images and chart dependencies are pulled.

Use these companion commands while developing:

```bash
make dev-logs
make dev-down
make dev-reset
```

See the [developer guide](./docs/developer-guide/) and [operator guide](./docs/operator-guide/) for deeper setup and operating details.

## Installation options

| Target | Use case | Guide |
|---|---|---|
| kind | Local development and CI-style end-to-end testing | [kind installation](./docs/installation/kind.md) |
| k3s | Single-node labs and small environments | [k3s installation](./docs/installation/k3s.md) |
| Hetzner with load balancer | Production-oriented self-managed clusters | [Hetzner installation](./docs/installation/hetzner.md) |
| GKE, EKS, or AKS | Managed Kubernetes deployments | [Managed Kubernetes installation](./docs/installation/managed-k8s.md) |

All installation modes use the same repository-owned Helm charts under `deploy/helm/` and the same control-plane contracts.

## Architecture at a glance

![Architecture diagram](./docs/assets/architecture-overview.svg)

Musematic uses a control-plane and satellite-services architecture. The Python control plane owns API orchestration, bounded-context services, policies, audit records, and integrations. Go satellite services own latency-sensitive runtime responsibilities: launching agent pods, sandboxing code execution, running reasoning modes, and managing simulations.

Kafka carries domain events between bounded contexts. PostgreSQL stores relational state, Redis holds hot counters and leases, Qdrant stores vector embeddings, Neo4j stores knowledge-graph relationships, ClickHouse stores analytical rollups, OpenSearch provides full-text search, and S3-compatible object storage holds larger artifacts.

The frontend is a Next.js application that consumes typed REST, WebSocket, and generated client contracts. Observability is first-class: Prometheus, Grafana, Jaeger, and Loki are part of the deployment model, and dashboards are checked into the Helm chart surface.

The platform is designed so governance remains centralized while execution remains scalable. Operators can add new bounded contexts or satellite capabilities without bypassing common identity, policy, telemetry, and audit behavior.

## Documentation

- [Administration Guide](./docs/admin-guide/)
- [Operator Guide](./docs/operator-guide/)
- [Developer Guide](./docs/developer-guide/)
- [User Guide](./docs/user-guide/)
- [Integrations](./docs/admin-guide/integrations.md)
- [Agent Builder Guide](./docs/developer-guide/building-agents.md)
- [System Architecture](./docs/system-architecture-v6.md)
- [Software Architecture](./docs/software-architecture-v6.md)
- [Tenant Architecture](./docs/saas/tenant-architecture.md)
- [Functional Requirements](./docs/functional-requirements-revised-v6.md)

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for contribution guidelines. That governance file is not part of UPD-038 and may be added by a follow-up repository administration task.

## License

See [LICENSE](./LICENSE) for license terms. If the file is absent in a checkout, treat the project as not yet carrying a declared open-source license until repository maintainers add one.

## Community and support

- Issues: [GitHub Issues](https://github.com/gntik-ai/musematic/issues)
- Discussions: use [GitHub Issues](https://github.com/gntik-ai/musematic/issues) until GitHub Discussions is enabled.
- Releases: [GitHub Releases](https://github.com/gntik-ai/musematic/releases)
- Security disclosure: see [SECURITY.md](./SECURITY.md) for responsible disclosure guidance.
