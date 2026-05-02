# Product Software Architecture (v5 — Audit Pass + UPD-035 Capstone)

Version: 2.0
Scope baseline: 391 functional requirements + 375 technical requirements = 766 total requirements covered
Primary implementation stance: modular monolith for the control plane, extraction-ready from day 1
Primary deployment target: Kubernetes
Public streaming protocol: WebSockets
Internal service protocol: gRPC
Event backbone: Kafka
Interoperability baseline: MCP + A2A first-class

---

## 1. Purpose of this document

This document defines the **software architecture** of the platform.

Where `system-architecture.md` describes system planes, deployment topology, trust boundaries, and platform-wide flows, this document answers the software-design questions:

- How should the codebase be structured?
- What are the control-plane bounded contexts?
- Which elements stay inside the modular monolith, and which are separate services?
- What are the main internal APIs, gRPC contracts, Kafka topics, and domain entities?
- How do workflow execution, runtime orchestration, sandboxes, registry, marketplace, interactions, fleets, trust, memory, evaluation, context engineering, reasoning, self-correction, resource optimization, agent composition, scientific discovery, privacy, marketplace intelligence, fleet learning, agent simulation, AgentOps, and testing fit together in code?
- How does the software design remain extractable without prematurely committing to a microservice sprawl?

---

## 2. Design baseline and locked decisions

1. The control plane is a **modular monolith**, not a day-1 microservice fleet.
2. Internal heavy control paths use **gRPC**.
3. Public CRUD and management APIs use **versioned REST/JSON**.
4. Public live streaming uses **WebSockets**.
5. Durable async coordination uses **Kafka**.
6. The physical reference deployment is **Kubernetes**, but software contracts stay portable.
7. **A2A and MCP** are first-class architectural capabilities.
8. Registry, marketplace, monitor, interactions server, workbenches, certification, trust, factories, fleet abstractions, context engineering, reasoning orchestration, self-correction, resource optimization, agent composition, scientific discovery, privacy-preserving computation, marketplace intelligence, fleet learning, simulation, AgentOps, and semantic testing all exist in the target design.
9. High-privilege operations exist but are isolated behind strict brokered paths.
10. **Dedicated purpose-built data stores from day 1**: PostgreSQL for relational truth, Qdrant for vector search, Neo4j for knowledge graph, ClickHouse for analytics, Redis for caching/hot state, OpenSearch for full-text discovery.
11. **Reasoning orchestration and self-correction** are implemented as a **separate Go service** (`reasoning-engine`) alongside the runtime controller. Context engineering remains in the Python monolith.

---

## 3. Coverage statement

This software architecture covers:

- **Functional requirements:** 391
- **Technical requirements:** 375
- **Total:** 766

---

## 4. Software architecture style

## 4.1 Why a modular monolith is the correct starting point

The platform now spans an even broader problem space than the initial design:
- identity and multi-tenancy;
- registry and marketplace metadata with intelligent recommendation;
- workflow compilation and execution semantics;
- interactions, workspaces, and conversation branching;
- trust, policy, and certification with privacy impact assessment;
- evaluation, experimentation, and scientific discovery;
- factories, SDKs, and AI-assisted composition;
- connector routing;
- runtime and sandbox orchestration;
- **context engineering with quality scoring, provenance, and compaction;**
- **reasoning orchestration with budget management and adaptive depth;**
- **self-correction with convergence detection;**
- **resource-aware optimization with dynamic model switching and cost intelligence;**
- **agent simulation and digital twins;**
- **AgentOps with behavioral versioning and governance-aware CI/CD;**
- **semantic and behavioral testing with adversarial generation.**

A modular monolith provides the right balance for all of these, with explicit extraction seams.

## 4.2 What "modular monolith" means here

- One main control-plane codebase;
- one primary relational schema authority (PostgreSQL); dedicated stores for vector (Qdrant), graph (Neo4j), analytics (ClickHouse), cache (Redis), and search (OpenSearch);
- one deployment family for business logic;
- strict bounded contexts with owned models and APIs;
- no direct database access across domains;
- event publication and query projection inside the monolith;
- independent worker/scheduler/API/WebSocket/context/reasoning/agentops profiles from the same image.

## 4.3 What is allowed to be separate from day 1

- Runtime controller (Go);
- Sandbox manager (Go);
- HostOps broker;
- Simulation controller (Go);
- Optional browser automation worker;
- Stateful foundation systems (Kafka, PostgreSQL, object storage, search/vector/graph backends);
- Observability stack.

## 4.4 Extraction criteria

A bounded context should only be extracted when:
- independently scaling profile exceeds in-process boundaries;
- security isolation needs differ materially;
- team ownership requires independent release cadence;
- compliance or residency rules demand separation;
- latency or fault-isolation data justifies network cost.

---

## 5. Repository and package layout

```text
repo/
  apps/
    control-plane/
      src/platform/
        api/
        admin/                     # NEW (UPD-036): composition layer for /api/v1/admin/*
                                   #   (NOT a bounded context — composes admin_router.py from each BC)
                                   #   Contains: router.py, rbac.py, 2pa_service.py, impersonation_service.py,
                                   #   read_only_middleware.py, change_preview.py, activity_feed.py,
                                   #   installer_state.py, bootstrap.py
        common/
          secret_provider.py        # NEW (UPD-040): SecretProvider Protocol + Mock / Kubernetes / Vault impls
          logging.py                # Structured logger (UPD-034)
          config.py
          ...
        auth/                      # + admin_router.py (users, roles, groups, sessions, oauth, ibor, api-keys)
                                   # + services/oauth_bootstrap.py (UPD-041: env-var seeding)
        accounts/
        workspaces/                # + admin_router.py (tenants, workspaces, namespaces, quotas)
        connectors/                # + admin_router.py (plugin config)
        registry/
        marketplace/
        interactions/
        workflows/
        execution/
        fleets/
        policies/
        trust/
        promptops/
        memory/
        analytics/
        billing/                   # NEW (UPD-047): plans, subscriptions, quotas, overage, payment providers
        evaluation/
        audit/
        search/
        notifications/
        hooks/
        workbenches/
        context_engineering/       # NEW: context assembly, quality scoring, provenance, compaction
        reasoning/                 # NEW: mode selection, budget management, CoT/ToT orchestration
        self_correction/           # NEW: correction loops, convergence detection, analytics
        resource_optimization/     # NEW: task classifier, dynamic routing, cost intelligence
        agent_composition/         # NEW: AI-assisted composition, blueprint generation
        scientific_discovery/      # NEW: hypothesis management, tournament ranking, experiments
        privacy/                   # NEW: differential privacy, data minimization, anonymization
        marketplace_intelligence/  # NEW: recommendation, quality signals, contextual discovery
        fleet_learning/            # NEW: performance profiles, adaptation, knowledge transfer
        simulation/                # NEW: digital twins, behavioral prediction, simulation coordination
        agentops/                  # NEW: behavioral versioning, canary control, health scoring
        testing/                   # NEW: semantic scoring, adversarial generation, drift detection
        communication/             # NEW: broadcast/multicast, conversation branching, negotiation
        governance/                # NEW: Judge/Enforcer roles, governance pipeline
        a2a_gateway/               # NEW: A2A protocol server/client, Agent Card generation
        privacy_compliance/        # NEW (v4): DSR handler, RTBF cascade, DLP, PIA, residency
        security_compliance/       # NEW (v4): SBOM, vuln scanning, pen test tracking, secret rotation, JIT, audit chain
        cost_governance/           # NEW (v4): cost attribution, chargeback, budgets, forecasting
        multi_region_ops/          # NEW (v4): region config, replication monitoring, failover, maintenance mode
        model_catalog/             # NEW (v4): approved models, model cards, fallback policies
        localization/              # NEW (v4): locale files, i18n workflow, user locale preferences
        common/
      migrations/
      entrypoints/
        api_main.py
        scheduler_main.py
        worker_main.py
        ws_main.py
        certifier_main.py
        projector_main.py
        context_main.py            # NEW
        reasoning_main.py          # NEW
        agentops_main.py           # NEW
    ui/
      nextjs-app/
        app/
          (auth)/                   # Auth-shell routes
            login/                  # existing
            forgot-password/        # existing
            reset-password/         # existing
            signup/                 # NEW (UPD-037): public signup page
            verify-email/           # NEW (UPD-037): pending + token validation pages
            waiting-approval/       # NEW (UPD-037): admin-approval waiting page
            auth/oauth/[provider]/callback/  # NEW (UPD-037): dedicated OAuth callback page
            auth/oauth/error/       # NEW (UPD-037): OAuth error page
            profile-completion/     # NEW (UPD-037): first-time OAuth profile completion
          (main)/                   # Public/user-facing routes
            marketplace/
            workbenches/
            notifications/          # NEW (UPD-042): user notification inbox
            settings/
              notifications/        # NEW (UPD-042): preferences matrix
              api-keys/             # NEW (UPD-042): self-service tokens
              security/             # NEW (UPD-042): mfa / sessions / activity
              privacy/              # NEW (UPD-042): consent / dsr
              account/connections/  # NEW (UPD-037): OAuth link management
              status-subscriptions/ # NEW (UPD-045): public status subscription prefs
            workspaces/             # NEW (UPD-043): workspace owner workbench
              [id]/                 # members, settings, connectors, visibility, quotas, tags
            agent-management/
              [fqn]/
                context-profile/    # NEW (UPD-044): editor + history
                contract/           # NEW (UPD-044): authoring + history
              contracts/library/    # NEW (UPD-044): template library
            discovery/              # EXISTING network view, extended in UPD-045
              [session_id]/         # session detail with tabs, hypotheses, experiments, evidence
            evaluation-testing/
              simulations/
                scenarios/          # NEW (UPD-045): scenario editor + library
            ...
          (admin)/                  # UPD-036 admin workbench tree (40+ pages)
            security/vault/         # NEW (UPD-040): Vault ops panel
            oauth-providers/        # UPD-036 extended by UPD-041
            ...
          api/log/client-error/     # UPD-034 client error ingest
    ops-cli/
      cli/
          (admin)/                  # NEW (UPD-036): admin workbench route tree
            layout.tsx              # Role gate + admin shell
            page.tsx                # Landing dashboard (FR-547)
            users/, roles/, groups/, sessions/, oauth-providers/, ibor/, api-keys/   # Identity & Access (FR-548)
            tenants/, workspaces/, namespaces/                                         # Tenancy (FR-549) — tenants super admin only
            settings/, feature-flags/, model-catalog/, policies/, connectors/          # System Config (FR-550)
            audit-chain/, security/, privacy/, compliance/                             # Security & Compliance (FR-551)
            health/, incidents/, runbooks/, maintenance/, regions/, queues/, warm-pool/, executions/   # Operations (FR-552)
            costs/                  # Cost & Billing (FR-553)
            observability/          # Observability admin (FR-554)
            integrations/           # Integrations (FR-555)
            lifecycle/              # Platform Lifecycle (FR-556) — super admin only
            audit/                  # Audit & Logs (FR-557)
          api/log/client-error/     # UPD-034 client error ingest
    ops-cli/
      cli/
  services/
    runtime-controller/
    sandbox-manager/
    hostops-broker/
    browser-worker/
    simulation-controller/         # NEW
  sdk/
    python/
    go/
  templates/
    agents/
    fleets/
    prompts/
    policies/
    context-profiles/              # NEW
    reasoning-configs/             # NEW
    fleet-personalities/           # NEW
    simulation-scenarios/          # NEW
    adversarial-suites/            # NEW
  proto/
    runtime_controller.proto
    sandbox_manager.proto
    hostops_broker.proto
    simulation_controller.proto    # NEW
    reasoning_engine.proto         # NEW
  deploy/
    kubernetes/
    helm/
  tests/
    e2e/                             # NEW: E2E test harness (kind-based)
      cluster/                       # kind cluster config, values-e2e.yaml overlay
      fixtures/                      # pytest fixtures: http client, ws client, db session, seeders
      seeders/                       # deterministic test data (users, agents, policies, fleets)
      suites/                        # E2E test suites organized by bounded context
        auth/                        # local auth, MFA, Google OAuth, GitHub OAuth
        registry/                    # FQN, namespaces, visibility, pattern discovery
        trust/                       # pre-screener, certification, contracts, surveillance
        governance/                  # Judge/Enforcer pipeline, verdicts, enforcement
        interactions/                # conversations, workspace goals, GID, attention, alerts
        workflows/                   # executions, checkpoints, rollback, re-prioritization
        reasoning/                   # CoT, ToT, ReAct, CoD, self-correction, compute_budget
        evaluation/                  # TrajectoryScorer, LLM-as-Judge, A/B testing
        agentops/                    # adaptation pipeline, canary
        discovery/                   # hypothesis proximity graph
        a2a/                         # Agent Card, server mode, client mode, SSE
        mcp/                         # client discovery, server exposure
        runtime/                     # warm pool, secrets injection
        storage/                     # generic S3 upload/download/lifecycle
        ibor/                        # IBOR sync
      chaos/                         # chaos injection scenarios
      performance/                   # performance smoke tests
      journeys/                      # user journey tests (cross-cutting, per persona)
        conftest.py                  # shared journey fixtures (admin/creator/consumer clients)
        helpers/                     # oauth_login, register_agent, certify, wait_for_exec
                                     # + (UPD-035) assert_log_entry, assert_metric, assert_trace,
                                     #              assert_dashboard_snapshot, axe_runner
        test_j01_admin_bootstrap.py           # extended in UPD-035
        test_j02_creator_to_publication.py    # extended in UPD-035
        test_j03_consumer_discovery_execution.py    # extended in UPD-035
        test_j04_workspace_goal_collaboration.py    # extended in UPD-035
        test_j05_trust_governance_pipeline.py       # extended in UPD-035
        test_j06_operator_incident_response.py      # extended in UPD-035
        test_j07_evaluator_improvement_loop.py      # extended in UPD-035
        test_j08_external_a2a_mcp.py                # extended in UPD-035
        test_j09_scientific_discovery.py            # extended in UPD-035
        test_j10_privacy_officer.py                 # NEW in UPD-035
        test_j11_security_officer.py                # NEW in UPD-035
        test_j12_finance_owner.py                   # NEW in UPD-035
        test_j13_sre_multi_region.py                # NEW in UPD-035
        test_j14_model_steward.py                   # NEW in UPD-035
        test_j15_accessibility_user.py              # NEW in UPD-035
        test_j16_compliance_auditor.py              # NEW in UPD-035
        test_j17_dashboard_consumer.py              # NEW in UPD-035
      Makefile                       # e2e-up, e2e-down, e2e-test targets
      conftest.py                    # shared pytest configuration
  docs/
    adr/
```

### 5.1 Important structural rules

- Each bounded context owns its application service layer, domain model, persistence mappers, and read/query projections.
- Cross-context interaction occurs via well-defined internal service interfaces, domain events published to Kafka, and explicit query APIs.
- Shared code in `common/` is restricted to infra primitives, cross-cutting types, correlation/auth helpers, shared serializers, generic error handling, and event envelope utilities.
- Business logic must not drift into `common/`.
- New bounded contexts for context engineering, reasoning, self-correction, resource optimization, agent composition, scientific discovery, privacy, marketplace intelligence, fleet learning, simulation, AgentOps, testing, and communication follow the same ownership rules.

---

## 6. Runtime profiles from the same control-plane codebase

## 6.1 API profile

Owns:
- public REST APIs;
- BFF APIs for workbenches;
- A2A public HTTP endpoints;
- MCP exposure endpoints;
- webhook ingress;
- auth/session entrypoints;
- agent composition API endpoints;
- simulation coordination API endpoints.

## 6.2 Scheduler profile

Owns:
- workflow scheduling with reasoning budget awareness;
- retry timers;
- approval reactivation;
- priority queue selection with adaptive reprioritization;
- compatibility checks for hot updates;
- dispatch coordination;
- reasoning budget allocation.

## 6.3 Worker profile

Owns:
- background event consumers;
- connector orchestration logic;
- notification jobs;
- memory consolidation jobs;
- evaluation collectors;
- lifecycle hook execution;
- context quality scoring jobs;
- fleet health aggregation jobs;
- behavioral drift detection jobs;
- learned allocation policy updates.

## 6.4 WebSocket profile

Owns:
- authenticated WebSocket connections;
- subscription registry;
- live fan-out from Kafka events;
- operator and workbench streaming;
- reasoning trace milestone streaming;
- self-correction progress streaming.

## 6.5 Projection/indexer profile

Owns:
- search projections (PostgreSQL FTS);
- trust signal projections;
- analytics rollups;
- marketplace query indexes;
- monitor dashboards' derived views;
- quality signal aggregation;
- fleet performance profile computation;
- cost intelligence aggregation.

## 6.6 Certifier profile

Owns:
- certification pipeline runs;
- evidence ingestion;
- recertification triggers;
- trust-state transitions;
- policy and guardrail validation orchestrations;
- privacy impact assessment execution.

## 6.7 Context engineering profile (NEW)

Owns:
- context assembly orchestration;
- quality scoring computation;
- provenance persistence;
- budget enforcement;
- compaction execution;
- context A/B test coordination;
- context drift monitoring.

## 6.8 Reasoning coordination profile (NEW — thin adapter)

Owns:
- reasoning event consumption from Kafka and persistence to PostgreSQL/ClickHouse/object storage;
- reasoning configuration resolution from policies;
- query APIs for workbench reasoning trace visualization;
- reasoning analytics aggregation.

Note: The hot-path reasoning execution (budget tracking, convergence detection, tree branch management) runs in the **Go reasoning engine satellite service**, not in this Python profile.

## 6.9 AgentOps/testing profile (NEW)

Owns:
- behavioral version tracking;
- governance-aware CI/CD gating;
- canary deployment coordination;
- behavioral regression detection;
- agent health scoring;
- automated retirement workflows;
- semantic similarity scoring;
- adversarial test generation and execution;
- statistical robustness test orchestration;
- behavioral drift detection orchestration;
- multi-agent coordination testing;
- human-AI grading pipeline;
- test case generation.

---

## 7. Bounded contexts inside the control-plane monolith

This section defines all software modules and their responsibilities.

## 7.1 `auth` bounded context

### Responsibilities
Local authentication, password rotation/reset, lockout/throttling, MFA/TOTP, token/session issuance/rotation/revocation, service-account auth, enterprise SSO hooks, **OAuth2/OIDC social login (Google, GitHub)** — provider registration, authorization code flow with PKCE, ID token validation, first-login auto-provisioning, account linking, domain/org restrictions, external group-to-role mapping.

### Owns
`UserCredential`, `Session`, `MfaEnrollment`, `AuthAttempt`, `PasswordResetToken`, `ServiceAccountCredential`, **`OAuthProvider`** (provider config: client_id, client_secret ref, redirect_uri, domain/org restrictions, group mapping, enabled flag), **`OAuthLink`** (user_id, provider, external_id, external_email, linked_at)

### Publishes events
`user.authenticated`, `user.locked`, `user.unlocked`, `session.revoked`, `mfa.enrolled`, **`user.oauth_linked`**, **`user.oauth_provisioned`**

## 7.2 `accounts` bounded context

### Responsibilities
Registration, invite-only flows, email verification, admin approval, subscription toggle, user lifecycle.

### Owns
`User`, `UserStatus`, `Invitation`, `ApprovalRequest`, `EmailVerification`, `SubscriptionState`

## 7.3 `workspaces` bounded context

### Responsibilities
Workspace creation/lifecycle, memberships/roles, default workspace logic, limits, settings, goals, super-context metadata.

### Owns
`Workspace`, `Membership`, `WorkspaceRoleGrant`, `WorkspaceGoal`, `WorkspaceSettings`, `WorkspaceSubscription`

## 7.4 `connectors` bounded context

### Responsibilities
Connector configuration, credential references, routing rules, inbound/outbound definitions, instance lifecycle, provider normalization.

### Owns
`Connector`, `ConnectorInstance`, `ConnectorCredentialRef`, `ConnectorRoute`, `InboundSource`, `OutboundTarget`

### Publishes events
`connector.message.received`, `connector.delivery.requested`, `connector.delivery.failed`, `connector.quarantined`

## 7.5 `registry` bounded context

> **Update (v3):** Added namespace management (CRUD, uniqueness validation). Agent identity via FQN (namespace:local_name). FQN resolution endpoint. FQN pattern matching in discovery. Zero-trust visibility filtering at query time. Mandatory natural-language purpose and optional approach fields. Agent role_type enum includes judge and enforcer. Workspace-level visibility grants.

### Responsibilities
Authoritative metadata system of record for agents (with maturity level, reasoning mode support, context engineering profile), revisions, fleets, policies, certifications, conversations, interactions, workspaces, user references, visibility and endpoint descriptors, attribution.

### Owns
`AgentProfile`, `AgentRevision`, `FleetProfile`, `ConversationRecord`, `InteractionRecord`, `PolicyRecord`, `CertificationRecord`, `UserReference`, `AgentMaturityRecord`, `ReasoningModeDescriptor`, `ContextEngineeringProfileRef`

## 7.6 `marketplace` bounded context

### Responsibilities
Discovery APIs, natural-language search, filtered listings, comparison views, trust-signal composition, access-request workflows, revision resolution, maturity filtering, cost-performance matching.

### Owns
`MarketplaceListingProjection`, `TrustSignalProjection`, `AccessRequest`, `AuthenticatedRating`, `DiscoverySavedView`

### Depends on
`registry`, `trust`, `search`, `policies`, `monitor`, `marketplace_intelligence`

## 7.7 `interactions` bounded context

> **Update (v3):** Added workspace goal lifecycle (READY→WORKING→COMPLETE). Added Goal ID (GID) as first-class correlation dimension. Added configurable agent response decision mechanisms (LLM relevance, allowlist/blocklist, keyword, embedding similarity, best-match). Added agent-initiated attention requests. Added configurable user alert settings (state transitions, delivery methods, per-interaction overrides).

### Responsibilities
Start conversation, create bounded interactions, accept mid-process messages, workspace-goal message injection, status APIs, causal ordering, conversation branching and merging, multi-interaction concurrency.

### Owns
`Conversation`, `Interaction`, `InteractionMessage`, `WorkspaceGoalMessage`, `InteractionParticipant`, `ConversationBranch`, `BranchMergeRecord`

## 7.8 `workflows` bounded context

### Responsibilities
YAML schema validation, typed IR with reasoning mode hints and context budget constraints, workflow versioning, compatibility metadata, compilation-time validation.

### Owns
`WorkflowDefinition`, `WorkflowVersion`, `CompiledWorkflowIR`, `WorkflowCompatibilityRule`, `TriggerDefinition`

## 7.9 `execution` bounded context

### Responsibilities
Execution creation, append-only journal (including reasoning traces and self-correction iterations), checkpoints, scheduling with reasoning budget awareness, retry policies, pause/cancel, replay/resume/rerun, prioritization, dispatch leasing, runtime reconciliation.

### Owns
`Execution`, `ExecutionEvent`, `Checkpoint`, `DispatchLease`, `RetrySchedule`, `ApprovalWait`, `CompensationRecord`, `ReasoningTraceRef`, `SelfCorrectionIterationRef`

## 7.10 `fleets` bounded context

### Responsibilities
Fleet domain model, membership and topology descriptors, orchestration style, lifecycle, observer membership, degraded operation state, escalation paths, personality profiles.

### Owns
`Fleet`, `FleetMember`, `FleetTopology`, `FleetPolicyBinding`, `FleetHealthProjection`, `ObserverAssignment`, `FleetPersonalityProfile`

## 7.11 `policies` bounded context

### Responsibilities
Structured policy definitions, purpose-bound constraints, runtime evaluation contracts, policy attachment, capability algebra, enforcement semantics, versioning, maturity-gated access rules.

### Owns
`Policy`, `PolicyVersion`, `PolicyAttachment`, `CapabilityConstraint`, `EnforcementRule`, `PurposeScope`, `MaturityGateRule`

## 7.12 `trust` bounded context

> **Update (v3):** Added SafetyPreScreener (rule-based, <10ms, hot-updatable YAML rules). Added tool output secret sanitizer. Added agent contract model (task scope, quality thresholds, cost/time limits, enforcement). Added contract compliance monitoring. Added third-party certifier registration. Added ongoing surveillance program with periodic reassessment and auto-recertification. Added certification expiry and renewal workflow. Added agent decommissioning lifecycle.

### Responsibilities
Certification workflows, evidence binding, trust tiers, issuer lifecycle, trust projections, proof/integrity hooks, revocation, recertification.

### Owns
`Certification`, `CertificationEvidenceRef`, `TrustTier`, `TrustSignal`, `ProofLink`, `RecertificationTrigger`

## 7.13 `promptops` bounded context

### Responsibilities
Prompt asset registry, structured task briefs, prompt versions/promotion, context assembly references, output contracts, output repair metadata, prompt experiment tracking.

### Owns
`PromptAsset`, `PromptVersion`, `StructuredBrief`, `OutputContract`, `PromptExperiment`

## 7.14 `memory` bounded context

### Responsibilities
Memory scope resolution, vector and keyword retrieval orchestration, trajectory capture, pattern store, knowledge graph orchestration, consolidation and compaction jobs, contradiction metadata.

### Owns
`TrajectoryRecord`, `PatternAsset`, `MemoryScopeBinding`, `MemoryWriteRequest`, `EvidenceConflict`, `EmbeddingJob`

## 7.15 `analytics` bounded context

### Responsibilities
Usage metering, cost estimation, KPI projection, dashboard rollups, billing-support views, quota-consumption projections, cost intelligence aggregation, resource prediction data.

### Owns
`UsageEvent`, `UsageRollup`, `CostEstimate`, `KpiSeries`, `QuotaConsumption`, `CostIntelligenceReport`, `ResourcePrediction`

## 7.15a `billing` bounded context (UPD-047)

### Responsibilities
Commercial plan catalog and immutable plan-version publication, workspace- and tenant-scoped subscriptions, lifecycle transitions, quota enforcement, overage authorization, billing-period rollover, active-compute metering, provider usage reporting, and platform-staff subscription administration.

### Owns
`Plan`, `PlanVersion`, `Subscription`, `UsageRecord`, `OverageAuthorization`, `ProcessedEventId`; PostgreSQL migrations 103 and 104 seed the default Free/Pro/Enterprise plans, backfill default-tenant workspace subscriptions, and link `cost_attributions.subscription_id` for billing-aware analytics.

### Publishes events
`billing.plan.published`, `billing.subscription.upgraded`, `billing.subscription.downgrade_scheduled`, `billing.subscription.downgrade_cancelled`, `billing.subscription.downgrade_effective`, `billing.subscription.cancelled`, `billing.subscription.period_renewed`, `billing.overage.required`, `billing.overage.authorized`, `billing.overage.revoked`.

### Payment providers
Provider integration is expressed as a `PaymentProvider` Protocol, with methods for customer creation, subscription create/update/cancel, proration preview, invoice retrieval, and metered-usage reporting. The deterministic stub provider is used in local, test, and CI flows. Stripe remains an implementation detail behind the same interface, so subscription service code does not branch on provider-specific SDK objects.

### Quota-enforcement hot path
Chargeable operations call the `QuotaEnforcer` synchronously before durable side effects: execution creation, workspace creation, agent publication, invitation acceptance, and model selection. The enforcer resolves the active subscription, reads the pinned plan version, uses process-local and Redis quota caches, then returns `OK`, hard-cap, overage-required, overage-cap, model-tier, no-subscription, or suspended decisions. Hard caps return HTTP 402 without partial state; Pro overage can create a paused execution until authorization; Enterprise zero-cap plans short-circuit.

## 7.16 `evaluation` bounded context

> **Update (v3):** Added TrajectoryScorer (full execution path evaluation: efficiency, tool appropriateness, coherence, cost-effectiveness; 5 comparison methods; multi-agent cooperation scoring). Added LLM-as-Judge formalization (configurable judge model, rubric definitions with criteria/scale/examples, structured verdicts, calibration runs with score distributions). Added contract-based evaluation KPI.

### Responsibilities
Offline and online evaluations, scorer registry, evalset definitions, A/B assignments, experiment entities, human/AI review artifacts, hypothesis and experiment support.

### Owns
`EvaluationRun`, `JudgeVerdict`, `EvalSet`, `BenchmarkCase`, `AbExperiment`, `Hypothesis`, `ExperimentRun`, `TournamentRankingRecord`

## 7.17 `audit` bounded context

### Responsibilities
Append-only audit records, action attribution, blocked-action records, forensic export, retention metadata, redaction policies, evidence-to-audit linkage.

### Owns
`AuditEvent`, `RetentionRule`, `RedactionPolicy`, `ForensicExport`, `ActorAttribution`

## 7.18 `search` bounded context

### Responsibilities
Search projections (OpenSearch), natural-language search orchestration, filter/sort, saved views, query optimization.

### Owns
`SearchProjection`, `SavedView`, `FacetProjection`, `RankingSignal`

## 7.19 `notifications` bounded context

### Responsibilities
User alerts, outbound email dispatch, notification templates, escalation messages, delivery status.

### Owns
`Notification`, `NotificationTemplate`, `AlertSubscription`, `DeliveryAttempt`

## 7.20 `hooks` bounded context

### Responsibilities
Lifecycle hook registration, ordering/priority, failure-policy semantics, background automation triggers, typed lifecycle event handling.

### Owns
`HookDefinition`, `HookBinding`, `HookExecution`, `WorkerAssignment`

## 7.21 `workbenches` bounded context

### Responsibilities
Compose API/BFF views for consumer, creator, trust, operator, and evaluator surfaces. Aggregate data from registry, monitor, trust, interactions, execution, analytics, context engineering, reasoning, self-correction, AgentOps, and testing.

### Owns
Primarily composed views, not deeply independent transactional truth.

## 7.22 `context_engineering` bounded context (NEW)

### Responsibilities
- Deterministic context assembly from multiple policy-approved sources;
- context quality scoring with configurable criteria (relevance, freshness, authority, contradiction density, token efficiency, coverage);
- provenance tracking for every included context element;
- budget enforcement at step, execution, and agent levels;
- compaction strategies (relevance truncation, summarization, priority eviction, hierarchical compression, semantic deduplication);
- context A/B testing;
- context drift detection and alerting.

### Owns
`ContextAssemblyRecord`, `ContextQualityScore`, `ContextProvenanceEntry`, `ContextBudgetEnvelope`, `ContextCompactionStrategy`, `ContextAbTest`, `ContextDriftAlert`, `ContextEngineeringProfile`

### Depends on
`memory`, `promptops`, `policies`, `privacy`, `execution`

### Publishes events
`context.assembled`, `context.quality.computed`, `context.budget.exceeded`, `context.drift.detected`

## 7.23 `reasoning` bounded context (NEW — thin coordination layer)

### Note on implementation split
The **core reasoning execution logic** (budget tracking, convergence detection, tree branch management, correction loops) runs in the **Go reasoning engine** satellite service. This bounded context in the Python monolith serves as the **coordination and persistence adapter** — it handles API exposure, policy resolution, Kafka event consumption for cold storage, and query APIs for workbench and analytics consumption.

### Responsibilities
- Reasoning configuration resolution from policies and task briefs;
- reasoning event consumption from Kafka (emitted by Go reasoning engine) and persistence to PostgreSQL + object storage;
- query APIs for reasoning trace inspection, budget history, and quality metrics;
- workbench data composition for reasoning trace visualization;
- reasoning analytics aggregation (delegates to ClickHouse);
- reasoning mode configuration management.

### Owns (persistence side)
`ReasoningModeConfig`, `ReasoningBudgetEnvelope`, `ChainOfThoughtTrace`, `TreeOfThoughtBranch`, `ReasoningQualityScore`, `AdaptiveDepthPolicy`, `CodeAsReasoningRequest`

### Depends on
`execution`, `policies`, `analytics`

### Consumes events (from Go reasoning engine via Kafka)
`reasoning.mode.selected`, `reasoning.budget.allocated`, `reasoning.trace.milestone`, `reasoning.budget.exceeded`, `reasoning.branch.created`, `reasoning.branch.selected`

## 7.24 `self_correction` bounded context (NEW — thin coordination layer)

### Note on implementation split
Like reasoning, the **core self-correction loop logic** (convergence detection, iteration management, escalation) runs in the **Go reasoning engine**. This bounded context handles policy resolution, event persistence, query APIs, and analytics.

### Responsibilities
- Self-correction policy resolution from governance bundles;
- correction event consumption from Kafka and persistence;
- query APIs for correction iteration inspection;
- self-correction analytics aggregation (delegates to ClickHouse);
- human escalation routing integration with approval system.

### Owns (persistence side)
`SelfCorrectionLoop`, `CorrectionIteration`, `ConvergenceMetric`, `CorrectionPolicy`, `CorrectionAnalytics`, `ProducerReviewerBinding`

### Depends on
`execution`, `policies`, `evaluation`

### Consumes events (from Go reasoning engine via Kafka)
`correction.iteration.started`, `correction.iteration.completed`, `correction.converged`, `correction.escalated`, `correction.budget.exceeded`

## 7.25 `resource_optimization` bounded context (NEW)

### Responsibilities
- Task complexity classification;
- dynamic model routing based on complexity, cost, latency, quality;
- context pruning orchestration;
- resource prediction before execution;
- graceful degradation when limits are reached;
- learned allocation policies from historical data;
- cost intelligence dashboards and recommendations.

### Owns
`TaskComplexityClassification`, `ModelRoutingDecision`, `ResourcePrediction`, `LearnedAllocationPolicy`, `CostIntelligenceReport`, `GracefulDegradationEvent`

### Depends on
`execution`, `analytics`, `policies`, `context_engineering`

### Publishes events
`routing.model.selected`, `routing.degradation.triggered`, `routing.prediction.computed`

## 7.26 `agent_composition` bounded context (NEW)

### Responsibilities
- AI-assisted agent blueprint generation from natural-language descriptions;
- fleet blueprint generation from mission descriptions;
- composition validation against platform constraints;
- composition audit trail;
- integration with certification and publication readiness pipelines.

### Owns
`AgentBlueprint`, `FleetBlueprint`, `CompositionRequest`, `CompositionAuditEntry`, `CompositionValidationResult`

### Depends on
`registry`, `policies`, `trust`, `promptops`, `context_engineering`

## 7.27 `scientific_discovery` bounded context (NEW)

> **Update (v3):** Added Hypothesis Proximity Graph: compute embeddings (Qdrant), build proximity edges (Neo4j), cluster similar hypotheses, identify landscape gaps, bias generation toward underrepresented areas.

### Responsibilities
- Hypothesis generation workflow coordination;
- multi-agent hypothesis critique orchestration;
- Elo-based tournament ranking;
- experiment design workflow coordination;
- generate-debate-evolve cycle management;
- discovery evidence provenance chains.

### Owns
`Hypothesis`, `HypothesisCritique`, `TournamentRanking`, `EloScore`, `DiscoveryExperiment`, `DiscoveryEvidence`, `GenerateDebateEvolveCycle`

### Depends on
`execution`, `evaluation`, `memory`, `policies`

## 7.28 `privacy` bounded context (NEW)

### Responsibilities
- Differential privacy engine for memory and analytics;
- data minimization enforcement for context assembly and cross-scope transfers;
- anonymization pipeline for cross-tenant telemetry;
- privacy impact assessment for context assemblies and memory operations.

### Owns
`PrivacyBudget`, `DifferentialPrivacyConfig`, `DataMinimizationPolicy`, `AnonymizationRule`, `PrivacyImpactAssessment`

### Depends on
`policies`, `context_engineering`, `memory`, `analytics`

## 7.29 `marketplace_intelligence` bounded context (NEW)

### Responsibilities
- Agent recommendation engine (collaborative filtering, content matching, contextual signals);
- quality signal aggregation (success rates, quality scores, self-correction frequency, satisfaction);
- contextual discovery suggestions within workbenches;
- trending and popular agent surfacing.

### Owns
`AgentRecommendation`, `QualitySignalAggregate`, `ContextualDiscoverySuggestion`, `TrendingAgentProjection`, `UsageQualityMetric`

### Depends on
`registry`, `marketplace`, `analytics`, `evaluation`

## 7.30 `fleet_learning` bounded context (NEW)

### Responsibilities
- Fleet performance profile aggregation;
- fleet performance tournament coordination;
- fleet behavioral adaptation (adjust orchestration rules from observed data);
- cross-fleet knowledge transfer through approved channels;
- fleet personality profile management.

### Owns
`FleetPerformanceProfile`, `FleetTournament`, `FleetAdaptationRule`, `CrossFleetTransferRequest`, `FleetPersonalityConfig`

### Depends on
`fleets`, `evaluation`, `analytics`, `policies`

## 7.31 `simulation` bounded context (NEW)

### Responsibilities
- Simulation sandbox provisioning coordination;
- digital twin management (configuration snapshots, behavioral history);
- behavioral prediction from historical patterns;
- simulation isolation enforcement;
- simulation comparison analytics.

### Owns
`SimulationRun`, `DigitalTwin`, `BehavioralPrediction`, `SimulationIsolationPolicy`, `SimulationComparisonReport`

### Depends on
`registry`, `execution`, `analytics`

## 7.32 `agentops` bounded context (NEW)

> **Update (v3):** Added agent adaptation pipeline (evaluate performance → identify improvement opportunities → propose configuration adjustments → human approval → apply as new revision). Self-correction convergence data feeds into adaptation signals. Context quality → performance correlation tracking.

### Responsibilities
- Behavioral versioning (tracking behavioral changes over time through evaluation metrics);
- governance-aware CI/CD gating (deployment blocked on policy, evaluation, certification, regression);
- canary deployment coordination;
- behavioral regression detection (statistical comparison against baselines);
- agent health scoring (composite of uptime, quality, safety, cost, satisfaction);
- automated retirement workflows.

### Owns
`BehavioralVersion`, `CiCdGateResult`, `CanaryDeployment`, `BehavioralRegressionAlert`, `AgentHealthScore`, `RetirementWorkflow`

### Depends on
`registry`, `evaluation`, `analytics`, `policies`, `trust`

## 7.33 `testing` bounded context (NEW)

> **Update (v3):** Extended to include E2E platform testing on ephemeral kind clusters. New responsibilities: E2E test harness management, deterministic test data seeding across all bounded contexts, chaos injection (pod kills, network partitions, credential failures), performance smoke test execution, CI/CD integration with JUnit XML output. The E2E test harness lives in a dedicated `tests/e2e/` tree at repository root (not in the monolith) but the testing bounded context provides the in-platform hooks: test-only data seeding APIs (feature-flagged), chaos injection endpoints (admin-only, dev-only), deterministic mock LLM provider wiring.

### Responsibilities
- Semantic similarity scoring using embeddings (Qdrant);
- adversarial test case generation (prompt injection, edge cases, contradictions);
- statistical robustness test execution (multi-run distribution analysis);
- behavioral drift detection (baseline comparison over time);
- multi-agent coordination test harness;
- human-AI collaborative grading pipeline;
- AI-assisted test case generation from agent configuration;
- **E2E test data seeding API** (feature-flagged, admin-only, dev-only);
- **chaos injection endpoints** for testing resilience (feature-flagged, admin-only, dev-only);
- **mock LLM provider integration** for deterministic E2E test runs;
- **user journey test orchestration** — 9 cross-cutting journeys covering all personas (admin, creator, consumer, collaborator, trust officer, operator, evaluator, external integrator, researcher), each with 15+ assertions at bounded-context boundaries.

### Owns
`SemanticSimilarityResult`, `AdversarialTestCase`, `RobustnessTestRun`, `BehavioralDriftMetric`, `CoordinationTestResult`, `HumanAiGrade`, `GeneratedTestSuite`

### Depends on
`evaluation`, `registry`, `execution`, `analytics`

## 7.34 `communication` bounded context (NEW)

### Responsibilities
- Broadcast and multicast messaging within fleets and workspace-scoped groups;
- conversation branching (fork into parallel threads) and merging (recombine results);
- acknowledgment and delivery tracking for agent-to-agent messages;
- structured negotiation protocols (propose-counter-accept-reject);
- priority-aware message routing;
- communication pattern templates.

### Owns
`BroadcastMessage`, `MulticastGroup`, `ConversationBranch`, `BranchMergeOperation`, `MessageAcknowledgment`, `NegotiationSession`, `CommunicationPatternTemplate`

### Depends on
`interactions`, `fleets`, `execution`

### Publishes events
`communication.broadcast.sent`, `communication.branch.created`, `communication.branch.merged`, `communication.ack.received`, `communication.negotiation.concluded`

---



## 7.35 `governance` bounded context (NEW)

### Responsibilities
- Judge agent role management (receive observer signals, evaluate against policies, emit structured verdicts)
- Enforcer agent role management (receive verdicts, execute enforcement actions: block, quarantine, notify, revoke-cert, log-and-continue)
- Observer → Judge → Enforcer pipeline configuration per fleet/workspace
- Governance chain validation and lifecycle
- Verdict and enforcement action persistence

### Owns
- `governance_verdicts` table
- `governance_enforcement_actions` table
- `governance_chain` config (stored on fleets and workspaces)

### Publishes events
- `governance.verdict.issued`
- `governance.enforcement.executed`

## 7.36 `a2a_gateway` bounded context (NEW)

### Responsibilities
- A2A Agent Card auto-generation from registry metadata
- A2A server mode: discovery endpoints, task submission, lifecycle management, SSE streaming
- A2A client mode: fetch external Agent Cards, submit tasks, parse responses
- External Agent Card caching with configurable TTL
- Policy enforcement on all A2A interactions (via tool gateway)

### Owns
- Agent Card generation logic (read-only projection of registry data)
- A2A task state tracking
- External Agent Card cache

### Depends on
- `registry` (agent profiles for Card generation)
- `policies` (enforcement on outbound A2A calls)
- `interactions` (map A2A tasks to internal interactions)

## 7.37 `notifications` bounded context (UPDATED again)

> **Update (v4):** Extended from 3 channels to 6 channels: in-app WebSocket, email (SMTP), webhook (HMAC-signed), Slack (incoming webhook or app), Microsoft Teams, SMS (Twilio or equivalent). Added outbound callback registration for external systems. Added webhook signing and delivery guarantees (at-least-once, idempotency keys, exponential backoff, dead-letter queue).



> **Update (v3):** Expanded from basic alerting to full user alert management. Added configurable alert settings per user (state transitions, delivery methods). Added per-interaction alert overrides. Added attention request consumption. Added WebSocket push for real-time alerts.

### Responsibilities
- User alert settings management (CRUD)
- Alert generation on interaction state changes (matching user preferences)
- Attention request consumption from `interaction.attention` Kafka topic
- WebSocket push for logged-in users
- Offline alert storage and delivery on next login

### Owns
- `user_alert_settings` table
- `user_alerts` table

## 7.38 `privacy_compliance` bounded context (NEW)

### Responsibilities
- Data subject rights handler (GDPR/CCPA): access, rectification, erasure, portability, restriction, objection
- Right-to-be-forgotten cascade engine across PostgreSQL, Qdrant, Neo4j, ClickHouse, OpenSearch, S3
- Tombstone audit records with cryptographic proof of deletion completion
- Data residency enforcement (per-workspace region, query-time cross-region transfer blocks)
- DLP pipeline integration (scans outbound responses, tool payloads, logs, artifacts)
- Privacy Impact Assessment (PIA) workflow with privacy officer approval
- Consent and disclosure tracking

### Owns
`DataSubjectRequest`, `DeletionTombstone`, `DataResidencyConfig`, `DlpRule`, `DlpEvent`, `PrivacyImpactAssessment`, `ConsentRecord`

### Publishes events
`privacy.dsr.received`, `privacy.dsr.completed`, `privacy.deletion.cascaded`, `privacy.dlp.event`, `privacy.pia.approved`

### Depends on
All bounded contexts owning PII (auth, accounts, workspaces, interactions, memory, audit)

## 7.39 `security_compliance` bounded context (NEW)

### Responsibilities
- SBOM generation per release (SPDX + CycloneDX)
- Vulnerability scan result ingestion and release gating
- Penetration test tracking (schedules, findings, remediation status, attestation)
- Secret rotation scheduling with dual-credential windows
- JIT credential issuance and revocation for privileged operations
- Cryptographic audit chain (hash-chain integrity verification, export with signatures)
- Compliance evidence substrate for SOC2/ISO27001/HIPAA/PCI-DSS

### Owns
`SoftwareBillOfMaterials`, `VulnerabilityScanResult`, `PenetrationTest`, `PenTestFinding`, `SecretRotationSchedule`, `JitCredentialGrant`, `AuditChainEntry`, `ComplianceControl`, `ComplianceEvidence`

### Publishes events
`security.sbom.published`, `security.scan.completed`, `security.pentest.finding.raised`, `security.secret.rotated`, `security.jit.issued`, `security.jit.revoked`, `security.audit.chain.verified`

### Depends on
`auth`, `audit`, `trust`, all contexts with secrets

## 7.40 `cost_governance` bounded context (NEW)

### Responsibilities
- Cost attribution per execution (model tokens × price, compute seconds × rate, storage bytes × rate × duration, platform overhead)
- Chargeback and showback aggregation by workspace, agent, fleet, model, user, workflow
- Budget enforcement (soft alerts at thresholds, hard caps with admin override)
- End-of-period forecasting
- Cost intelligence dashboard data feed (anomaly detection, cost-per-quality metrics)

### Owns
`CostAttribution`, `WorkspaceBudget`, `BudgetAlert`, `CostForecast`, `CostAnomaly`

### Publishes events
`cost.execution.attributed`, `cost.budget.threshold.reached`, `cost.budget.exceeded`, `cost.anomaly.detected`, `cost.forecast.updated`

### Depends on
`execution`, `analytics`, `workspaces`, `registry`

## 7.41 `multi_region_ops` bounded context (NEW)

### Responsibilities
- Region configuration management (primary, secondary, data residency rules)
- Cross-region replication monitoring (PostgreSQL lag, Kafka MirrorMaker lag, S3 replication status)
- RPO/RTO tracking and alerting on drift
- Failover orchestration and runbook execution
- Maintenance mode management (schedule, enable, disable, drain in-flight work)

### Owns
`RegionConfig`, `ReplicationStatus`, `FailoverPlan`, `MaintenanceWindow`

### Publishes events
`region.replication.lag`, `region.failover.initiated`, `region.failover.completed`, `maintenance.mode.enabled`, `maintenance.mode.disabled`

### Depends on
All stateful services (read-only monitoring)

## 7.42 `model_catalog` bounded context (NEW)

### Responsibilities
- Approved model catalog management (add/update/approve/deprecate models)
- Model card storage (capabilities, training cutoff, limitations, safety evals, bias assessments)
- Model fallback policy configuration
- Per-agent / per-step / per-workspace model binding validation
- Model provider credential management (rotation via security_compliance)
- Model usage tracking for cost attribution

### Owns
`ModelCatalogEntry`, `ModelCard`, `ModelFallbackPolicy`, `ModelProviderCredential` (reference only; secret stored in vault)

### Publishes events
`model.catalog.updated`, `model.card.published`, `model.fallback.triggered`, `model.deprecated`

### Depends on
`trust` (for certification), `security_compliance` (for credential rotation)

## 7.43 `localization` bounded context (NEW)

### Responsibilities
- Locale file management (translations for all user-facing strings)
- Translation workflow integration (pull to translation vendor, merge back)
- Per-user locale preferences
- Number, date, currency formatting helpers
- Content locale detection for agent responses (optional)

### Owns
`LocaleFile`, `TranslationKey`, `UserLocalePreference`

### Depends on
`accounts` (user preferences), frontend UI build pipeline

## 8. Satellite services outside the monolith

## 8.1 Runtime Controller (Go)

> **Update (v3):** Added warm pool manager (pre-initialized pods, <2s dispatch latency, configurable pool size per workspace). Added secrets injection from vault — secrets mounted as env vars in pod, never in LLM context. Added secret detection validation: if secret pattern found in LLM prompt, block and alert.

### Why separate
Kubernetes orchestration focus, gRPC-heavy, execution-plane isolation, future multi-backend adapters.

### Responsibilities
Launch/inspect/stop runtime workloads, maintain runtime state, reconcile drift, stream events to Kafka, manage warm pools and dedicated-pod modes.

### Primary interface
`RuntimeControlService` over gRPC.

## 8.2 Sandbox Manager (Go)

### Responsibilities
Sandbox template resolution, create/destroy sandbox workloads including code-as-reasoning sandboxes, execute language-specific runs, collect logs/outputs/artifacts, enforce restrictions.

### Primary interface
`SandboxService` over gRPC.

## 8.3 HostOps Broker

### Responsibilities
Structured high-risk operation execution, approval enforcement, JIT tokens, command validation, privileged adapter execution, full audit.

### Primary interface
`HostOpsService` over gRPC or controlled REST/gRPC bridge.

## 8.4 Browser Automation Worker

### Responsibilities
Browser session lifecycle, snapshot capture, trajectory capture, anti-abuse checks, optional human handoff.

## 8.5 Reasoning Engine

> **Update (v3):** Added DEBATE mode (Chain of Debates: N agents × structured rounds of position→critique→rebuttal→synthesis). Added SELF_CORRECTION mode (iterative refinement with convergence detection). Added `compute_budget` parameter for Scaling Inference Law. Added structured reasoning trace export (JSON: technique, steps, tool calls, quality scores, tokens, budget utilization). (Go) (NEW)

### Why separate
Reasoning budget tracking requires sub-millisecond latency (Redis-backed hot state). Self-correction convergence detection involves tight numerical loops. Tree-of-thought branch management requires concurrent goroutine coordination. gRPC bidirectional streaming to agent runtimes demands Go's native performance.

### Responsibilities
- Reasoning mode selection and budget allocation with real-time enforcement;
- chain-of-thought trace coordination;
- tree-of-thought concurrent branch management and evaluation;
- adaptive reasoning depth adjustment;
- code-as-reasoning bridge to sandbox services;
- self-correction loop execution with convergence detection;
- draft-critique-revision triple management;
- iteration and cost limit enforcement;
- human escalation routing on non-convergence;
- multi-agent review loop coordination.

### Primary interface
`ReasoningEngineService` over gRPC.

### gRPC methods
- `SelectReasoningMode(SelectReasoningModeRequest) returns (ReasoningModeConfig)`
- `AllocateReasoningBudget(AllocateReasoningBudgetRequest) returns (ReasoningBudgetEnvelope)`
- `StreamReasoningTrace(stream ReasoningTraceEvent) returns (ReasoningTraceAck)`
- `CreateTreeBranch(CreateTreeBranchRequest) returns (TreeBranchHandle)`
- `EvaluateTreeBranches(EvaluateTreeBranchesRequest) returns (BranchSelectionResult)`
- `StartSelfCorrectionLoop(StartSelfCorrectionRequest) returns (SelfCorrectionHandle)`
- `SubmitCorrectionIteration(CorrectionIterationEvent) returns (ConvergenceResult)`
- `GetReasoningBudgetStatus(GetBudgetStatusRequest) returns (BudgetStatusResponse)`

### State management
- **Hot state (Redis):** active reasoning budgets, live convergence metrics, tree branch scores, tournament leaderboards
- **Cold state (PostgreSQL):** completed traces, correction records, budget history, quality evaluations
- **Large payloads (Object storage):** full CoT dumps, ToT branch payloads, correction artifacts

## 8.6 Simulation Controller (Go) (NEW)

### Why separate
Requires dedicated pod lifecycle management with strict production isolation. Infrastructure-heavy with network policy enforcement.

### Responsibilities
Simulation sandbox provisioning, simulation pod lifecycle, production isolation enforcement, simulation artifact collection, simulation resource accounting.

### Primary interface
`SimulationControlService` over gRPC.

### gRPC methods
- `CreateSimulation(CreateSimulationRequest)`
- `GetSimulationStatus(GetSimulationStatusRequest)`
- `StreamSimulationEvents(StreamSimulationEventsRequest)`
- `TerminateSimulation(TerminateSimulationRequest)`
- `CollectSimulationArtifacts(CollectSimulationArtifactsRequest)`

## 8.7 Stateful dependencies

All stores are deployed from day 1 with workload-appropriate technology:

- **PostgreSQL 16+** — relational system-of-record, append-only journal, governance, audit
- **Qdrant** — vector search for semantic retrieval, recommendation, similarity testing
- **Neo4j 5.x** — knowledge graph for relationship traversal, dependency analysis, provenance chains
- **ClickHouse** — OLAP analytics for usage, cost intelligence, behavioral drift, fleet profiling
- **Redis 7+ (Cluster)** — caching, reasoning budget hot state, tournament leaderboards, distributed locks
- **OpenSearch 2.x** — full-text marketplace discovery, natural-language search, faceted navigation
- **Apache Kafka** — durable event backbone
- **S3-compatible object storage** — artifacts, traces, evidence, large payloads
- **Observability collectors** — OpenTelemetry, Prometheus, Grafana, Jaeger

---

## 9. Internal interface architecture

## 9.1 Public API style

REST/JSON with versioning. Examples:
- `/api/v1/auth/*`
- `/api/v1/workspaces/*`
- `/api/v1/agents/*`
- `/api/v1/workflows/*`
- `/api/v1/interactions/*`
- `/api/v1/fleets/*`
- `/api/v1/trust/*`
- `/api/v1/marketplace/*`
- `/api/v1/reports/*`
- `/api/v1/context/*` (NEW)
- `/api/v1/reasoning/*` (NEW)
- `/api/v1/compositions/*` (NEW)
- `/api/v1/discovery/*` (NEW — scientific discovery)
- `/api/v1/simulations/*` (NEW)
- `/api/v1/agentops/*` (NEW)
- `/api/v1/testing/*` (NEW)

## 9.2 WebSocket contracts

Channel families:
- `execution:<execution_id>`
- `interaction:<interaction_id>`
- `conversation:<conversation_id>`
- `workspace:<workspace_id>`
- `fleet:<fleet_id>`
- `alerts:<user_id>`
- `operator:<scope>`
- `reasoning:<execution_id>` (NEW)
- `correction:<execution_id>` (NEW)
- `simulation:<simulation_id>` (NEW)
- `testing:<test_run_id>` (NEW)

## 9.3 gRPC interfaces

### RuntimeControlService (Go)
- `LaunchRuntime`, `GetRuntime`, `PauseRuntime`, `ResumeRuntime`, `StopRuntime`, `StreamRuntimeEvents`, `CollectRuntimeArtifacts`

### ReasoningEngineService (Go) (NEW)
- `SelectReasoningMode(SelectReasoningModeRequest) returns (ReasoningModeConfig)`
- `AllocateReasoningBudget(AllocateReasoningBudgetRequest) returns (ReasoningBudgetEnvelope)`
- `StreamReasoningTrace(stream ReasoningTraceEvent) returns (ReasoningTraceAck)`
- `CreateTreeBranch(CreateTreeBranchRequest) returns (TreeBranchHandle)`
- `EvaluateTreeBranches(EvaluateTreeBranchesRequest) returns (BranchSelectionResult)`
- `StartSelfCorrectionLoop(StartSelfCorrectionRequest) returns (SelfCorrectionHandle)`
- `SubmitCorrectionIteration(CorrectionIterationEvent) returns (ConvergenceResult)`
- `GetReasoningBudgetStatus(GetBudgetStatusRequest) returns (BudgetStatusResponse)`
- `StreamBudgetEvents(StreamBudgetEventsRequest) returns (stream BudgetEvent)`

### SandboxService (Go)
- `CreateSandbox`, `ExecuteSandboxStep`, `StreamSandboxLogs`, `TerminateSandbox`, `CollectSandboxArtifacts`

### HostOpsService
- `RequestOperation`, `ApproveOperation`, `RejectOperation`, `ExecuteApprovedOperation`, `GetOperationAuditTrail`

### SimulationControlService (Go) (NEW)
- `CreateSimulation`, `GetSimulationStatus`, `StreamSimulationEvents`, `TerminateSimulation`, `CollectSimulationArtifacts`

## 9.4 Kafka event model

Important event families (additions in bold):
- interaction lifecycle
- workflow dispatch
- runtime lifecycle
- sandbox lifecycle
- connector ingress/delivery
- marketplace/trust projection refresh
- evaluation results
- alerts and anomalies
- fleet observer findings
- **context assembly and quality events**
- **reasoning trace milestones and budget events**
- **self-correction iteration and convergence events**
- **resource optimization routing events**
- **fleet health aggregation events**
- **behavioral drift signals**
- **simulation events**
- **testing results**
- **broadcast and multicast messages**
- **agentops behavioral events**

## 9.5 A2A and MCP protocols

### A2A
Public HTTP(S) endpoint, JSON-RPC-style for task exchange, agent cards with maturity level, remote task identifiers with correlation, optional streaming, async completion signals.

### MCP
Capability mapping of tools/resources/prompts, external MCP client adapters, internal platform resource exposure, policy-aware capability negotiation.

---

## 10. Canonical domain model

## 10.1 Identity and tenancy entities
`User`, `ServiceAccount`, `Session`, `Workspace`, `Membership`, `WorkspaceGoal`, `WorkspaceSettings`

## 10.2 Agent and fleet entities
`Agent`, `AgentRevision`, `AgentShareGrant`, `AgentMaturityRecord`, `Fleet`, `FleetMember`, `FleetTopology`, `ObserverAssignment`, `FleetPersonalityProfile`

## 10.3 Workflow and execution entities
`WorkflowDefinition`, `WorkflowVersion`, `CompiledWorkflowIR`, `Execution`, `ExecutionEvent`, `Checkpoint`, `DispatchLease`, `ApprovalWait`, `CompensationRecord`, `ReasoningTraceRef`, `SelfCorrectionIterationRef`

## 10.4 Interaction entities
`Conversation`, `Interaction`, `InteractionMessage`, `WorkspaceGoalMessage`, `RemoteTaskLink`, `ConversationBranch`, `BranchMergeRecord`

## 10.5 Governance entities
`Policy`, `PolicyAttachment`, `Certification`, `CertificationEvidenceRef`, `TrustSignal`, `Approval`, `BlockedActionRecord`, `MaturityGateRule`, `PrivacyImpactAssessment`

## 10.6 Runtime and sandbox entities
`RuntimeInstance`, `RuntimeHeartbeat`, `RuntimeArtifactRef`, `SandboxRun`, `SandboxArtifactRef`, `PrivilegedOperationRequest`, `SimulationRun`, `DigitalTwin`

## 10.7 Context engineering entities (NEW)
`ContextAssemblyRecord`, `ContextQualityScore`, `ContextProvenanceEntry`, `ContextBudgetEnvelope`, `ContextCompactionStrategy`, `ContextAbTest`, `ContextDriftAlert`, `ContextEngineeringProfile`

## 10.8 Reasoning entities (NEW)
`ReasoningModeConfig`, `ReasoningBudgetEnvelope`, `ChainOfThoughtTrace`, `TreeOfThoughtBranch`, `ReasoningQualityScore`, `AdaptiveDepthPolicy`, `CodeAsReasoningRequest`

## 10.9 Self-correction entities (NEW)
`SelfCorrectionLoop`, `CorrectionIteration`, `ConvergenceMetric`, `CorrectionPolicy`, `CorrectionAnalytics`, `ProducerReviewerBinding`

## 10.10 Resource optimization entities (NEW)
`TaskComplexityClassification`, `ModelRoutingDecision`, `ResourcePrediction`, `LearnedAllocationPolicy`, `CostIntelligenceReport`, `GracefulDegradationEvent`

## 10.11 Composition and discovery entities (NEW)
`AgentBlueprint`, `FleetBlueprint`, `CompositionRequest`, `CompositionAuditEntry`, `Hypothesis`, `HypothesisCritique`, `TournamentRanking`, `EloScore`, `DiscoveryExperiment`, `DiscoveryEvidence`

## 10.12 Privacy entities (NEW)
`PrivacyBudget`, `DifferentialPrivacyConfig`, `DataMinimizationPolicy`, `AnonymizationRule`

## 10.13 Marketplace intelligence entities (NEW)
`AgentRecommendation`, `QualitySignalAggregate`, `ContextualDiscoverySuggestion`, `TrendingAgentProjection`

## 10.14 Fleet learning entities (NEW)
`FleetPerformanceProfile`, `FleetTournament`, `FleetAdaptationRule`, `CrossFleetTransferRequest`

## 10.15 AgentOps entities (NEW)
`BehavioralVersion`, `CiCdGateResult`, `CanaryDeployment`, `BehavioralRegressionAlert`, `AgentHealthScore`, `RetirementWorkflow`

## 10.16 Testing entities (NEW)
`SemanticSimilarityResult`, `AdversarialTestCase`, `RobustnessTestRun`, `BehavioralDriftMetric`, `CoordinationTestResult`, `HumanAiGrade`, `GeneratedTestSuite`

## 10.17 Communication entities (NEW)
`BroadcastMessage`, `MulticastGroup`, `MessageAcknowledgment`, `NegotiationSession`, `CommunicationPatternTemplate`

## 10.18 Search, memory, and evaluation entities
`SearchProjection`, `TrajectoryRecord`, `PatternAsset`, `EvaluationRun`, `JudgeVerdict`, `UsageEvent`, `KpiSeries`

## 10.19 Important relationship rules

- A `Conversation` contains many `Interaction`s and may have `ConversationBranch`es.
- An `Interaction` may point to one active `Execution` lineage and zero or more remote A2A tasks.
- An `Agent` has many immutable `AgentRevision`s, each with an `AgentMaturityRecord`.
- A `Certification` binds to a specific target revision or fleet.
- A `Fleet` groups `AgentRevision` participants through topology descriptors, runtime policies, and `FleetPersonalityProfile`.
- `ExecutionEvent`s reference `Execution`, `Interaction`, and optionally `Fleet`, `RuntimeInstance`, `ReasoningTraceRef`, and `SelfCorrectionIterationRef`.
- `ContextAssemblyRecord`s link to `Execution` and carry `ContextProvenanceEntry` chains and `ContextQualityScore`.
- `ChainOfThoughtTrace`s and `TreeOfThoughtBranch`es link to `Execution` through `ReasoningTraceRef`.
- `SelfCorrectionLoop`s link to `Execution` and contain ordered `CorrectionIteration`s with `ConvergenceMetric`.
- `TrustSignal`s are projections that include `AgentHealthScore` and `QualitySignalAggregate` data.
- `SimulationRun`s are isolated from production `Execution`s and carry `SimulationIsolationPolicy`.
- `BehavioralVersion`s form a time-series linked to `AgentRevision`s.

---

## 11. Workflow engine software architecture

## 11.1 Compilation pipeline

Input path:
1. YAML parse
2. Schema validation
3. Reference resolution
4. Semantic validation (including reasoning mode hints and context budget constraints)
5. Compatibility checks
6. IR generation (preserving step identities, data bindings, retry/timeout policies, branching semantics, parallel branches, compensation hooks, approval checkpoints, trigger definitions, update compatibility markers, reasoning mode hints, context budget constraints)
7. Version publication

## 11.2 Execution journal

Append-only. Stores: created, queued, dispatched, runtime-started, sandbox-requested, waiting-for-approval, resumed, retried, completed, failed, canceled, compensated, **reasoning-trace-emitted**, **self-correction-started**, **self-correction-converged**, **self-correction-escalated**, **context-assembled**, **context-compacted**.

## 11.3 Scheduler

Responsibilities:
- compute runnable steps;
- allocate priority with reasoning budget awareness;
- enforce concurrency rules;
- obtain dispatch lease;
- issue runtime or connector work with reasoning config and context engineering profile;
- re-queue on retry;
- pause on approval;
- trigger compensation;
- dynamic reprioritization on new events, deadlines, or severity changes.

## 11.4 Hot updates and intervention

Supports manual variable updates, pause/resume, skip under governance, compatible hot patches, incompatibility rejection, context injection/pruning mid-execution, and audit of every intervention.

## 11.5 Replay, resume, rerun

- `replay` = state reconstruction from journal, reasoning traces, and artifacts
- `resume` = continuation of eligible interrupted execution
- `rerun` = new lineage from same or changed input set

---

## 12. Agent runtime software architecture

## 12.1 Runtime package layout

Internal layers:
- startup contract loader
- prompt/context assembler (delegates to context engineering service)
- policy guard and tool gateway client
- model router (delegates to resource optimization service) and failover handler
- reasoning mode executor (delegates to reasoning orchestration)
- task plan/execution loop
- self-correction loop executor (delegates to self-correction engine)
- tool execution bridge
- sandbox request bridge (including code-as-reasoning)
- event emitter
- artifact writer
- A2A client
- MCP client

## 12.2 Startup contract

Runtime receives:
- runtime instance id
- workspace scope
- agent revision id and digest
- policy bundle reference
- trust tier
- model binding and credential refs
- prompt asset selection
- context assembly inputs
- correlation identifiers
- budget envelope (tokens, cost, time, reasoning)
- context engineering profile reference
- reasoning mode config
- self-correction policy reference
- agent maturity level

## 12.3 Context assembly

Context assembly is delegated to the context engineering service. The runtime requests context, receives a scored and provenanced bundle, and integrates it into the model call. The runtime does not directly concatenate context.

## 12.4 Tool invocation path

1. Runtime chooses tool/resource/agent-as-tool candidate
2. Request goes through tool gateway policy validation
3. Request routed to local plugin, MCP resource, A2A peer, or sandbox
4. Result normalized and returned with trace linkage

## 12.5 Reasoning execution

1. Reasoning mode selector determines strategy (direct, CoT, ToT, ReAct, code-as-reasoning, debate)
2. Reasoning budget manager allocates tokens, rounds, and time
3. Runtime executes with selected mode, emitting trace events
4. For code-as-reasoning, sandbox bridge handles computation
5. For tree-of-thought, branch manager coordinates parallel explorations
6. Reasoning quality evaluator assesses trace quality

## 12.6 Self-correction execution

1. Step output is evaluated against quality criteria
2. If below threshold, self-correction policy determines action
3. Producer-reviewer binding identifies which agent/evaluator critiques
4. Correction iteration executes: critique → revise → re-evaluate
5. Convergence detector assesses quality delta between iterations
6. Loop terminates on convergence, iteration limit, cost cap, or human escalation

## 12.7 Review, reflection, debate

Supports self-reflection steps, producer-reviewer loops, producer-critic flows, debate/consensus flows, ReAct loops, plan generation/replanning, generate-debate-evolve cycles. All patterns are represented in typed runtime state.

---

## 13. Sandbox and privileged-operation architecture

## 13.1 Sandbox execution model

Each sandbox run is a separate execution cell with language template, resource budget, timeout, filesystem policy, network egress policy, artifact upload path, and event stream. Code-as-reasoning sandboxes use the same infrastructure with specific templates that return structured computation results.

## 13.2 HostOps separation

Privileged actions use distinct path: structured request → policy validation → approval → JIT credential → broker-side execution → full audit.

---

## 14. Registry, marketplace, trust, and workbench internals

## 14.1 Registry internals

Normalized metadata tables with maturity classification, reasoning mode support, and context engineering profile references. Versioned schemas, write-side services, projection triggers, policy-aware query layer.

## 14.2 Marketplace internals

Query flow: resolve scope → apply access/maturity/trust constraints → structured + semantic search (OpenSearch + Qdrant) → join trust/quality signals → intelligent recommendation → ranked results.

## 14.3 Trust internals

Evidence ingestion, certification state machine, expiry/recertification, trust-signal publication including behavioral health scores and quality signal aggregates.

## 14.4 Workbench BFF pattern

The monolith exposes BFF routes for consumer, creator, trust, operator, and evaluator workbenches. Creator workbench integrates AI-assisted composition. Operator workbench includes reasoning budget monitoring, fleet health, and behavioral drift views.

---

## 15. Conversation, interaction, workspace, and fleet software semantics

## 15.1 Conversations and interactions

Conversation is the super-container. Interaction is the bounded task unit. Conversations support branching (fork into parallel threads) and merging (recombine results). Multi-interaction concurrency is supported without state collision.

## 15.2 Workspace super-context

A workspace carries messages, goals, subscribed agents/fleets, policy context, connector context, reusable memory context, and fleet personality preferences.

## 15.3 Fleets

Modeled as managed teams with topology descriptors, delegation rules, aggregation rules, escalation rules, degraded-operation policies, observer assignments, personality profiles, lifecycle automation, performance profiles, and adaptation rules.

---

## 16. Memory, retrieval, and knowledge architecture

## 16.1 Short-term vs long-term memory

Short-term: conversation context, interaction state, execution working state, prompt assembly cache.
Long-term: vector memory (Qdrant), pattern store, trajectory store, graph views (Neo4j), evidence-linked knowledge artifacts.

## 16.2 Retrieval coordinator

Orchestrates keyword + vector + optional graph retrieval, ranks by authority and freshness, detects contradiction, requests follow-up retrieval, gates ambiguous evidence for escalation.

## 16.3 Learning consolidation

Workers perform: retrieve → judge → distill → consolidate → promote to reusable pattern if approved. Privacy-preserving constraints applied during cross-scope consolidation.

---

## 17. Evaluation, experimentation, and prioritization

## 17.1 Evaluation framework

Supports offline benchmarks, online scoring, human review, LLM-as-judge, stored verdicts, trajectory analysis, multi-agent cooperation scoring, semantic similarity scoring, adversarial testing, statistical robustness testing, behavioral drift detection.

## 17.2 Scientific discovery support

Supports hypothesis generation, Elo-based tournament ranking, generate-debate-evolve cycles, experiment coordination, and discovery evidence provenance.

## 17.3 Priority scheduler

Priority is a native scheduler input accepting urgency, importance, risk, severity, due date, SLA pressure, dependency status, policy-driven escalation, reasoning budget remaining, and strategic alignment.

---

## 18. Connector framework software architecture

Connector plugin contract: credential binding, inbound normalization, outbound delivery, retry semantics, dead-letter handling, observability hooks, scope enforcement.

---

## 19. Build, release, and factory architecture

## 19.1 Agent factory

Templates, SDKs, build descriptors, publication readiness checks, required telemetry/identity hooks, AI-assisted composition integration.

## 19.2 Fleet factory

Topology descriptors, reference orchestration patterns, resilience test packs, lifecycle automation, governance and certification hooks, personality profile templates.

## 19.3 Delivery pipeline

Static analysis → dependency hygiene → unit tests → integration tests → resilience tests → certification readiness → signed artifacts + SBOM → auditable promotion → governance-aware CI/CD gating → canary deployment → behavioral regression monitoring → automatic promotion or rollback.

---

## 20. Observability and diagnostics software architecture

## 20.1 Standard telemetry contract

All major components emit structured logs, metrics, traces, correlation identifiers, runtime/execution status changes, reasoning trace milestones, self-correction events, context quality signals, and behavioral drift indicators.

## 20.2 Product-aware observability

Beyond generic infra telemetry: workflow step transitions, tool invocations, sandbox launches, approval waits, certification changes, fleet health status, blocked/sanitized actions, queue lag, replay actions, reasoning budget consumption, self-correction convergence, context quality trends, behavioral drift alerts, cost intelligence metrics.

## 20.3 Diagnostics

Operator layer exposes doctor-style checks for: PostgreSQL reachability, Qdrant reachability, Neo4j reachability, ClickHouse reachability, Redis reachability, OpenSearch reachability, Kafka health/lag, runtime-controller reachability, reasoning-engine reachability, sandbox-manager reachability, simulation-controller reachability, object storage access, connector credentials/callbacks, model provider availability, policy bundle freshness.

---

## 21. Extraction roadmap

### Stage 1 — initial production shape
- Control-plane modular monolith with 8 Python profiles
- Runtime controller (Go), reasoning engine (Go), sandbox manager (Go), simulation controller (Go) as separate services
- HostOps broker separate
- PostgreSQL, Qdrant, Neo4j, ClickHouse, Redis, OpenSearch, Kafka, object storage as dedicated stores

### Stage 2 — likely first extractions
- Evaluation service if scoring volume grows
- Certification service if trust workflows need independent cadence
- Context engineering service if assembly latency becomes critical (may warrant Go extraction)
- Marketplace intelligence service if recommendation volume grows

### Stage 3 — later extractions if justified
- Registry service as separate write-side service
- Marketplace/search service as separate BFF/query service
- Interactions service as separate real-time domain service
- Fleet orchestration service if compliance pressure warrants
- AgentOps service if behavioral lifecycle management needs independent cadence
- Testing engine if test execution volume grows significantly

No extraction should happen only because the logical domain exists. Extraction must be justified by data.

---

## 22. Software coverage map by requirement domain

| Requirement family | Key IDs | Primary software realization |
|---|---|---|
| Control plane/data plane split | TR-001–TR-003 | Modular monolith + runtime controller + sandbox manager + simulation controller |
| Python/FastAPI/Pydantic/SQLAlchemy baseline | TR-004–TR-010 | Control-plane repo structure and entrypoints |
| Storage and identifiers | TR-011–TR-018 | PostgreSQL schema + Qdrant + Neo4j + ClickHouse + Redis + OpenSearch, object storage, append-only journal |
| Agent artifacts | FR-040–FR-049, TR-019–TR-023 | Agent ingest, registry, immutable revisions, maturity classification |
| Public API and WebSockets | FR-124–FR-128, TR-024–TR-030 | API profile, WebSocket profile |
| Auth, RBAC, secrets | FR-007–FR-014, TR-031–TR-039 | `auth`, `accounts`, `policies`, `audit` |
| Execution fabric | FR-109–FR-112, TR-040–TR-046 | Runtime controller adapter interface |
| Agent runtime lifecycle | FR-093–FR-098, TR-047–TR-053 | Runtime controller + runtime startup contract + self-correction + reasoning |
| Sandboxes | FR-099–FR-104, TR-054–TR-060 | Sandbox manager + code-as-reasoning templates |
| Workflow semantics | FR-066–FR-089, TR-061–TR-070 | `workflows` + `execution` + reasoning mode hints |
| Connectors | FR-031–FR-039, TR-071–TR-075 | `connectors` + `notifications` |
| Usage and metering | FR-121, TR-076–TR-078 | `analytics` + cost intelligence |
| Observability | FR-120, FR-299, TR-079–TR-083 | Monitor projections + reasoning trace telemetry |
| Security hardening | FR-105–FR-108, TR-084–TR-088 | HostOps broker, sandbox policies |
| Installer and ops | FR-001–FR-006, TR-095–TR-098 | Ops CLI + deploy manifests |
| Testing and release | TR-099–TR-110 | CI/CD, benchmark harness, governance-aware gating |
| Governance and enforcement | FR-161–FR-166, TR-117–TR-128 | `policies` + `trust` + privacy module |
| Integrity and evidence | FR-280–FR-283, TR-129–TR-134 | Proof/evidence stores + certification |
| Memory, search, learning | FR-156–FR-160, FR-194–FR-200, TR-135–TR-141, TR-175–TR-182 | `memory` + retrieval coordinator + Qdrant + Neo4j |
| Plugin and browser | FR-167–FR-173, TR-146–TR-152 | Plugin SDK, extension registry |
| PromptOps and outputs | FR-174–FR-183, TR-160–TR-166, TR-212–TR-214 | `promptops` |
| Advanced orchestration | FR-184–FR-193, TR-167–TR-174 | Workflow engine + orchestrator + reasoning patterns |
| Safety and guardrails | FR-201–FR-211, TR-183–TR-190 | Safety pipeline, approval gates |
| Evaluation and improvement | FR-212–FR-218, TR-191–TR-197 | `evaluation` + `analytics` |
| Prioritization | FR-219–FR-223, TR-198–TR-201 | `execution` scheduler + priority engine |
| Exploration workflows | FR-224–FR-228, TR-202–TR-205 | `scientific_discovery` |
| A2A and MCP | FR-229–FR-233, TR-206–TR-211, TR-307 | A2A gateway + MCP gateway |
| Ecosystem management | FR-234–FR-299, TR-215–TR-289, TR-309 | `registry`, `marketplace`, `interactions`, `trust`, `workbenches`, `fleets`, `monitor` |
| Factory and AgentOps | FR-300–FR-307, TR-290–TR-300 | Templates, SDKs, validation pipelines |
| Microagent baseline | TR-301–TR-308 | Runtime templates, operational endpoints |
| **Context engineering** | FR-308–FR-314, TR-310–TR-315 | `context_engineering` bounded context |
| **Agent maturity** | FR-315–FR-319, TR-316–TR-319 | `registry` maturity records + `policies` maturity gates |
| **Self-correction** | FR-320–FR-325, TR-320–TR-323 | `self_correction` bounded context |
| **Advanced reasoning** | FR-326–FR-332, TR-324–TR-329 | `reasoning` bounded context |
| **Resource optimization** | FR-333–FR-340, TR-330–TR-336 | `resource_optimization` bounded context |
| **Agent-builds-agent** | FR-341–FR-345, TR-337–TR-339 | `agent_composition` bounded context |
| **Scientific discovery** | FR-346–FR-351, TR-340–TR-343 | `scientific_discovery` bounded context |
| **Privacy** | FR-352–FR-356, TR-344–TR-347 | `privacy` bounded context |
| **Marketplace intelligence** | FR-357–FR-361, TR-348–TR-350 | `marketplace_intelligence` bounded context |
| **Fleet learning** | FR-362–FR-366, TR-351–TR-354 | `fleet_learning` bounded context |
| **Advanced communication** | FR-367–FR-372, TR-355–TR-358 | `communication` bounded context |
| **Agent simulation** | FR-373–FR-378, TR-359–TR-362 | `simulation` bounded context + simulation controller |
| **AgentOps** | FR-379–FR-384, TR-363–TR-368 | `agentops` bounded context |
| **Semantic/behavioral testing** | FR-385–FR-391, TR-369–TR-375 | `testing` bounded context |

---

## 23. Final confirmation

This software architecture covers the full target platform shape including all 15 new requirement domains and explicitly includes all major requirement families:
- modular monolith control-plane design with 8 Python runtime profiles;
- Go reasoning engine as a dedicated satellite service alongside runtime controller;
- 34 bounded contexts (21 original + 13 new, with reasoning and self-correction as thin coordination layers in Python backed by Go execution);
- Go satellite services: runtime controller, reasoning engine, sandbox manager, simulation controller, HostOps broker;
- registry, marketplace, monitor, interactions, and workbenches;
- deterministic workflow engine with reasoning and self-correction support;
- fleets, observer roles, fleet learning, and fleet personality profiles;
- trust and certification with privacy impact assessment;
- prompt/context/output operations with context engineering as a first-class discipline;
- advanced reasoning with CoT/ToT persistence, adaptive depth, and code-as-reasoning;
- self-correction with convergence detection and multi-agent review;
- resource-aware optimization with dynamic model switching and cost intelligence;
- AI-assisted agent and fleet composition;
- scientific discovery with hypothesis generation and tournament ranking;
- privacy-preserving collaboration with differential privacy and data minimization;
- marketplace intelligence with recommendation and quality signals;
- advanced communication with broadcast/multicast, conversation branching, and negotiation;
- agent simulation with digital twins and behavioral prediction;
- AgentOps with behavioral versioning, governance-aware CI/CD, and canary deployment;
- semantic and behavioral testing with adversarial generation and drift detection;
- A2A and MCP interoperability;
- Kafka-based event coordination;
- Kubernetes-oriented production deployment;
- local installation support;
- factory-style delivery and governance.

The design is therefore suitable as the software architecture baseline for the current revised requirement set of **391 functional requirements + 375 technical requirements = 766 total requirements**.
