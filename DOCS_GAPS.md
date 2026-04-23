# Docs Gaps

Tracker for every `TODO(andrea):` placeholder the docs site carries
after the initial scaffold. Resolve an entry by replacing the TODO with
grounded content; remove the row here once done.

The docs site is ready to deploy with these TODOs in place — they are
visible inline on each page so readers know the placeholder is
unresolved. See `docs/README.md` for contribution rules.

## Top-level pages

Substantive gaps on the end-user-facing and reference pages (home,
getting-started, installation, agents, flows, faq, roadmap, configuration
reference). These should be closed first — they are the pages most
readers land on.

- `docs/faq.md:55` — - `escalate` — TODO(andrea): confirm escalation wiring location.
- `docs/faq.md:98` — TODO(andrea): not at the repo root as of the current main branch.
- `docs/flows.md:362` — (TODO(andrea): confirm escalation wiring location in `workflows/models.py`).
- `docs/getting-started.md:35` — TODO(andrea): the repo does not currently ship a top-level
- `docs/installation.md:47` — from test fixtures. TODO(andrea): document the canonical local-dev
- `docs/installation.md:473` — TODO(andrea): the repo ships individual service-level troubleshooting notes
- `docs/reference/configuration.md:120` — TODO(andrea): the actual canonical `values.yaml` shape on main uses a
- `docs/roadmap.md:90` — TODO(andrea): walk the `Status:` headers of every `specs/*/spec.md`

## Administration section

Gaps in the platform-administrator pages. These are high-value to
close because they affect operators running the platform.

- `docs/administration/audit-and-compliance.md:42` — TODO(andrea): the constitution's audit-pass (v1.2.0) introduces a
- `docs/administration/audit-and-compliance.md:67` — TODO(andrea): confirm exact table names from migration files; the
- `docs/administration/backup-and-restore.md:57` — TODO(andrea): confirm the exact manifest schema and CLI subcommand
- `docs/administration/integrations-and-credentials.md:16` — | HashiCorp Vault | `vault` | TODO(andrea): the Vault adapter is declared but raises `NotImplementedError` as of the current main branch. |
- `docs/administration/integrations-and-credentials.md:86` — TODO(andrea): real Google + GitHub OAuth provider configuration is
- `docs/administration/integrations-and-credentials.md:107` — endpoint per installation. TODO(andrea): the constitution's AD-19
- `docs/administration/integrations-and-credentials.md:127` — TODO(andrea): the notification client's canonical env-var surface is
- `docs/administration/multi-tenancy.md:105` — TODO(andrea): confirm the cascade-deletion worker name and Kafka topic.
- `docs/administration/observability.md:13` — TODO(andrea): the Helm chart for the observability stack lives at
- `docs/administration/observability.md:48` — TODO(andrea): the canonical metric-name prefix and per-BC metric catalogue
- `docs/administration/observability.md:92` — TODO(andrea): list the exact dashboard JSONs and their ConfigMap names
- `docs/administration/quotas-and-limits.md:5` — (TODO(andrea): [spec 018][s018] mentions per-user workspace limits but
- `docs/administration/quotas-and-limits.md:29` — TODO(andrea): confirm whether `Workspace.settings` JSONB holds an
- `docs/administration/quotas-and-limits.md:99` — the internal seeder. TODO(andrea): add a
- `docs/administration/rbac-and-permissions.md:156` — TODO(andrea): surface this as a runtime admin API so custom roles can be
- `docs/administration/upgrades.md:106` — TODO(andrea): there is no consolidated "supported versions" policy

## Feature page skeletons

There are **57 auto-generated feature pages** under
`docs/features/`, one per SpecKit spec. Each page is a skeleton with
seven `TODO(andrea):` markers following the same template:

1. **How it works** — short technical explanation from `plan.md`.
2. **How to use it (end-user)** — minimal runnable example.
3. **Benefits** — 3–5 concrete outcomes.
4. **Administrator configuration** — keys, credentials, RBAC,
   quotas, observability hooks, data retention.
5. **Enable / disable procedure.**
6. **Required integration credentials.**
7. **Related features and dependencies.**

Total TODOs across feature skeletons: **638**.

Prioritise by feature importance — the P1 and core-platform features
deserve their content first. Suggested first batch:

- `features/014-auth-bounded-context.md`
- `features/018-workspaces-bounded-context.md`
- `features/021-agent-registry-ingest.md`
- `features/028-policy-governance-engine.md`
- `features/029-workflow-execution-engine.md`
- `features/032-trust-certification-guardrails.md`
- `features/047-observability-stack.md`
- `features/052-gid-correlation-envelope.md`
- `features/053-zero-trust-visibility.md`
- `features/061-judge-enforcer-governance.md` (not on `main`, will
  land when branches merge)

<details>
<summary>Full list of feature-skeleton files (57 files)</summary>

- `docs/features/001-postgresql-schema-foundation.md`
- `docs/features/002-redis-cache-hot-state.md`
- `docs/features/003-kafka-event-backbone.md`
- `docs/features/004-minio-object-storage.md`
- `docs/features/005-qdrant-vector-search.md`
- `docs/features/006-neo4j-knowledge-graph.md`
- `docs/features/007-clickhouse-analytics.md`
- `docs/features/008-opensearch-full-text-search.md`
- `docs/features/009-runtime-controller.md`
- `docs/features/010-sandbox-manager.md`
- `docs/features/011-reasoning-engine.md`
- `docs/features/012-simulation-controller.md`
- `docs/features/013-fastapi-app-scaffold.md`
- `docs/features/014-auth-bounded-context.md`
- `docs/features/015-nextjs-app-scaffold.md`
- `docs/features/016-accounts-bounded-context.md`
- `docs/features/017-login-auth.md`
- `docs/features/018-workspaces-bounded-context.md`
- `docs/features/019-websocket-realtime-gateway.md`
- `docs/features/020-analytics-cost-intelligence.md`
- `docs/features/021-agent-registry-ingest.md`
- `docs/features/022-context-engineering-service.md`
- `docs/features/023-memory-knowledge-subsystem.md`
- `docs/features/024-interactions-conversations.md`
- `docs/features/025-connector-plugin-framework.md`
- `docs/features/026-026-home-dashboard.md`
- `docs/features/026-home-dashboard.md`
- `docs/features/027-027-admin-settings-panel.md`
- `docs/features/027-admin-settings-panel.md`
- `docs/features/028-policy-governance-engine.md`
- `docs/features/029-workflow-execution-engine.md`
- `docs/features/030-marketplace-discovery-intelligence.md`
- `docs/features/031-conversation-interface.md`
- `docs/features/032-trust-certification-guardrails.md`
- `docs/features/033-fleet-management-learning.md`
- `docs/features/034-evaluation-semantic-testing.md`
- `docs/features/035-agent-marketplace-ui.md`
- `docs/features/036-workflow-editor-monitor.md`
- `docs/features/037-agentops-lifecycle.md`
- `docs/features/038-ai-agent-composition.md`
- `docs/features/039-scientific-discovery-orchestration.md`
- `docs/features/040-simulation-digital-twins.md`
- `docs/features/041-agent-catalog-workbench.md`
- `docs/features/042-fleet-dashboard.md`
- `docs/features/043-trust-certification-workbench.md`
- `docs/features/044-operator-dashboard-diagnostics.md`
- `docs/features/045-installer-operations-cli.md`
- `docs/features/046-cicd-pipeline.md`
- `docs/features/047-observability-stack.md`
- `docs/features/048-backup-restore.md`
- `docs/features/049-analytics-cost-dashboard.md`
- `docs/features/050-evaluation-testing-ui.md`
- `docs/features/051-fqn-namespace-agent-identity.md`
- `docs/features/052-gid-correlation-envelope.md`
- `docs/features/053-zero-trust-visibility.md`
- `docs/features/054-safety-prescreener-sanitization.md`
- `docs/features/index.md`

</details>
