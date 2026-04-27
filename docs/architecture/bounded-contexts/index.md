# Bounded Contexts

Each bounded context owns its model, service logic, REST surface, event contracts, and migrations. The pages in this catalog summarize operational ownership.

| Context | Primary Responsibility |
| --- | --- |
| [Auth](auth.md) | Login, tokens, MFA, sessions, service accounts. |
| [Accounts](accounts.md) | Signup, invitations, user lifecycle. |
| [Workspaces](workspaces.md) | Workspace membership, goals, visibility. |
| [Registry](registry.md) | Agent profiles, revisions, lifecycle. |
| [Governance](governance.md) | Policy compile and enforcement. |
| [Audit](audit.md) | Audit chain and attestations. |
| [Notifications](notifications.md) | Delivery channels and dead letters. |
| [Workflows](workflows.md) | Workflow definitions and triggers. |
| [Execution](execution.md) | Execution state, approvals, scheduling. |
| [Runtime](runtime.md) | Runtime pod lifecycle. |
| [Reasoning](reasoning.md) | Reasoning orchestration and budget. |
| [Sandbox](sandbox.md) | Isolated code execution. |
| [Simulation](simulation.md) | Simulation and digital twin execution. |
| [Analytics](analytics.md) | Analytics rollups and recommendations. |
| [Cost Governance](cost-governance.md) | Budgets, chargeback, anomalies. |
| [Incident Response](incident-response.md) | Incidents, integrations, runbooks. |
| [Multi-Region Ops](multi-region-ops.md) | Region config and failover plans. |
| [Security Compliance](security-compliance.md) | Evidence, vulnerability gates, audit mapping. |
| [Privacy Compliance](privacy-compliance.md) | DSR, residency, DLP, consent. |
| [Model Catalog](model-catalog.md) | Model entries, fallback, provider routing. |
| [Interactions](interactions.md) | Conversations, messages, attention. |
| [Fleets](fleets.md) | Fleet membership, learning, governance. |
| [Evaluation](evaluation.md) | Semantic testing and ATE. |
| [Trust](trust.md) | Certification, moderation, policy review. |
| [Connectors](connectors.md) | Connector routes and external delivery. |
| [Memory](memory.md) | Memory entries, embeddings, knowledge. |
| [Context Engineering](context-engineering.md) | Context assembly and quality. |
| [Discovery](discovery.md) | Marketplace search and experiments. |
| [Testing](testing.md) | E2E and regression testing APIs. |
| [Observability](observability.md) | Metrics, logs, traces, dashboards. |
