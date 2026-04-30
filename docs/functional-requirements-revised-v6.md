# Functional Requirements Specification v6 (v5 + UPD-035 Capstone)

## 0. Revision Intent, Scope Discipline, and Superseding Clarifications

This revision incorporates **Agentic Mesh** concepts and **Agentic Design Patterns** guidance where they translate into concrete product capabilities for the platform. It extends the prior baseline with new requirement domains inspired by both references, including context engineering, agent self-correction, reasoning architecture, resource-aware optimization, agent-builds-agent automation, scientific discovery patterns, privacy-preserving collaboration, marketplace intelligence, fleet-level learning, advanced communication patterns, agent simulation, AgentOps, and semantic/behavioral testing.

### 0.1 What This Revision Intentionally Adds
This revision elevates the following concerns to first-class product requirements:
- marketplace-driven discovery and trust-aware selection;
- registry-centric metadata, conversations, interactions, and policy/certification records;
- interaction server semantics for user-to-agent, agent-to-agent, and workspace-goal execution;
- event-driven mesh communication for asynchronous multiagent coordination;
- layered trust, certification, and lifecycle governance for both agents and fleets;
- workbench-oriented UX for consumers, creators, trust reviewers, and operators;
- fleet abstractions, observer agents, and factory-style standardization for large-scale delivery;
- **context engineering as a formal discipline with quality scoring, provenance tracking, and budget management;**
- **agent capability maturity levels and self-assessment;**
- **self-correction, reflection, and iterative refinement as first-class orchestration patterns;**
- **advanced reasoning support including chain-of-thought persistence, tree-of-thought branching, and reasoning budget allocation;**
- **resource-aware optimization including contextual pruning, proactive resource prediction, learned allocation policies, and graceful degradation;**
- **agent-builds-agent automation and AI-assisted agent composition;**
- **scientific discovery and co-scientist patterns including hypothesis generation, tournament ranking, and experimental validation;**
- **privacy-preserving collaboration including federated learning, differential privacy in memory, and secure multi-agent computation;**
- **marketplace intelligence including recommendation engines, automated agent matching, and usage-based quality signals;**
- **fleet-level learning and adaptation including fleet personality profiles and performance tournaments;**
- **advanced communication patterns including broadcast/multicast, conversation branching/merging, and acknowledgment tracking;**
- **agent simulation and digital twin mode for what-if scenarios and behavioral prediction;**
- **AgentOps formalization including behavioral versioning, semantic evaluation at fleet level, and governance-aware CI/CD;**
- **semantic and behavioral testing including similarity scoring, adversarial testing, and behavioral drift detection.**

### 0.2 What This Revision Intentionally Does Not Convert into Product Requirements
The following topics from the reference material are treated as **out of product scope** unless later requested explicitly:
- workforce transition, reskilling, and change-management programs;
- macroeconomic projections, societal impacts, and "agent economy" scenarios;
- legal personhood of agents, autonomous corporations, or extra-product legal constructs;
- non-product HR or organizational operating-model recommendations that do not map to platform capabilities.

### 0.3 Superseding Clarifications
The following interpretations supersede earlier wording where ambiguity exists:
1. **Catalog** shall be understood as a combination of **registry + marketplace + workbenches**, not merely a passive list of agents.
2. **Execution interaction** shall include **conversations, interactions, and workspace goals**, not only workflow runs.
3. **Multiagent runtime coordination** shall assume **event-driven messaging** as the default mesh coordination model for asynchronous agent collaboration, while REST remains mandatory for management, ingress, and external integration APIs.
4. **Agent governance** shall cover not only single-agent policy enforcement, but also **certification, trust signals, and lifecycle controls** visible to users and operators.
5. **Workspace** shall be understood not only as an ownership boundary, but also as a potential **shared execution super-context** for goal-oriented collaboration.
6. **Context engineering** shall be a first-class discipline covering context assembly, quality scoring, provenance tracking, compaction, and budget management.
7. **Agent maturity** shall be classifiable across capability levels from basic prompt-response through fully autonomous collaborative agents.
8. **Self-correction** shall be a native runtime capability, not only an optional pattern bolted on by prompt engineering.
9. **Resource optimization** shall be a continuous, adaptive process rather than a one-time configuration decision.

## 1. Scope and Product Positioning

This document defines the functional requirements for a multi-tenant agent orchestration platform inspired by OpenClaw concepts, but designed as a security-hardened product with deterministic workflow execution, isolated agent runtimes, isolated code sandboxes, and support for multiple deployment backends.

The platform shall support compatibility with OpenClaw-style agent packages while extending the model with enterprise-grade user management, workspace isolation, execution governance, and infrastructure abstraction.

## 2. Core Product Principles

- The platform shall distinguish between **trusted single-tenant mode** and **shared multi-tenant mode**.
- The platform shall support **deterministic workflow execution**, meaning that execution history, state transitions, step inputs, step outputs, retries, and approvals are recorded so that an execution can be resumed, replayed, or audited.
- The platform shall treat **agent packages**, **workflow definitions**, **execution logs**, **sandbox runs**, and **connector credentials** as first-class managed resources.
- The platform shall keep **security policy** separate from human-readable agent instructions such as `TOOLS.md`.
- The platform shall treat **context engineering** as a first-class discipline, not as an afterthought of prompt construction.
- The platform shall support **agent capability maturity assessment** so that agents can be classified, compared, and governed based on their actual sophistication level.

## 3. Installation, Bootstrap, and Deployment Modes

### FR-001 Deployment Modes
The system shall support installation in the following deployment modes:
1. local native installation;
2. Docker single-host installation;
3. Docker Swarm installation;
4. Kubernetes installation;
5. Incus cluster installation.

### FR-002 Database and Object Storage by Deployment Mode
The system shall use:
- SQLite for local native installations;
- SQLite optionally for non-HA Docker single-host development setups;
- PostgreSQL for Docker Swarm, Kubernetes, Incus cluster, and any HA or distributed deployment.

For object storage, the system shall use:
- local filesystem for local native installations;
- S3-compatible object storage for Docker, Docker Swarm, Kubernetes, Incus, and any networked deployment.
The platform shall not require any specific S3 provider. Any S3-compatible endpoint (Hetzner Object Storage, AWS S3, Cloudflare R2, Backblaze B2, Wasabi, DigitalOcean Spaces, self-hosted MinIO, or equivalent) shall be supported. For local development, a self-hosted MinIO instance may be used via Docker Compose, but MinIO shall not be a production dependency.

### FR-003 Installer Modes
The system shall provide:
- an interactive installer;
- a non-interactive installer for automation and CI/CD;
- a reconfiguration mode for changing settings after first installation;
- an upgrade mode for later platform versions.

### FR-004 Admin Bootstrap
During installation, the system shall:
- create an initial `admin` user;
- generate a temporary password;
- display that password in the CLI exactly once;
- require the admin to change the password at first login.

Additionally, the installer shall support **environment-variable-driven super admin provisioning** as an alternative to CLI bootstrap. When the following environment variables are present at install time, the installer provisions a `superadmin` user non-interactively:
- `PLATFORM_SUPERADMIN_USERNAME` (required) — the username of the super admin account.
- `PLATFORM_SUPERADMIN_EMAIL` (required) — the email address of the super admin.
- `PLATFORM_SUPERADMIN_PASSWORD` (optional) — the initial password. If absent, the installer generates a secure random password and writes it to stdout exactly once and to a Kubernetes Secret (`platform-superadmin-bootstrap`) that the installer flags for one-time retrieval and immediate deletion.
- `PLATFORM_SUPERADMIN_PASSWORD_FILE` (optional, alternative to `PLATFORM_SUPERADMIN_PASSWORD`) — path to a file containing the password, for compatibility with Docker secrets, sealed-secrets, and CI/CD secret stores.
- `PLATFORM_SUPERADMIN_MFA_ENROLLMENT` (optional, default `required_on_first_login`) — one of `required_on_first_login`, `required_before_first_login` (install fails if MFA cannot be enrolled), or `disabled` (not permitted in production; dev/test only with explicit `ALLOW_INSECURE=true`).
- `PLATFORM_SUPERADMIN_FORCE_PASSWORD_CHANGE` (optional, default `true`) — whether the super admin must change the password at first login.
- `PLATFORM_INSTANCE_NAME` (optional) — a display name for the platform instance, stored in platform settings and visible in the admin workbench.
- `PLATFORM_TENANT_MODE` (optional, default `single`) — one of `single` or `multi`; governs whether the super admin can create additional tenants.

The installer shall reject conflicting configurations (e.g., both `PASSWORD` and `PASSWORD_FILE`), refuse to run in production with `ALLOW_INSECURE=true`, and emit an audit chain entry recording the bootstrap method (CLI or env-var) and timestamp without logging any secret values.

### FR-004a Super Admin Distinction from Regular Admin
The platform shall distinguish between `admin` (tenant-scoped administrator — default role created on install) and `superadmin` (platform-wide administrator with cross-tenant visibility and the exclusive ability to: manage tenant lifecycle, configure platform-level settings, perform maintenance operations, rotate platform-level secrets, trigger failover, approve emergency JIT credentials at platform scope). A super admin can delegate or remove any administrator role in any tenant. A regular admin cannot escalate to super admin without explicit provisioning.

### FR-004b Bootstrap Idempotency and Safety
The installer's super-admin provisioning step shall be idempotent: running it multiple times with identical inputs shall not create duplicate users nor overwrite an existing super admin's password without an explicit `--force-reset-superadmin` flag. The `--force-reset-superadmin` flag shall require confirmation and shall emit a critical audit chain entry. In production deployments, the flag shall be rejected unless `ALLOW_SUPERADMIN_RESET=true` is also set, preventing accidental resets during routine reinstalls.

### FR-005 Installation Validation
The installer shall validate:
- selected deployment backend availability;
- database reachability;
- S3-compatible object storage reachability (endpoint connectivity, credential validity, bucket existence or creation permissions);
- storage location availability;
- secret generation;
- network prerequisites;
- connector prerequisites when selected.

### FR-006 Environment-Specific Artifacts
The installer shall be able to generate environment-specific deployment artifacts, including:
- local configuration files;
- Docker Compose or equivalent single-host artifacts;
- Docker Swarm stack artifacts;
- Kubernetes Helm values or manifests;
- Incus bootstrap or profile artifacts;
- S3-compatible object storage configuration (endpoint URL, region, credentials reference, bucket prefix, path-style flag).

## 4. Identity, Authentication, and Authorization

### FR-007 Local Authentication
The system shall support local authentication with username/email and password.

### FR-008 Password Management
The system shall support:
- password change;
- password reset;
- password reset expiration;
- forced password rotation for temporary credentials.

### FR-009 Login Attempt Protection
The system shall enforce configurable login attempt protection for **all users including admin**, including:
- maximum failed attempts;
- lockout duration or permanent lock option;
- admin unlock capability;
- audit logging of lockouts and unlocks.

### FR-010 MFA
The system shall support multi-factor authentication, with the ability to make MFA mandatory for:
- all administrators;
- selected roles;
- all users.

### FR-011 Sessions
The system shall support secure session management, including:
- access session expiration;
- refresh or renewal policies;
- logout from current session;
- logout from all sessions.

### FR-012 RBAC
The system shall support role-based access control with, at minimum, the following roles:
- superadmin;
- admin;
- workspace_owner;
- workspace_admin;
- agent_manager;
- operator;
- auditor;
- member;
- guest;
- service_account.

RBAC shall also govern agent-to-agent communication and tool access. Each agent role is recorded in an Identity Book of Record (IBOR), and role-based policies determine which agents may collaborate and which tools may be invoked.

### FR-013 Scoped Authorization
Authorization shall be enforceable at the following scopes:
- system/global scope;
- workspace scope;
- agent scope;
- workflow scope;
- execution scope;
- connector scope;
- credential scope.

### FR-014 Service Accounts
The system shall support service accounts for API-based automation and machine-to-machine access.

## 5. Registration, Subscription, Activation, and User Lifecycle

### FR-015 Self-Signup
The platform shall provide an admin-only configuration option to enable or disable self-signup.

### FR-016 Admin Approval
The platform shall provide an admin-only configuration option to require administrator approval before a newly registered user becomes active.

### FR-017 Subscription Feature Toggle
The platform shall provide an admin-only configuration option to enable or disable subscription-related features for users.

### FR-018 Separate Activation and Billing
The platform shall treat:
- account activation;
- billing/subscription eligibility;
- workspace membership;
as separate states.

### FR-019 Invite-Only Mode
The platform shall support invite-only registration mode.

### FR-020 Email Verification
The platform shall support optional or mandatory email verification before account activation.

### FR-021 User Statuses
User accounts shall support at least the following statuses:
- pending_verification;
- pending_approval;
- active;
- suspended;
- blocked;
- archived.

### FR-022 Admin User Lifecycle Actions
Authorized administrators shall be able to:
- approve users;
- reject users;
- suspend users;
- reactivate users;
- reset MFA;
- reset passwords;
- unlock accounts.

## 6. Workspaces, Membership, and Collaboration

### FR-023 Default Workspace
Each newly activated user shall receive a default workspace.

### FR-024 Multiple Workspaces
Users shall be able to create additional workspaces subject to configured limits.

### FR-025 Workspace Limit
Administrators shall be able to configure the maximum number of workspaces a user may create, where:
- `0` means unlimited.

### FR-026 Workspace Roles
Each workspace shall support its own membership and role model.

### FR-027 Workspace Invitations
Authorized users shall be able to invite other users into a workspace.

### FR-028 Shared vs Private Data
The system shall distinguish between:
- user-private settings and credentials;
- workspace-shared resources and configurations.

### FR-029 Workspace Lifecycle
The system shall support:
- workspace creation;
- workspace renaming;
- workspace archival;
- workspace restore within retention period;
- workspace deletion according to policy.

### FR-030 Workspace Isolation
Data, credentials, connectors, and execution history shall be isolated by workspace unless explicitly shared.

## 7. External Interfaces and Connectors

### FR-031 Connector Scope
Each workspace shall be able to configure its own external interfaces independently from other workspaces.

### FR-032 Supported Interfaces
The system shall provide interface support for:
- Telegram;
- WhatsApp;
- Discord;
- Slack;
- Signal;
- Email;
- Webhooks;
- REST API.

### FR-033 Multiple Connector Instances
A workspace shall be able to configure multiple instances of the same connector type, each with different credentials or routing settings.

### FR-034 Connector Credential Isolation
Connector credentials shall be isolated per workspace and shall not be exposed to unauthorized users or other workspaces.

### FR-035 Connector Enablement
Administrators shall be able to enable or disable connector types globally.

### FR-036 Workspace Connector Routing
A workspace shall be able to route messages, webhooks, or events to one or more selected agents or workflows.

### FR-037 Inbound and Outbound Email Separation
The system shall treat inbound email handling and outbound email delivery as separate configuration domains.

### FR-038 Email Delivery Options
Administrators shall be able to configure outbound email delivery using:
- Amazon SES API;
- Amazon SES SMTP;
- generic SMTP.

### FR-039 Email Intake Options
The system shall support inbound email intake using:
- IMAP polling;
- provider webhook or API, where supported.

## 8. Agent Package Import, Validation, and Catalog

### FR-040 Supported Agent Package Formats
The platform shall accept agent uploads in:
- `.tar.gz`;
- `.zip`.

### FR-041 Safe Package Validation
The platform shall validate uploaded packages and reject unsafe archives, including:
- path traversal entries;
- unsafe symlinks;
- unsupported file names;
- oversized extracted content;
- invalid directory structure.

### FR-042 OpenClaw-Style Agent Compatibility
The platform shall support agent packages containing an `agent/` directory with markdown-based agent files.

### FR-043 Required Agent Files
For a package to be publishable, the platform shall require:
- `agent/AGENTS.md`;
- `agent/SOUL.md`;
- `agent/USER.md`;
- a structured manifest file such as `agent.json` or `manifest.json`.

### FR-044 Optional Agent Files
The platform shall allow optional files including:
- `agent/BOOTSTRAP.md`;
- `agent/HEARTBEAT.md`;
- `agent/IDENTITY.md`;
- `agent/MEMORY.md`;
- `agent/TOOLS.md`;
- `agent/SOURCE.md`;
- optional memory, skills, or support directories.

### FR-045 Agent Manifest
The agent manifest shall support, at minimum:
- agent identifier;
- name;
- version;
- description;
- category;
- tags;
- author;
- compatibility metadata;
- required files;
- default model configuration;
- security policy references;
- forbidden operations;
- sandbox policy;
- package checksum or digest;
- declared capability maturity level;
- declared reasoning mode support;
- context engineering profile reference.

The agent manifest shall additionally include FQN-related fields: `namespace`, `local_name`, `fqn` (computed: namespace:local_name), `purpose` (mandatory natural-language definition), `approach` (optional natural-language strategy), `visibility_agents` (FQN patterns for discoverable agents), `visibility_tools` (FQN patterns for accessible tools), and `role_type` (executor | planner | orchestrator | observer | judge | enforcer).

### FR-046 Immutable Agent Revisions
Each successful upload shall create an immutable agent revision.

### FR-047 Agent Statuses
Agents and revisions shall support statuses such as:
- draft;
- validated;
- published;
- disabled;
- deprecated;
- archived.

### FR-048 Agent Catalog
The platform shall provide a catalog view for searching, filtering, tagging, and browsing agents and revisions.

### FR-049 Import Failure Reporting
When an agent upload fails validation, the system shall provide a detailed error report.

## 9. Agent Permissions, Policies, and Tooling

### FR-050 Structured Agent Policy
The platform shall support structured, machine-enforced agent policy separate from markdown instructions. Each policy element shall reference a category (tool restriction, host command policy, behavioral constraint, safety override, agent contract terms) and shall define enforcement semantics. Policies shall include both traditional operational policies and formalized agent contracts (task scope, quality thresholds, cost limits, escalation conditions). Markdown files such as TOOLS.md shall be treated as human-readable documentation only, never as the enforcement model (subsumes prior FR-054).

### FR-051 Declared Forbidden Operations
Agent metadata shall support a list of operations that the agent is never allowed to perform.

### FR-052 Host Command Policy
Agent metadata shall support a command policy including:
- allowed commands or patterns;
- denied commands or patterns;
- path restrictions;
- approval requirements for risky commands.

### FR-053 Tool Categories
Tools shall be categorized at least as:
- safe tools;
- external integration tools;
- sandbox tools;
- elevated host tools.

### FR-054 TOOLS.md Non-Authoritative
*[MERGED into FR-050. TOOLS.md is descriptive documentation only; enforcement is via structured policy.]*

### FR-055 Policy Overrides
The platform shall support policy composition across:
- global policy;
- deployment policy;
- workspace policy;
- agent policy;
- execution-time policy.

### FR-056 Policy Conflict Resolution
The system shall define and enforce deterministic policy precedence when multiple policies apply.

## 10. Agent Sharing Across Workspaces

### FR-057 Sharing Modes
An agent shall be shareable as:
- private;
- workspace-shared;
- shared with selected workspaces;
- published in an internal catalog.

### FR-058 Reference-Based Sharing
Sharing an agent across workspaces shall not require duplicating files by default.

### FR-059 Share Permissions
The owner of an agent or revision shall be able to control whether consuming workspaces may:
- use the agent;
- clone the revision;
- override model settings;
- override credentials;
- override policy;
- pin or auto-upgrade revisions.

## 11. Model Configuration and Credential Flows

### FR-060 Multiple Models per Agent
Each agent shall support:
- one primary model;
- one secondary model;
- optional additional ordered fallback models.

### FR-061 Supported Credential Modes
Model credentials shall support:
- API key;
- OAuth browser popup flow;
- OAuth device flow when relevant;
- stored secret reference;
- service account or machine identity where supported by provider.

### FR-062 UI Guidance for Model Login
The UI shall clearly indicate whether the user must:
- open an OAuth popup;
- complete a device-code flow;
- enter an API key;
- provide a secret reference.

### FR-063 Model Health and Failover
The system shall support health checking and automatic failover between model definitions.

### FR-064 Failover Triggers
Failover may be triggered by:
- authentication failure;
- timeout;
- rate limit;
- provider outage;
- quota or billing issue;
- explicit operator action.

### FR-065 Failover Audit
The system shall record the exact reason for each model failover event.

## 12. Workflow Engine

### FR-066 Workflow Definition Format
The workflow engine shall support workflow definitions in YAML.

### FR-067 Workflow Core Elements
A workflow definition shall support, at minimum:
- id;
- version;
- inputs;
- variables;
- steps;
- outputs;
- retries;
- timeouts;
- error handling;
- finalization/cleanup;
- triggers;
- approvals;
- concurrency control;
- reasoning mode hints;
- context budget constraints.

### FR-068 Default Sequential Behavior
By default, the output of one step shall become the input of the next step unless explicit mapping overrides are defined.

### FR-069 Advanced Data Mapping
The system shall support explicit input/output mapping between non-adjacent steps and between parallel branches.

### FR-070 Workflow Patterns
The workflow engine shall support:
- sequential flows;
- conditional branching;
- parallel execution;
- fan-out/fan-in;
- approval gates;
- manual intervention points;
- reflection/self-correction loops;
- debate rounds;
- tree-of-thought branching.

### FR-071 Workflow Validation
Before publication, the system shall validate workflow definitions for:
- schema correctness;
- broken references;
- invalid dependencies;
- cycles where unsupported;
- missing agents;
- missing connectors;
- incompatible policies;
- context budget feasibility.

### FR-072 Workflow Versioning
Each published workflow shall have an immutable version.

### FR-073 Workflow States
Workflow definitions shall support states such as:
- draft;
- published;
- disabled;
- deprecated;
- archived.

## 13. Workflow Triggers

### FR-074 Supported Trigger Types
A workflow shall be triggerable by:
- webhook;
- cron;
- agent orchestrator;
- manual UI action;
- REST API;
- event-bus subscription;
- workspace-goal event.

### FR-075 Webhook Trigger Security
Webhook-triggered workflows shall support signed verification, replay protection, and optional IP allowlisting.

### FR-076 Cron Scheduling
The system shall support cron-based workflow scheduling with timezone-aware configuration.

### FR-077 Trigger Scoping
Trigger ownership and permissions shall be enforceable per workspace and per workflow.

## 14. Deterministic Execution, Resume, Replay, and Rerun

### FR-078 Execution Journal
Each workflow execution shall persist an append-only execution journal including:
- workflow version;
- agent revision references;
- trigger source;
- execution inputs;
- per-step inputs;
- per-step outputs;
- retries;
- errors;
- timestamps;
- operator interventions;
- approval events;
- state transitions;
- reasoning traces and chain-of-thought summaries;
- context assembly snapshots at each step boundary;
- self-correction iterations and convergence metadata.

### FR-079 Resume
The system shall be able to resume a paused or interrupted execution from the last valid checkpoint.

### FR-080 Replay
The system shall be able to replay an execution using the persisted journal to reconstruct state without re-running already committed steps.

### FR-081 Rerun
The system shall support a full rerun from the beginning as a new execution.

### FR-082 Deterministic Error Recording
Errors shall be stored in a structured format with:
- machine-readable code;
- human-readable summary;
- step context;
- retry count;
- backend/runtime details;
- sandbox details where relevant;
- reasoning state at time of failure.

## 15. Retry, Timeout, Cancellation, and Compensation

### FR-083 Per-Step Retry Policy
Each step shall support retry configuration including:
- max attempts;
- retryable error classes;
- non-retryable error classes;
- backoff strategy;
- max retry duration.

### FR-084 Timeout Policy
Each step and each workflow shall support timeout policies.

### FR-085 Pause and Cancel
Authorized users shall be able to pause, resume, and cancel running executions.

### FR-086 Compensation and Cleanup
The workflow engine shall support cleanup or compensation actions for:
- failed steps;
- canceled executions;
- expired approvals;
- orphaned sandboxes;
- connector-side artifacts when applicable.

## 16. Safe Hot Change and Runtime Intervention

### FR-087 Execution Updates
The platform shall support safe in-flight execution updates through controlled interventions such as:
- signal;
- operator update;
- variable override;
- step skip with approval;
- controlled migration to a compatible workflow version;
- context injection or context pruning mid-execution.

### FR-088 Compatibility Validation
The system shall validate compatibility before applying a change to a running execution.

### FR-089 Manual Intervention Audit
Every manual intervention shall be fully audited.

## 17. Default Orchestrator Agent

### FR-090 Built-In Orchestrator
The system shall include a built-in default agent orchestrator.

### FR-091 Orchestrator Capabilities
The orchestrator shall be able to:
- call workflows;
- delegate to agents;
- request approvals;
- coordinate sub-agents;
- route execution based on policy and context;
- invoke reflection and self-correction loops;
- manage reasoning budget allocation across delegated tasks.

### FR-092 Restricted Orchestrator Policy
The orchestrator shall run under a restricted default policy and shall not have elevated host access by default.

## 18. Agent Runtime and Lifecycle Management

### FR-093 Isolated Agent Runtime
Agents shall execute in isolated runtime environments separate from the control plane.

Agent runtime pods shall support warm pool dispatch. When a warm pod matching the agent type is available, it shall be used instead of cold-starting a new pod, reducing launch latency to <2 seconds. Secrets shall be injected at pod launch by the Runtime Controller from the vault, never through the agent's LLM context.

### FR-094 Runtime Control Interface
Each agent runtime shall expose a control interface for:
- health;
- readiness;
- execution requests;
- status updates;
- logs/events streaming;
- shutdown;
- capability maturity self-report.

### FR-095 Runtime States
The platform shall track runtime states including:
- requested;
- scheduled;
- image_pulling;
- starting;
- ready;
- busy;
- paused;
- stopping;
- stopped;
- succeeded;
- failed;
- timed_out;
- canceled;
- degraded.

### FR-096 Runtime Startup Contract
After startup, the runtime shall receive an execution contract containing:
- agent revision identifier;
- package digest;
- workspace context;
- tool policy;
- sandbox policy;
- model binding;
- secret references;
- correlation identifiers;
- context engineering profile;
- reasoning budget envelope;
- self-correction policy.

### FR-097 Read-Only Package Mount
Agent packages shall be mounted or injected as read-only artifacts at runtime.

### FR-098 Event Streaming
The runtime shall stream operational events, progress information, and relevant execution details back to the workflow engine.

## 19. Sandboxed Code Execution

### FR-099 Sandbox-Only Code Execution
Whenever an agent executes code, that code shall execute in a sandbox rather than directly in the agent runtime.

### FR-100 Preconfigured Sandboxes
The platform shall include preconfigured sandbox profiles for at least:
- Python;
- JavaScript/TypeScript;
- Go.

### FR-101 Sandbox Policies
Sandbox policies shall support:
- CPU limit;
- memory limit;
- disk limit;
- timeout;
- network on/off;
- egress allowlist;
- mounted data policy;
- persistence policy.

### FR-102 Sandbox Manager
Sandbox creation shall be performed by a managed sandbox service or controller rather than by giving agents direct access to the infrastructure backend.

### FR-103 Sandbox Telemetry
Sandbox runs shall record:
- start and end time;
- exit code;
- stdout;
- stderr;
- produced artifacts;
- resource usage where available.

### FR-104 Sandbox Cleanup
The platform shall automatically clean up expired or orphaned sandboxes.

## 20. Elevated Host Operations

### FR-105 Elevated Host Access Disabled by Default
In shared multi-tenant mode, elevated host operations shall be disabled by default.

### FR-106 Trusted Mode Exception
Elevated host operations may be enabled only in trusted mode or under a global administrative exception policy.

### FR-107 Approval for Risky Operations
The platform shall support approval policies for elevated operations.

### FR-108 Full Audit of Elevated Operations
All elevated host operations shall be fully audited, including initiator, command, target, result, and approval trace.

## 21. Infrastructure Backend Abstraction

### FR-109 Supported Execution Backends
The platform shall support execution using:
- Docker;
- Docker Swarm;
- Kubernetes;
- Incus.

### FR-110 Backend Abstraction
The control plane shall interact with execution backends through a uniform abstraction capable of:
- launch;
- inspect;
- stream logs;
- terminate;
- collect artifacts;
- reconcile state.

### FR-111 Backend Selection
At installation time, the operator shall choose the execution backend for:
- agent runtimes;
- sandbox runtimes.

The operator shall also choose the object storage backend:
- external S3-compatible provider (endpoint URL, credentials, region); or
- self-hosted MinIO (development and lab environments only).

### FR-112 V1 Backend Constraint
The baseline product may require the same backend family for both agent runtimes and sandboxes in version 1.

## 22. Limits, Quotas, and Governance

### FR-113 Agent Limit per User
Administrators shall be able to configure the maximum number of agents a user may create, where:
- `0` means unlimited.

### FR-114 Execution Limits
The platform shall support configurable limits for:
- concurrent workflow executions;
- concurrent agents;
- concurrent sandboxes;
- API request rate;
- connector throughput.

### FR-115 Token and Cost Limits
The platform shall support configurable token and estimated cost limits at:
- system level;
- workspace level;
- user level;
- workflow level;
- agent level.

### FR-116 Storage Limits
The platform shall support configurable storage quotas for:
- uploaded packages;
- logs;
- execution artifacts;
- sandbox artifacts.
Storage quotas shall be enforced against S3-compatible object storage usage. The platform shall track per-workspace bucket consumption and alert or throttle when thresholds are reached.

### FR-117 Enforcement and Reporting
Quota enforcement shall happen at runtime and shall be visible in dashboards and audit logs.

## 23. User Interface and Operator Experience

### FR-118 Web UI
The platform shall provide a web UI for:
- administration;
- workspace management;
- agent catalog;
- workflow design and monitoring;
- connector management;
- credential setup;
- execution investigation.

### FR-119 Role-Aware Visibility
The UI shall show only the actions and settings permitted for the current role.

### FR-120 Live Execution View
The UI shall provide a live execution view including:
- current workflow graph state;
- step timeline;
- logs/events stream;
- approvals pending;
- runtime state;
- sandbox state;
- reasoning trace visualization;
- self-correction iteration progress;
- context quality indicators.

### FR-121 Token and Cost Analytics
The UI shall provide analytics for token consumption and estimated cost by:
- provider;
- model;
- workspace;
- user;
- workflow;
- agent;
- time period.

### FR-122 Model Credential UX
The UI shall clearly support both OAuth-based model login and API-key-based model configuration.

### FR-123 Admin Settings UI
The UI shall allow administrators to manage:
- signup policy;
- approval policy;
- subscription feature toggles;
- quotas and limits;
- connector availability;
- email configuration;
- security controls.

## 24. API, Webhooks, and Automation

### FR-124 Public API
The platform shall expose a versioned REST API for management and execution operations.

### FR-125 API Authentication
The API shall support secure authentication using:
- user sessions;
- API tokens;
- service accounts.

### FR-126 API Idempotency
The API shall support idempotency for relevant create/trigger operations.

### FR-127 Webhook Security
Inbound webhooks shall support:
- signature validation;
- replay prevention;
- timestamp validation;
- secret rotation.

### FR-128 Event Subscription
The platform shall support outbound event subscriptions or callback notifications for selected execution events.

## 25. Audit, Compliance, Retention, and Recovery

### FR-129 Audit Logging
The system shall audit, at minimum:
- authentication events;
- authorization changes;
- workspace changes;
- connector changes;
- agent uploads and sharing changes;
- workflow publication and updates;
- execution interventions;
- elevated operations;
- secret access events where meaningful;
- self-correction loop iterations;
- reasoning budget consumption events.

### FR-130 Retention Policies
The system shall support configurable retention for:
- audit logs;
- execution logs;
- prompts and outputs;
- artifacts;
- connector payloads;
- reasoning traces;
- context assembly snapshots.

### FR-131 Redaction
The platform shall support redaction or masking of sensitive information in logs and UI views.

### FR-132 Backup and Restore
The platform shall support backup and restore procedures for configuration, metadata, and execution history.

### FR-133 Forensic Export
Authorized users shall be able to export a complete forensic package for a workflow execution, including logs, state transitions, step inputs/outputs, and referenced artifacts subject to permissions.

## 26. Reporting, Search, and Discovery

### FR-134 Search
The platform shall support search across:
- users;
- workspaces;
- agents;
- workflows;
- executions;
- audit logs.

### FR-135 Filters and Saved Views
The UI shall support filtering, sorting, and saving of operational views.

### FR-136 Exportable Reports
Administrators and auditors shall be able to export reports for:
- usage;
- token consumption;
- cost estimation;
- failed executions;
- security events.

## 27. Data Lifecycle and Deletion

### FR-137 Soft Delete
The platform shall support soft delete where recovery is required by policy.

### FR-138 Hard Delete and Anonymization
The platform shall support permanent delete or anonymization flows according to configured retention and compliance rules.

### FR-139 Dependency-Aware Deletion
Deletion operations shall validate dependencies and either block deletion or perform safe cascading according to policy.

## 28. Compatibility and Upgrade Safety

### FR-140 Agent and Workflow Pinning
Workflow versions shall reference specific agent revisions rather than mutable latest references.

### FR-141 Backward Compatibility Rules
The platform shall define backward compatibility rules for:
- agent manifest versions;
- workflow schema versions;
- runtime control API versions.

### FR-142 Upgrade Safety
Platform upgrades shall preserve stored agents, workflow definitions, execution journals, and audit history.

## 29. Minimum Functional Acceptance Baseline

The product shall not be considered functionally complete unless all of the following are simultaneously true:

1. a fresh installation can create and display a temporary admin credential in the installer CLI;
2. a user can be registered, approved, activated, and assigned a default workspace;
3. a workspace can configure at least one connector and one model credential;
4. an OpenClaw-style agent package can be uploaded, validated, versioned, and assigned to a workspace;
5. a YAML workflow can be published and triggered by at least one trigger type;
6. the workflow execution can persist deterministic state and survive interruption;
7. an agent can execute through an isolated runtime;
8. code execution can occur only through an isolated sandbox;
9. usage metrics and token accounting are visible in the UI;
10. audit history is available for security and operational actions.

## 30. Ruflo-Informed Functional Update Notes

This revision extends the original functional specification after reviewing Ruflo's current architecture and functionality. The update **adapts** Ruflo ideas to a secure, multi-tenant control-plane/data-plane product rather than copying Ruflo verbatim.

## 31. Developer and Operator Entry Points

### FR-143 Operator CLI
The platform shall provide an operator and developer CLI for installation, diagnostics, administration, workflow operations, runtime inspection, and automation scripting.

### FR-144 MCP-Compatible Access
The platform shall implement full MCP (Model Context Protocol) support in both server and client modes. In server mode, platform tools, resources, and prompts are exposed to external MCP clients via the standard MCP discovery and invocation protocol. In client mode, agents can connect to external MCP servers to discover and use tools, subject to tool gateway policy enforcement. See FR-392 through FR-396 for detailed MCP requirements.

### FR-145 Headless and Non-Interactive Mode
The platform shall support headless and non-interactive execution modes suitable for CI/CD, scheduled automation, remote shells, and machine-triggered workflows.

### FR-146 Health Check and Diagnostics
The platform shall provide a diagnostic capability, available through the UI, CLI, or API, for validating:
- database connectivity;
- object or artifact storage access;
- execution backend health;
- sandbox backend health;
- model provider connectivity;
- connector health;
- policy compilation status;
- runtime event streaming health.

## 32. Hook System and Background Automation

### FR-147 Lifecycle Hook Framework
The platform shall support configurable lifecycle hooks around relevant events including:
- session start and end;
- workflow start and completion;
- step start and completion;
- runtime start and termination;
- sandbox start and termination;
- model invocation;
- memory write;
- connector receipt and delivery;
- self-correction iteration;
- reasoning budget threshold breach.

### FR-148 Hook Conditions and Priorities
Hooks shall support:
- conditional execution;
- priority ordering;
- timeout handling;
- failure policy;
- auditability of hook execution.

### FR-149 Background Workers
The platform shall support background workers for operations such as:
- usage aggregation;
- retry handling;
- sandbox cleanup;
- connector delivery retry;
- memory consolidation;
- diagnostics;
- drift detection;
- alert generation;
- context quality scoring;
- fleet health aggregation.

## 33. Swarm Coordination and Anti-Drift Collaboration

### FR-150 Swarm Topologies
The orchestrator shall support coordinated multi-agent execution using one or more swarm topologies including:
- hierarchical;
- mesh;
- ring;
- star;
- hybrid.

### FR-151 Consensus Strategies
The platform shall support configurable coordination or consensus strategies for multi-agent decisions, including:
- majority;
- weighted majority;
- quorum-based or Byzantine-tolerant style modes for critical decisions;
- Elo-tournament ranking for hypothesis or answer selection.

### FR-152 Anti-Drift Controls
The orchestrator shall support anti-drift controls for long-running collaborative execution, including:
- role specialization;
- checkpoints;
- verification gates;
- bounded task cycles;
- explicit re-alignment prompts or policy refresh;
- escalation to operator review when drift risk exceeds threshold;
- semantic similarity monitoring of agent outputs against declared purpose.

### FR-153 Shared Collaboration Channels
Agent teams shall be able to use controlled collaboration primitives such as:
- shared task lists;
- mailbox or message channels;
- shared memory namespaces;
- claim or assignment tracking;
- completion notifications;
- broadcast and multicast message delivery.

### FR-154 Dynamic Agent Selection
The system shall be able to suggest or automatically select agent mixes, swarm templates, or orchestration patterns based on:
- task complexity;
- workflow intent;
- policy;
- configured cost or latency objectives;
- required capabilities;
- agent capability maturity level;
- historical performance data.

### FR-155 Stream Chaining
The platform shall support streaming the output of one agent or workflow step to downstream agents or steps while also persisting the committed step output deterministically.

## 34. Memory, Learning, and Knowledge Reuse

### FR-156 Trajectory Capture
The platform shall support capturing execution trajectories for selected runs, tools, or connectors, including:
- sequence of actions;
- inputs and outputs;
- snapshots or references where applicable;
- success or failure verdict;
- reusable metadata;
- reasoning chain summaries.

### FR-157 Pattern Store and Retrieval
The platform shall support storing reusable patterns derived from successful executions and retrieving them for similar future tasks.

### FR-158 Scoped Memory Model
The platform shall support scoped memory domains including:
- per-agent memory;
- per-workspace memory;
- shared orchestrator memory;
- controlled cross-agent transfer rules.

### FR-159 Knowledge Graph Views
The platform should be able to derive graph-oriented views from stored memory or execution relationships to help discover related agents, patterns, workflows, failures, or reusable artifacts.

### FR-160 Rule and Pattern Promotion Workflow
The platform shall support promoting successful local or workspace-level experiments, templates, or patterns into broader shared use through an explicit approval and audit workflow.

## 35. Governance, Trust, and Safety Control Plane

### FR-161 Compiled Governance Bundles
The platform shall be able to compile human-authored governance inputs, such as agent markdown instructions and structured policies, into machine-usable execution bundles containing:
- always-loaded invariants;
- task-scoped rule shards;
- validation manifest metadata.

### FR-162 Enforcement Gates
The platform shall support runtime enforcement gates capable of blocking or constraining actions such as:
- destructive commands;
- secrets exposure;
- unauthorized tools;
- oversized or risky changes;
- unauthorized memory writes.

### FR-163 Trust and Privilege Tiers
The platform shall support trust or reliability tiers for agents, tools, or runtimes, allowing policy to adjust approval requirements, throughput, or permissions based on observed behavior.

### FR-164 Adversarial Defense
The platform shall provide safeguards against adversarial agent behavior and prompt-layer attacks including:
- prompt injection detection;
- memory poisoning detection;
- suspicious privilege escalation detection;
- exfiltration pattern detection;
- inter-agent collusion alerts;
- jailbreak resistance controls.

### FR-165 Critical Write Quorum
The platform shall support quorum or multi-party confirmation for selected critical writes such as shared memory updates, governance changes, or high-impact execution overrides.

### FR-166 Integrity and Proof Chain
The platform shall preserve an integrity-oriented chain of execution, policy, and approval events suitable for replay, forensics, and audit verification.

## 36. Extensibility, Skills, and Advanced Tooling

### FR-167 Unified Plugin Framework
The platform shall support a plugin or extension framework for:
- tools;
- workers;
- model providers;
- connectors;
- policies;
- analytics or reporting modules;
- reusable workflow or agent templates;
- context engineering strategies;
- reasoning technique plugins.

### FR-168 Internal Extension Catalog
The platform shall provide an internal catalog or registry for approved extensions, templates, skills, or reusable orchestration assets.

### FR-169 Browser Automation Capability
The platform should support browser automation as a managed capability, including:
- navigation;
- form filling;
- DOM or accessibility-tree snapshots;
- screenshot capture;
- security scanning of browser targets;
- reusable workflow templates for login, OAuth, scraping, and validation.

### FR-170 Cost-Aware Model Routing
Beyond simple model failover, the system shall support routing requests to models based on:
- capability fit;
- latency;
- cost;
- rate-limit health;
- policy;
- availability;
- task complexity classification;
- reasoning depth required.

### FR-171 Deterministic Fast Paths
The platform should support deterministic, non-LLM fast paths for eligible low-risk transformations or policy checks in order to reduce latency and cost.

### FR-172 External Agent Environment Adapters
The platform should support adapters or integration patterns for external agent environments, such as developer CLIs, IDE assistants, or remote orchestration tools, through API, CLI, or MCP-style protocols.

### FR-173 Reusable Skills and Templates
The platform shall support reusable, versioned skills or templates for:
- workflow scaffolding;
- swarm topologies;
- connector setups;
- sandbox profiles;
- policy bundles;
- diagnostic routines;
- context engineering profiles;
- reasoning strategy configurations.

## 37. Additional Functional Acceptance Criteria for the Ruflo-Informed Profile

In addition to the original minimum functional acceptance baseline, the Ruflo-informed profile shall not be considered complete unless all of the following are also true:

1. a hook can be configured to run on at least one workflow or runtime lifecycle event and its outcome is visible to operators;
2. a multi-agent execution can run with an explicitly selected topology and anti-drift control settings;
3. a reusable pattern or trajectory can be captured from one successful execution and reused in a later one;
4. a compiled governance bundle and enforcement gates can block at least one forbidden action before execution;
5. the platform can route at least one execution using cost-aware model selection rather than simple primary/secondary failover alone;
6. at least one approved extension, skill, or template can be installed or activated from an internal catalog;
7. a headless diagnostic command or API can validate core control-plane and execution-plane dependencies.

## 38. Agentic Design Patterns-Driven Revisions and Corrections

This revision extends the current functional specification using the design guidance from *Agentic Design Patterns*. Where the requirements in this section are more specific than earlier wording, **the later wording in this section takes precedence**.

## 39. Prompt, Context, and Output Engineering

### FR-174 Prompt Asset Management
The platform shall treat prompts, task briefs, reviewer instructions, router prompts, safety prompts, and connector-specific prompt templates as versioned assets rather than as ad hoc strings embedded only in code.

### FR-175 Prompt Scope and Precedence
Prompt assets shall support composition and precedence across:
- global scope;
- workspace scope;
- agent scope;
- workflow scope;
- execution scope.

### FR-176 Structured Task Briefs
The platform shall support a structured task brief model for agent and workflow execution that can include:
- objective;
- constraints;
- acceptance criteria;
- preferred output format;
- priority;
- time budget;
- cost budget;
- safety class;
- required context sources;
- reasoning mode hint;
- expected capability maturity level.

### FR-177 Context Assembly Pipeline
The platform shall provide a context assembly capability that can construct runtime context from:
- system instructions;
- workflow state;
- short-term interaction history;
- long-term memory retrievals;
- tool outputs;
- connector payloads;
- user or workspace metadata;
- environment or runtime state;
- prior reasoning traces where relevant.

### FR-178 Context Privacy and Eligibility Controls
The system shall enforce policy over which implicit context may be included in a prompt or runtime context, including user identity, prior interactions, recent purchases, organizational role, and environment state.

### FR-179 Context Quality Feedback Loops
The platform shall support improving context quality over time through feedback loops, including evaluation-driven context refinement and prompt/context optimization workflows.

### FR-180 Structured Output Contracts
Agents, steps, and workflows shall be able to declare structured output contracts, including support for formats such as:
- JSON;
- YAML;
- XML;
- CSV;
- Markdown tables;
- typed object or schema-backed responses.

### FR-181 Output Validation and Repair
When a step or agent declares a structured output contract, the system shall validate the produced output and may run a bounded repair or refinement loop before committing the result.

### FR-182 Prompt and Output Testing
The platform shall support testing prompt assets and output contracts against reference cases before promotion to production use.

### FR-183 Multimodal Prompting and Context
The platform shall support multimodal task execution where the selected models and connectors allow it, including text combined with one or more of:
- file attachments;
- images;
- extracted tables;
- document snippets;
- optional audio or video metadata.

## 40. Advanced Orchestration Patterns

### FR-184 Routing Strategy Modes
The platform shall support multiple routing strategies for query, step, or agent selection, including:
- rule-based routing;
- classifier-based routing;
- embedding or semantic routing;
- LLM-based routing.

### FR-185 Route Explainability
For routed decisions that affect execution flow, the system shall persist the selected route, the decision basis, and the decision input context.

### FR-186 Parallel Branch Policies
Parallel execution shall support explicit policies for:
- fan-out concurrency;
- branch-level timeout;
- branch-level retry;
- partial failure handling;
- deterministic aggregation or merge strategy.

### FR-187 Reflection as a First-Class Pattern
The platform shall support reflection or self-correction as a first-class orchestration pattern, allowing an output to be reviewed and refined before finalization.

### FR-188 Producer-Critic and Reviewer Modes
The system shall support review patterns where one agent or step produces an output and another agent or step critiques it against policy, quality, or acceptance criteria.

### FR-189 Debate and Consensus Patterns
The orchestration layer shall support collaborative reasoning patterns in which multiple agents produce, challenge, compare, or score alternative answers before a final answer is selected. Supported debate modes shall include: Chain of Debates (CoD) with structured rounds of position-critique-rebuttal-synthesis (see FR-404), simple majority voting, weighted voting based on agent expertise scores, and arbitrated consensus where a judge agent makes the final determination. All debate transcripts shall be persisted as reasoning artifacts linked to the execution journal.

### FR-190 Agent-as-a-Tool Invocation
The platform shall support invoking an agent as a tool from another agent or workflow step, with explicit contracts for input, output, permissions, and audit.

### FR-191 ReAct-Style Deliberation Loops
The system shall support bounded reasoning-action-observation loops in which an agent can alternate between planning, acting with tools, and incorporating observations.

### FR-192 Plan Generation and Replanning
Where agentic planning is enabled, the system shall allow an orchestrator or agent to generate a plan, revise it in response to new observations, and expose that plan for audit or review.

### FR-193 Reasoning Budget Controls
The platform shall support configurable reasoning or deliberation budgets at least at the model call, step, and execution level.

## 41. Memory, Retrieval, and Knowledge Quality

### FR-194 Short-Term and Long-Term Memory Separation
The platform shall distinguish between short-term execution or conversation memory and long-term persistent memory.

### FR-195 Memory Types
The platform shall support separate memory categories for:
- semantic memory;
- episodic memory;
- procedural memory.

### FR-196 Memory Freshness and Authority
The platform shall support memory freshness and source-authority policies so that newer or more authoritative knowledge can supersede stale or low-authority information.

### FR-197 Contradiction Detection in Retrieval
The system shall detect and expose contradictions across retrieved sources when materially relevant to a generated answer, execution, or recommendation.

### FR-198 Hybrid Retrieval Modes
The retrieval subsystem shall support one or more of the following retrieval strategies depending on deployment profile:
- keyword retrieval;
- vector retrieval;
- graph-based retrieval;
- hybrid retrieval.

### FR-199 Agentic RAG
The platform shall support an agentic retrieval mode in which a reasoning component can:
- validate retrieved sources against multiple corroborating sources;
- reconcile conflicting evidence by reasoning about source authority and freshness;
- request additional retrieval passes when initial results are insufficient;
- fill knowledge gaps through approved tools or connectors;
- perform multi-step queries where each retrieval informs the next;
- produce attributable answers with citation provenance linking each claim to its source.
Agentic RAG is a Level 2+ agent capability that requires active context engineering (FR-417).

### FR-200 Retrieval Chunking Controls
The system shall support configuration of retrieval chunking, overlap, and source-citation behavior for document-backed knowledge stores.

### FR-201 Memory Governance
Persistent memory creation, update, promotion, and deletion shall be subject to policy, audit, and retention controls.

## 42. Safety, Guardrails, and Human Governance

### FR-202 Layered Guardrail Architecture
The platform shall support layered guardrails that may be applied at:
- input ingestion;
- prompt assembly;
- model output generation;
- tool invocation;
- memory writes;
- external action commit.

### FR-203 Input Validation and Sanitization
The system shall support validation and sanitization of inbound text, files, and connector payloads to reduce malformed input, unsafe content, and prompt injection risk.

### FR-204 Output Validation and Moderation
The platform shall support output validation and moderation before sensitive results are displayed, persisted, or used to trigger external actions.

### FR-205 Behavioral Constraints
The platform shall allow policy-driven behavioral constraints that explicitly limit what an agent is allowed to answer, suggest, or do in a given domain or risk context.

### FR-206 Safety Callbacks and Interceptors
The platform shall support safety callbacks or interceptors around model calls, tool calls, memory writes, and external commits.

### FR-207 Safety Checkpoint and Rollback
The system shall support rolling back or reverting to the last known safe checkpoint when a policy violation, unsafe action, or critical validation failure is detected.

### FR-208 Low-Cost Safety Screening
The platform shall implement a SafetyPreScreener as the mandatory first stage of the guardrail pipeline. This lightweight, fast classifier (<10ms latency target) screens all inputs for obvious policy violations (jailbreak patterns, prompt injection signatures, prohibited content, malformed input) before the full LLM-based guardrail runs. Clear violations are blocked immediately; ambiguous cases proceed to the full pipeline. The pre-screener also runs on tool outputs before they are returned to the LLM context. Pre-screener rules shall be versioned and hot-updatable without platform redeployment.

### FR-209 Human-on-the-Loop Mode
The platform shall support a human-on-the-loop operating mode in which agents can continue long-running tasks with limited supervision and only escalate when exceptions, risk thresholds, or approval requirements are met.

### FR-210 Final Human Quality Gate
Outputs that are irreversible, destructive, compliance-sensitive, externally published, or otherwise high impact shall support mandatory human approval before final commit.

### FR-211 Outputs as Proposals Until Commit
The platform shall treat high-impact agent outputs as proposals until they are accepted by policy, workflow control logic, or an authorized human approver.

## 43. Evaluation, Monitoring, and Continuous Improvement

### FR-212 Quality Metrics and KPIs
The platform shall support evaluation metrics and KPIs for agents, workflows, prompts, and runtimes, including at minimum:
- success rate;
- latency;
- cost;
- accuracy or correctness indicators;
- completeness indicators;
- compliance indicators;
- anomaly rate;
- self-correction convergence rate;
- reasoning depth utilization.

### FR-213 Offline Evaluation Suites
The platform shall support offline evaluation suites using golden cases, benchmark scenarios, regression sets, or policy challenge sets.

### FR-214 Online Monitoring and Drift Detection
The platform shall support continuous online monitoring for:
- performance drift;
- behavior drift;
- anomaly detection;
- policy violation frequency;
- SLA or deadline breaches;
- semantic drift from declared purpose.

### FR-215 A/B Testing and Canary Evaluation
The system shall support comparative evaluation of prompts, models, workflows, or orchestration patterns using A/B or canary-style experiments.

### FR-216 Human and Automated Reviewers
The platform shall support both automated evaluators and human reviewers for grading outputs, executions, or policy adherence.

### FR-217 AI Contracts
The platform shall support an execution contract or AI contract construct for selected workflows or agents, defining:
- objective;
- constraints;
- allowed actions;
- prohibited actions;
- success metrics;
- escalation conditions;
- review obligations.

### FR-218 Evaluation Artifacts
The system shall preserve evaluation artifacts such as judgments, scores, traces, and reviewer comments as auditable resources.

## 44. Prioritization and Task Governance

### FR-219 Prioritization Engine
The platform shall support a prioritization capability for selecting among competing actions, steps, workflows, or alerts.

### FR-220 Prioritization Criteria
Prioritization shall support criteria such as:
- urgency;
- importance;
- dependency order;
- severity;
- risk;
- resource cost;
- due date or deadline;
- reasoning budget remaining;
- strategic alignment score.

### FR-221 Dynamic Re-Prioritization
The system shall support explicit re-prioritization triggers that recalculate task priority when conditions change. Triggers shall include: new high-urgency step arrival in the same execution, SLA deadline approach (configurable threshold, e.g., 80% of time budget consumed), resource constraint changes (fleet member failure, model provider throttling), budget threshold breach (80%/90% of reasoning budget consumed), and external events (attention requests, goal updates). When a trigger fires, all queued (not yet dispatched) steps shall be re-evaluated using the priority algorithm. Re-prioritization events shall be emitted to Kafka for observability.

### FR-222 Priority Scopes
Prioritization shall be supported at multiple scopes, including:
- strategic goals;
- workflow queue selection;
- step scheduling;
- connector event handling;
- alert handling.

### FR-223 SLA- and Deadline-Aware Escalation
The platform shall support escalation or rerouting based on impending or breached deadlines, SLA targets, or severity thresholds.

## 45. Exploration, Discovery, and Experimentation

### FR-224 Exploration and Discovery Workflows
The platform shall support exploratory workflows intended to discover novel information, strategies, hypotheses, or opportunities rather than only executing predefined deterministic flows.

### FR-225 Hypothesis and Experiment Cycles
The system shall support workflows in which agents can:
- generate hypotheses;
- critique hypotheses;
- refine hypotheses;
- design experiments;
- execute approved experiments;
- evaluate outcomes;
- rank hypotheses using tournament-style scoring.

### FR-226 Discovery Artifact Capture
Exploration and discovery workflows shall capture research notes, hypotheses, experiment metadata, results, and supporting evidence as first-class artifacts.

### FR-227 Discovery Governance
Exploration and discovery modes shall support stricter guardrails, sandbox restrictions, and optional mandatory human review before promotion or operational use of discovered results.

### FR-228 Discovery-to-Pattern Promotion
Validated insights or successful discovery trajectories shall be promotable into reusable patterns, templates, or memory assets through an approval workflow.

## 46. A2A and MCP Interoperability Refinements

### FR-229 Agent Cards
A remotely addressable agent shall be able to expose a machine-readable card describing identity, endpoint, supported capabilities, authentication expectations, and skills.

### FR-230 Discovery Modes for Remote Agents
The platform shall support discovery of remote agents through one or more of:
- well-known endpoint discovery;
- curated registry discovery;
- direct configuration.

### FR-231 Multiple Remote Interaction Modes
Remote agent interactions shall support one or more of:
- synchronous request/response;
- asynchronous polling;
- streaming updates;
- push notification or webhook callbacks.

### FR-232 Multi-Turn Remote Task Context
The platform shall support preserving multi-turn remote interaction context for A2A-style tasks, including context identifiers, task identifiers, and artifact references.

### FR-233 MCP and A2A Coexistence
The platform shall support architectures in which MCP is used for tool and resource access while A2A is used for agent-to-agent coordination.

## 47. Additional Functional Acceptance Criteria

In addition to the existing functional acceptance criteria, this revision shall not be considered complete unless all of the following are also true:

1. at least one agent or workflow can use a versioned prompt asset and a structured task brief;
2. at least one execution can assemble context from memory, tool output, and workflow state under policy control;
3. at least one step can declare a structured output contract and pass schema validation or repair before commit;
4. at least one orchestration path can use a review or critic step before a final answer is committed;
5. layered guardrails can block or sanitize at least one unsafe input or output;
6. at least one evaluation suite can grade a workflow or agent against predefined criteria;
7. at least one live execution can be re-prioritized based on urgency, risk, or deadline;
8. at least one exploratory workflow can generate a hypothesis, run an approved experiment, and persist the result as an auditable artifact;
9. at least one remote agent can be described through an agent card and invoked through a supported remote interaction mode.

## 48. Agent Marketplace and Discovery

### FR-234 Agent Marketplace as a First-Class Product Surface
The platform shall provide a first-class **agent marketplace** for discovering, evaluating, selecting, and invoking agents and shared agents across workspaces.

### FR-235 Two-Sided Marketplace Behavior
The marketplace shall support both:
- consumer-facing discovery and invocation of agents; and
- creator-facing publication and lifecycle visibility of agent revisions.

### FR-236 Natural Language Agent Search
The marketplace shall support natural-language search over structured agent metadata, allowing users to search for agents using task-oriented phrases rather than only exact names, tags, or categories.

### FR-237 Hierarchical Agent Navigation
The marketplace shall support hierarchical browsing of agents through categories, domains, namespaces, business units, or other curated taxonomies.

### FR-238 Filtered Discovery
The marketplace shall support filtering agents by one or more of:
- workspace visibility;
- tags;
- namespace;
- capabilities;
- supported connectors;
- trust or certification status;
- policy labels;
- lifecycle state;
- owner or publisher;
- deployment readiness;
- capability maturity level;
- reasoning mode support.

### FR-239 Agent Comparison Views
Users shall be able to compare multiple agents side by side using metadata such as:
- purpose;
- description;
- inputs and outputs;
- supported tools or connectors;
- policy attachments;
- trust signals;
- version or revision information;
- performance metrics and evaluation scores.

### FR-240 Trust Signals in Listings and Profiles
Marketplace listings and profile pages shall expose trust signals such as:
- publisher identity;
- lifecycle state;
- certification status;
- policy attachments;
- operational success indicators;
- ratings or feedback summaries where enabled;
- self-correction effectiveness score.

### FR-241 Restricted Agent Access Workflow
When an agent is restricted by policy, scope, or trust level, the platform shall support an explicit authorization or access-request workflow instead of silently hiding all availability semantics.

### FR-242 Version- and Revision-Aware Agent Selection
The marketplace shall allow users or administrators to select:
- the default published revision;
- a pinned revision where permitted;
- a certified or policy-constrained revision where required.

## 49. Registry and Metadata System of Record

### FR-243 Registry as the Shared Source of Truth
The platform shall provide a **registry** that acts as the shared source of truth for managed metadata needed by humans, agents, and operational services.

### FR-244 Core Registry Entities
The registry shall support, at minimum, records for:
- agents;
- agent revisions;
- conversations;
- interactions;
- workspaces;
- workspace goals;
- policies;
- certifications;
- users or externally linked user references.

### FR-245 Rich Agent Profile Metadata
Each registry-backed agent profile shall support structured metadata including, at minimum:
- name;
- namespace;
- purpose;
- description;
- owner or publisher;
- capabilities;
- supported interaction modes;
- policy references;
- certification references;
- lifecycle state;
- visibility rules;
- endpoint or invocation descriptors;
- declared capability maturity level;
- supported reasoning modes;
- context engineering profile.

Agent profile metadata shall include FQN (namespace:local_name), purpose (natural-language), approach (natural-language), role_type, visibility configuration (agent/tool FQN patterns), and maturity level. Purpose and approach fields shall be primary search fields for marketplace discovery.

### FR-246 Policy Attachment at Registration or Publication Time
Policies shall be attachable to agents during registration, publication, revision approval, or certification workflows.

### FR-247 Certification Attachment and Status
Certifications shall be attachable to agent revisions with explicit status values such as:
- pending;
- active;
- expired;
- revoked;
- superseded.

### FR-248 User Identity Attribution in Registry Records
Registry records for actions or changes shall retain identity attribution sufficient to determine:
- who created a resource;
- who modified it;
- who approved it;
- who certified it;
- when each action occurred.

### FR-249 Conversation Records
The registry or an equivalent source-of-truth layer shall persist conversations as durable entities rather than treating them as transient chat UI constructs only.

### FR-250 Interaction Records
The registry or an equivalent source-of-truth layer shall persist interactions as first-class, bounded task records within or alongside conversations.

### FR-251 Workspace and Subscription Metadata
The registry shall support metadata describing:
- workspace execution settings;
- subscribed agents or fleets where applicable;
- workspace-level goals;
- workspace-scoped connectors;
- workspace-scoped policies.

### FR-252 Capability, Endpoint, and Visibility Metadata
The registry shall retain machine-readable metadata for capability discovery, invocation endpoints, and policy-constrained visibility so that both humans and agents can discover eligible collaborators.

## 50. Conversations, Interactions, Workspace Goals, and Super-Context

### FR-253 Conversations as Shared Context Containers
The platform shall support **conversations** as shared context containers that preserve message history, prior exchanges, and continuity across multiple related tasks.

### FR-254 Interactions as Bounded Task Units
The platform shall support **interactions** as bounded task units inside or alongside a conversation, each representing a distinct execution objective.

### FR-255 Unique Interaction Identifiers
Each interaction shall have a unique interaction identifier that prevents accidental cross-updates when multiple tasks coexist in the same higher-level conversation.

### FR-256 Multiple Concurrent Interactions per Conversation
A single conversation shall be able to contain multiple active or paused interactions at the same time.

### FR-257 Interaction Lifecycle Visibility
Users and operators shall be able to inspect interaction lifecycle state, including whether an interaction is:
- initializing;
- ready;
- running;
- waiting;
- paused;
- completed;
- failed;
- canceled.

### FR-258 Start-Conversation APIs and UI Flows
The platform shall provide APIs and UI flows to start a new conversation with a selected agent, returning enough identifiers to continue, monitor, or audit that conversation later.

### FR-259 Mid-Process Message Injection
The platform shall allow authorized users or systems to add new messages, clarifications, or instructions to an existing conversation or interaction during execution.

### FR-260 Workspace Goals
The platform shall support the creation of **workspace goals** that can be posted into a workspace context for goal-oriented execution, not only direct task-oriented agent invocations.

Workspace goals shall be tracked via Goal IDs (GIDs) as a first-class correlation dimension. Each goal follows lifecycle: READY → WORKING → COMPLETE. Agents use configurable decision mechanisms to decide whether to respond to each workspace message (FR-430). Messages are organized around goals with goal-scoped visibility.

### FR-261 Workspace as a Shared Super-Context
A workspace shall be able to act as a **shared super-context** in which messages, goals, state, policies, and subscribed agents or fleets collaborate around a common objective.

### FR-262 Goal-Oriented Workspace Participation
The platform shall support goal-oriented agents, or equivalent runtime roles, that can subscribe to workspace contexts and decide whether to act based on policy, role, or intent.

### FR-263 User Alerts and Status Notifications
The system shall support user alerts or notifications for conversation, interaction, or workspace-goal events such as:
- waiting for input;
- approval requested;
- execution failed;
- execution completed;
- certification or policy violation relevant to the user.

## 51. Event-Driven Communication and Interaction Management

### FR-264 Event-Driven Multiagent Runtime Coordination
The platform shall support event-driven communication as a first-class coordination model for asynchronous multiagent and multifleet execution.

### FR-265 Reliable Delivery and Persistence
The event-driven coordination model shall support durable message persistence, retries, and safe recovery of outstanding work.

### FR-266 Pub/Sub-Style Fan-Out
The platform shall support pub/sub-style fan-out for scenarios where multiple agents, observers, auditors, or operational services need to react to the same event stream.

### FR-267 Event Replay for Investigation and Recovery
The platform shall support replay of relevant event streams or execution segments for investigation, reconstruction, recovery, or compliance use cases.

### FR-268 Queue and Backlog Visibility
Operators shall be able to inspect queue health, backlog, and blocked or delayed work items associated with agent, workflow, workspace, or fleet communication channels.

### FR-269 Direct Agent-to-Agent Delegation Model
The platform shall support a direct agent-to-agent delegation model in which one agent can hand off a subset of a task to another agent without forcing all such communication through a human-facing surface.

### FR-270 User-to-Agent Interaction Server Semantics
The platform shall expose user-to-agent interaction semantics through APIs that can initiate work, check status, add context, and return user-facing results.

### FR-271 Agents as Explicit Plan Participants
An execution plan shall be able to reference other agents as explicit plan participants or plan steps rather than limiting plans to only tools or internal functions.

### FR-272 Message Stream Visibility for Oversight Roles
Authorized auditors, debuggers, or operators shall be able to access approved slices of message streams, interaction history, or event traces for investigation and oversight.

## 52. Trust, Certification, and Governance Expansion

### FR-273 Two-Layer Trust Model
The platform shall distinguish between:
- trust in the individual agent; and
- trust in the surrounding ecosystem, governance, and certification system.

### FR-274 Seven-Layer Trust Framework Alignment
The trust and governance model shall cover, at minimum, the following layers:
- identity and authentication;
- authorization and access control;
- purpose and policies;
- task planning and explainability;
- observability and traceability;
- certification and compliance;
- governance and lifecycle management.

The seven layers shall be explicitly mapped: Layer 1 (Identity — FQN + mTLS + IBOR), Layer 2 (Authorization — RBAC + zero-trust default), Layer 3 (Purpose & Policies — natural-language purpose + machine-enforceable policies), Layer 4 (Task Planning & Explainability — TaskPlanRecord + tool selection rationale), Layer 5 (Observability & Traceability — structured logging + IID/GID correlation), Layer 6 (Certification & Compliance — ATE + third-party + surveillance), Layer 7 (Governance & Lifecycle — continuous review + decommissioning).

### FR-275 Verifiable Agent Identity and Declared Purpose
Every publishable agent revision shall have a verifiable identity and a declared purpose that can be shown to both humans and enforcement systems.

### FR-276 Purpose-Bound Authorization
Authorization decisions for agents shall be enforceable not only by generic role or permission, but also by whether the action remains within the agent's declared purpose.

### FR-277 Machine-Readable Policy Definitions
Policies shall be machine-readable, versioned, attachable, and enforceable at runtime.

### FR-278 Runtime Explainability Obligations
For applicable executions, the platform shall preserve enough explainability data to inspect:
- task decomposition;
- tool selection;
- collaborator selection;
- parameterization decisions;
- execution sequence;
- reasoning chain traces.

### FR-279 Observability and Traceability Obligations
The platform shall preserve traceability across users, agents, fleets, tools, workflows, connectors, and certifications so that investigators can reconstruct who did what, when, and why.

### FR-280 Agent Certification Workflows
The platform shall support agent certification workflows that can validate an agent revision against trust, policy, explainability, resilience, and compliance criteria before broader publication or privileged use.

Certification workflows shall include: application with technical documentation of purpose/policies/architecture; evaluator review with risk assessment; testing in accredited environments (ATEs); iterative review; deployment environment inspection; formal certification issuance with published metrics; support for third-party certifiers (FR-445); and ongoing surveillance (FR-446).

### FR-281 Certification Lifecycle Management
The platform shall support certification lifecycle actions such as:
- issuance;
- renewal;
- expiration;
- revocation;
- suspension;
- recertification after material change.

### FR-282 Fleet Certification Workflows
Where fleets are supported, the platform shall support certification of a fleet as an end-to-end managed system and not only as a loose collection of individually certified agents.

### FR-283 Trust-Aware Discovery and Filtering
Discovery surfaces shall allow filtering or ranking based on certification, policy conformance, publisher trust, operational history, or other trust signals.

## 53. Fleets, Teamed Agents, and Observer Agents

### FR-284 Fleet Abstraction
The platform shall support a **fleet** abstraction for grouping agents into a managed team with shared purpose, topology, or operational policy.

### FR-285 Fleet Membership and Purpose
A fleet shall be able to declare:
- its purpose;
- its members;
- its orchestration style;
- its owner or owning workspace;
- its applicable policies and trust requirements.

### FR-286 Fleet Topologies
The platform shall support one or more fleet topologies, including:
- hierarchical;
- peer-to-peer;
- hybrid.

### FR-287 Fleet Orchestration and Escalation Rules
Fleets shall support rules for:
- task division;
- delegation;
- result aggregation;
- conflict handling;
- retry or reassignment;
- escalation to humans or other systems.

### FR-288 Fleet Lifecycle and Elastic Scaling
The platform shall support fleet lifecycle actions and elastic scaling behavior such as:
- start;
- stop;
- pause;
- scale up;
- scale down;
- rolling replacement of members.

### FR-289 Observer Agents
The platform shall support observer-style agents, or equivalent fleet monitoring roles, that can watch activity, detect anomalies, or summarize execution without directly owning the primary task.

Observer agents function as both sensors (detecting anomalies, threshold breaches) and smart actuators (triggering alerts, signals, escalation). Multiple observers can collaborate using a shared scratchpad workspace to corroborate signals. Observers feed signals to judge agents (FR-434), which evaluate against policies before enforcers (FR-435) act. The Observer → Judge → Enforcer pipeline is configurable per fleet (FR-436).

### FR-290 Fleet Degraded Operation
Where a fleet member fails or becomes unavailable, the platform shall support continuing operation at degraded capacity when policy allows.

### FR-291 Fleet-of-Fleets Collaboration
The platform shall support collaboration patterns in which fleets can coordinate with other fleets through governed discovery, routing, and policy-aware communication.

## 54. Workbenches and Governance UX

### FR-292 Consumer Workbench
The platform shall provide a consumer workbench where users can:
- launch tasks;
- open conversations;
- inspect status;
- collaborate in workspace contexts;
- retrieve outputs and artifacts.

### FR-293 Creator Workbench
The platform shall provide a creator workbench where authorized users can:
- register new agents;
- update metadata;
- manage revisions;
- test endpoints or packaged agents;
- prepare publication;
- configure context engineering profiles;
- set reasoning mode preferences.

### FR-294 Trust Workbench
The platform shall provide a trust workbench where authorized reviewers can:
- configure policies;
- attach policies to agents or fleets;
- run checks;
- issue or revoke certifications;
- inspect evidence and trust history.

### FR-295 Operator Workbench
The platform shall provide an operator workbench where operators can:
- inspect health and throughput;
- investigate failures;
- view queue backlog;
- pause, resume, or roll back eligible workloads;
- access trace and diagnostic views according to permission;
- monitor fleet-level health aggregates;
- inspect reasoning budget consumption.

### FR-296 Home and Orientation Surface
The platform shall provide a home or landing view that surfaces recent activity, available services, pending approvals, and entry points into marketplace and workbenches.

### FR-297 Enterprise Identity Continuity Across Surfaces
When enterprise identity integration is enabled, permissions and identity shall remain consistent across marketplace, workbenches, and execution-control surfaces.

### FR-298 Operator Execution Controls
Authorized operators shall be able to pause, resume, cancel, or roll back eligible agent or fleet executions through governed controls rather than ad hoc infrastructure access.

### FR-299 Diagnostics and Troubleshooting Views
The platform shall provide diagnostics and troubleshooting views with drill-down capability by agent, fleet, user, interaction, execution, or task type.

## 109. Administrator Workbench

### FR-546 Administrator Workbench
The platform shall provide a dedicated administrator workbench at `/admin` accessible only to users holding the `admin` or `superadmin` role. The workbench shall provide a structured navigation covering all administrative concerns grouped into logical sections: **Identity & Access**, **Tenancy & Workspaces**, **System Configuration**, **Security & Compliance**, **Operations & Health**, **Cost & Billing**, **Observability**, **Integrations**, **Platform Lifecycle**, and **Audit & Logs**. The workbench shall be navigable entirely via keyboard, fully internationalized per FR-489, and WCAG AA compliant per FR-488. The workbench shall display the current platform instance name (from `PLATFORM_INSTANCE_NAME`), the signed-in administrator's identity and role scope, and the platform version.

### FR-547 Admin Dashboard Landing Page
The `/admin` landing page shall display a high-level operational summary: total users / workspaces / agents / fleets counts, pending approvals counter, active incidents counter (linked to UPD-031), active maintenance windows indicator, recent audit chain integrity check status, observability stack health (Prometheus / Grafana / Loki reachability), last successful backup timestamp, and any critical alerts from the last 24 hours. Each counter and indicator shall link to the corresponding detail page within the workbench.

### FR-548 Identity & Access Pages
The workbench shall include an Identity & Access section with the following pages:
- **Users** (`/admin/users`): list, filter, and paginate all users; bulk actions (approve, reject, suspend, force-MFA-enrollment, force-password-reset, delete); detail drawer showing profile, sessions, OAuth links, MFA status, role assignments, recent audit entries, active API keys.
- **Roles** (`/admin/roles`): manage built-in and custom roles; edit role permissions (read, write, admin per resource type); clone roles; assign roles to users or groups.
- **Groups** (`/admin/groups`): manage user groups imported via IBOR (LDAP / OIDC / SCIM) and local groups; map groups to roles.
- **Sessions** (`/admin/sessions`): view active sessions platform-wide; revoke individual sessions; bulk-revoke all sessions for a user (force re-login); view session geolocation metadata where available.
- **OAuth Providers** (`/admin/oauth-providers`): enable, disable, configure Google / GitHub / additional providers; rotate client secrets via vault; test provider connectivity.
- **IBOR Connectors** (`/admin/ibor`): configure LDAP / OIDC / SCIM connectors for user/agent sync; trigger manual sync; view sync history and error logs.
- **API Keys** (`/admin/api-keys`): list all service-account API keys platform-wide; rotate, revoke, view last-used timestamp and scope.

### FR-549 Tenancy & Workspaces Pages
The workbench shall include a Tenancy & Workspaces section with the following pages:
- **Tenants** (`/admin/tenants`) — super admin only: list tenants, create new tenant, suspend tenant, delete tenant (with cascade preview and confirmation), configure per-tenant quotas, isolation level, region assignment, data residency policy.
- **Workspaces** (`/admin/workspaces`): list all workspaces across tenants (super admin) or within current tenant (admin); create workspace; configure owners, members, quotas, visibility policies, region residency, DLP rules; archive or delete workspaces with cascade preview.
- **Workspace Quotas** (`/admin/workspaces/{id}/quotas`): configure max agents, max fleets, max executions per period, max storage, max cost per period; apply templates (small / medium / large) and override individual limits.
- **Namespace Management** (`/admin/namespaces`): create, rename, archive FQN namespaces within a workspace; set visibility defaults; reassign ownership.

### FR-550 System Configuration Pages
The workbench shall include a System Configuration section:
- **Platform Settings** (`/admin/settings`): instance name, default locale, default timezone, default currency (acknowledging the single-currency limitation), signup policy, approval policy, password policy, MFA policy, session timeout, rate-limit tier definitions.
- **Feature Flags** (`/admin/feature-flags`): view and toggle platform-wide feature flags (see FR-584); scope flag changes per tenant or per workspace; view flag change history.
- **Model Catalog** (`/admin/model-catalog`): list approved models; add / update / deprecate entries; upload model cards; configure fallback policies; test provider connectivity; view per-model usage and cost.
- **Policies** (`/admin/policies`): create and edit platform-wide policies; attach to tenants or workspaces; preview policy evaluation against sample executions.
- **Connector Plugins** (`/admin/connectors`): enable, disable, configure connector implementations (Slack, Telegram, Webhook, Email); rotate credentials via vault; test connectivity.

### FR-551 Security & Compliance Pages
The workbench shall include a Security & Compliance section:
- **Audit Chain Integrity** (`/admin/audit-chain`): view chain verification status; trigger ad-hoc verification; export signed audit log for regulatory periods; view chain anomalies history.
- **SBOM & Vulnerabilities** (`/admin/security/sbom`): view SBOMs for current and past releases; filter CVEs by severity; track remediation status; link findings to incidents.
- **Penetration Tests** (`/admin/security/pentests`): schedule, view status, upload attestation reports; track findings.
- **Secret Rotation** (`/admin/security/rotations`): view rotation schedules; trigger manual rotation; view rotation history; configure default rotation intervals per secret type.
- **JIT Credentials** (`/admin/security/jit`): view active JIT grants; approve pending requests; revoke credentials; view detailed usage audit.
- **Privacy & DSR** (`/admin/privacy/dsr`): queue of pending data subject requests; approve, execute, or deny; view cascade deletion preview; issue tombstones; notify subjects.
- **DLP Rules** (`/admin/privacy/dlp`): manage data loss prevention patterns; view DLP events; configure per-workspace overrides.
- **PIA Approvals** (`/admin/privacy/pia`): review privacy impact assessments; approve or request changes.
- **Compliance Evidence** (`/admin/compliance`): SOC2 / ISO27001 / HIPAA / PCI control mapping; evidence collection status; export evidence bundles.
- **Consent Records** (`/admin/privacy/consent`): view aggregated consent status; revoke consent on behalf of user with justification.

### FR-552 Operations & Health Pages
The workbench shall include an Operations & Health section:
- **System Health** (`/admin/health`): real-time status of all platform services and satellites; color-coded state; links to service logs in the Observability section.
- **Incidents** (`/admin/incidents`): active and historical incidents; create manual incident; link to runbooks; generate post-mortem draft with timeline reconstruction.
- **Runbooks** (`/admin/runbooks`): library of runbooks; create, edit, assign to incidents; track runbook execution history.
- **Maintenance Mode** (`/admin/maintenance`): schedule maintenance windows; start/stop maintenance mode immediately; view in-flight work drain status; configure user-facing maintenance message.
- **Multi-Region Operations** (`/admin/regions`) — super admin only: view regions, replication lag per data store and component, RPO/RTO status, trigger failover test (requires two-person authorization), initiate failback.
- **Queue Health** (`/admin/queues`): Kafka consumer lag by topic, DLQ sizes, throughput metrics; ability to replay from DLQ or purge with confirmation.
- **Warm Pool** (`/admin/warm-pool`): view per-agent-type pool size, hit rate, cold-start latency; adjust pool sizes per workspace.
- **Execution Controls** (`/admin/executions`): pause, resume, cancel, or rollback any execution platform-wide; view execution status across tenants.

### FR-553 Cost & Billing Pages
The workbench shall include a Cost & Billing section:
- **Cost Overview** (`/admin/costs/overview`): platform-wide cost view (super admin) or tenant-scoped; drill down by workspace / agent / user / model.
- **Budgets** (`/admin/costs/budgets`): manage workspace budgets; view threshold breaches; approve admin overrides.
- **Chargeback Reports** (`/admin/costs/chargeback`): generate and export chargeback reports per period.
- **Anomalies** (`/admin/costs/anomalies`): review and acknowledge cost anomalies; mark false positives.
- **Forecasts** (`/admin/costs/forecasts`): platform and per-workspace forecasts with confidence intervals.
- **Provider Cost Rates** (`/admin/costs/rates`): configure cost rates per model provider, per compute type, per storage tier; apply overrides for negotiated contracts.

### FR-554 Observability Admin Pages
The workbench shall include an Observability section linking to the Grafana deployment:
- **Dashboards** (`/admin/observability/dashboards`): link to each of the 21 Grafana dashboards; embed thumbnails.
- **Alert Rules** (`/admin/observability/alerts`): view Prometheus and Loki alert rules; enable, disable, silence; view alert history.
- **Log Retention** (`/admin/observability/log-retention`): configure hot/cold retention per tenant.
- **Dashboard Registry** (`/admin/observability/registry`): view all provisioned dashboards; trigger reload on ConfigMap change.

### FR-555 Integrations Admin Pages
The workbench shall include an Integrations section:
- **Outbound Webhooks** (`/admin/integrations/webhooks`): manage outbound webhook registrations; view delivery status; retry failed deliveries; rotate signing secrets.
- **Incident Integrations** (`/admin/integrations/incidents`): configure PagerDuty / OpsGenie / VictorOps endpoints.
- **Notification Channels** (`/admin/integrations/notifications`): manage platform-level notification templates; test delivery per channel.
- **A2A Directory** (`/admin/integrations/a2a`): when A2A gateway is implemented, register and manage external agent card URLs; view federation topology.
- **MCP Catalog** (`/admin/integrations/mcp`): when MCP integration is implemented, register MCP servers and tools; approve or revoke.

### FR-556 Platform Lifecycle Pages
The workbench shall include a Platform Lifecycle section — super admin only:
- **Version & Upgrade** (`/admin/lifecycle/version`): view current platform version per component; view pending upgrade; launch rolling upgrade with dry-run option.
- **Database Migrations** (`/admin/lifecycle/migrations`): view applied and pending Alembic migrations; launch migration with confirmation; view migration history.
- **Backup & Restore** (`/admin/lifecycle/backup`): trigger manual backup; view backup history; initiate restore to a point-in-time with confirmation.
- **Installer State** (`/admin/lifecycle/installer`): view initial install metadata (date, method, environment variables used, excluding secrets); view any pending post-install steps.

### FR-557 Audit & Logs Admin Pages
The workbench shall include an Audit & Logs section:
- **Audit Log** (`/admin/audit`): unified query interface over the audit chain; filter by event type, actor, resource, time range; export signed selection.
- **Admin Activity** (`/admin/audit/admin-activity`): filtered view of administrator actions only.
- **Log Explorer** (`/admin/logs`): embedded Grafana Explore filtered to the platform's Loki logs; preserves admin scope.
- **Debug Logging Sessions** (`/admin/debug-logging`): create, monitor, and stop time-bounded debug logging sessions per FR-500.

### FR-558 Admin Workbench Search
The admin workbench shall include a universal search (Cmd/Ctrl+K command palette scoped to admin) that queries users by name / email / ID, workspaces by name / ID, agents by FQN, executions by ID, audit entries by keyword, and configuration keys. Results shall be role-aware (super admin sees all tenants; admin sees their tenant only).

### FR-559 Admin Bulk Actions
All list pages in the workbench shall support multi-select and bulk actions where meaningful: bulk user actions (approve / reject / suspend / force-reset / delete), bulk workspace actions (archive / export / apply quota template), bulk incident actions (acknowledge / close / reassign). Bulk actions shall have confirmation dialogs with action summaries and shall emit a single consolidated audit chain entry per batch.

### FR-560 Admin Change Preview and Dry-Run
Destructive or impactful admin actions (tenant deletion, workspace archiving, policy changes affecting >N existing executions, model catalog deprecation, failover, large-scale quota changes) shall show a change preview describing: affected entities with counts, expected side effects (cascade implications), irreversibility classification (reversible / partially reversible / irreversible), and estimated execution duration. Super admin shall be able to enforce a dry-run step before apply.

### FR-561 Two-Person Authorization for Critical Admin Actions
Critical admin actions shall require two-person authorization (2PA): super admin password reset, tenant deletion, platform-wide failover, mass secret rotation, audit chain truncation (if ever implemented), `--force-reset-superadmin` via CLI. The initiating admin enters credentials; a second authorized admin must approve within a configurable window (default 15 minutes) from a separate session. 2PA events shall emit critical audit chain entries.

### FR-562 Admin Impersonation with Full Audit
Super admins shall be able to impersonate a user for a time-bounded session (max 30 minutes) for troubleshooting purposes. Impersonation requires justification, emits an audit chain entry, triggers a notification to the impersonated user, and watermarks the impersonated UI session with a clear "Impersonating {username}" banner. Actions performed during impersonation shall be audited as `impersonation_user=<admin>, effective_user=<target>`.

### FR-563 Admin Read-Only Mode
The workbench shall support a read-only mode per admin session, activated by a header toggle. In read-only mode all write actions (including bulk) are hidden or disabled. The toggle state persists per session and is visible in the header. Useful for safe exploration and for running training sessions.

### FR-564 Admin Workbench Real-Time Updates
Key counters and indicators on the admin dashboard landing (FR-547) and on the Incidents, Queue Health, Warm Pool, Maintenance, and Multi-Region pages shall update in real time via WebSocket subscription (no page refresh required). Connection status indicator shall be visible.

### FR-565 Admin API Endpoints
Every admin UI page shall have corresponding admin REST endpoints under `/api/v1/admin/*`. Endpoints shall require `admin` or `superadmin` role and shall be segregated from non-admin endpoints in the OpenAPI specification. Endpoints include at minimum:
- `/api/v1/admin/users/*` — user lifecycle
- `/api/v1/admin/roles/*` — role management
- `/api/v1/admin/groups/*` — group management
- `/api/v1/admin/sessions/*` — session management and revocation
- `/api/v1/admin/oauth-providers/*` — OAuth provider CRUD
- `/api/v1/admin/ibor-connectors/*` — IBOR CRUD and trigger
- `/api/v1/admin/api-keys/*` — service-account API keys
- `/api/v1/admin/tenants/*` — tenant lifecycle (super admin only)
- `/api/v1/admin/workspaces/*` — workspace lifecycle and quotas
- `/api/v1/admin/namespaces/*` — namespace CRUD
- `/api/v1/admin/settings` — platform settings GET/PUT
- `/api/v1/admin/feature-flags/*` — feature flag CRUD
- `/api/v1/admin/policies/*` — platform policies
- `/api/v1/admin/connectors/*` — connector plugin config
- `/api/v1/admin/health` — real-time health
- `/api/v1/admin/incidents/*` — incident management
- `/api/v1/admin/runbooks/*` — runbook library
- `/api/v1/admin/maintenance/*` — maintenance mode control
- `/api/v1/admin/queues/*` — queue health and DLQ operations
- `/api/v1/admin/warm-pool/*` — warm pool management
- `/api/v1/admin/executions/*` — execution control
- `/api/v1/admin/dsr/*` — data subject requests (admin scope)
- `/api/v1/admin/dlp/*` — DLP rule management
- `/api/v1/admin/pia/*` — PIA review
- `/api/v1/admin/compliance/*` — compliance evidence
- `/api/v1/admin/consent/*` — consent records
- `/api/v1/admin/sbom/*` — SBOM management
- `/api/v1/admin/scans/*` — vulnerability scans
- `/api/v1/admin/pentests/*` — pen test management
- `/api/v1/admin/rotations/*` — rotation schedules
- `/api/v1/admin/jit/*` — JIT credentials
- `/api/v1/admin/audit/*` — audit query and export
- `/api/v1/admin/costs/*` — cost admin endpoints
- `/api/v1/admin/model-catalog/*` — model catalog admin endpoints
- `/api/v1/admin/regions/*` — multi-region operations
- `/api/v1/admin/integrations/*` — integrations
- `/api/v1/admin/lifecycle/*` — platform lifecycle
- `/api/v1/admin/impersonation` — impersonation session management
- `/api/v1/admin/2pa/*` — two-person authorization tokens

### FR-566 Admin API Rate Limits
Admin API endpoints shall have rate limits distinct from and generally more generous than user-facing endpoints. Super admin actions on platform-lifecycle endpoints shall have lower per-minute limits with explicit rationale (these are destructive operations, not high-frequency operations).

### FR-567 Admin Activity Feed
The workbench shall display an admin activity feed (`/admin/audit/admin-activity` and embedded on the landing page) showing: who did what, when, with diff of before/after where relevant (role assignment, setting change), and a link to the underlying audit chain entry. Admins see their own tenant's activity; super admins see all tenants.

### FR-568 Admin Workbench Tour and Onboarding
On first login, a new admin (but not super admin on bootstrap) shall be offered a guided tour covering: navigation, key pages (Users / Workspaces / Settings / Audit), where to find help, and how to contact super admin. The tour shall be dismissible and repeatable. For super admin on bootstrap, a first-install checklist shall be presented: verify instance settings, invite other admins, configure OAuth providers, install observability stack, run first backup, review security settings.

### FR-569 Admin Help Context
Every admin page shall include inline help context: a collapsible panel explaining the purpose of the page, linking to runbooks where relevant, and linking to the FR or architecture section for deeper reference. Help content shall be authored alongside the page and localized per FR-489.

### FR-570 Admin Workbench Accessibility and i18n
The admin workbench shall fully comply with WCAG 2.1 AA (per FR-488) and shall be fully internationalized across the six supported languages (per FR-489). All destructive action dialogs shall clearly describe consequences in the user's locale.

### FR-571 Admin Workbench Theming
The admin workbench shall honor the user theme preference (light / dark / system / high-contrast per FR-490). The admin workbench shall additionally offer an optional visual distinction (e.g., thin red top border or distinct accent color) to signal to admins that they are operating in an elevated privilege context, reducing accidental misuse.

### FR-572 Admin Export of Configuration
Admins shall be able to export platform and tenant configuration (settings, policies, quotas, roles, connectors, feature flags, model catalog entries — excluding secrets) as a signed YAML bundle. Super admins shall be able to import such a bundle to bootstrap a new environment from an existing one. Imports shall produce a diff preview and require explicit confirmation.

### FR-573 Admin Session Security
Admin sessions shall enforce stricter security requirements than regular user sessions: shorter idle timeout (default 30 minutes, configurable down to 5 minutes), mandatory MFA step-up for destructive actions (e.g., tenant deletion, 2PA initiation), IP allowlisting option at tenant and platform level, session binding to IP + user-agent (new combination requires re-authentication).

### FR-574 Admin Notifications Preferences
Admins shall have distinct notification preferences from regular users: default notification channels for incidents, budget breaches, security events, certification expiries, maintenance windows affecting their tenants. Super admins shall additionally receive platform-wide events (failover, bootstrap complete, upgrade complete).

### FR-575 Admin Page URL Scheme
Admin pages shall use a consistent URL scheme under `/admin/` with predictable hierarchy, such that deep-linking and bookmarking to specific resources (e.g., `/admin/workspaces/abc123/quotas`) works reliably. Breadcrumbs shall render at the top of every admin page.

### FR-576 Admin Data Table Standards
All admin list pages shall use a consistent data-table pattern: server-side pagination (default 50 per page, configurable up to 500), sortable columns, column-level filters, free-text search, column visibility toggle, CSV export of current result set, saved views per user (per FR-512).

### FR-577 Admin Action Confirmation Rules
Confirmation dialog requirements scale with impact:
- No-confirmation: read-only and low-impact actions.
- Simple-confirmation (one click): reversible actions affecting one entity.
- Typed-confirmation (user types entity name or specific phrase like `DELETE`): irreversible or high-impact actions.
- 2PA: critical actions per FR-561.

### FR-578 Admin Feature Flag Granularity
The Feature Flags admin page (FR-550) shall support: global flags (platform-wide), tenant-scoped overrides, workspace-scoped overrides, per-user overrides (for gradual rollout to specific admins). Flag changes shall emit audit chain entries including the diff and rationale.

### FR-579 Super Admin Break-Glass Access
A super admin shall have a documented break-glass procedure for recovery when other super admins are unavailable: console-level CLI access via `platform-cli superadmin recover` which requires physical cluster access and a second-factor present on the cluster (e.g., a sealed emergency key). Use of break-glass access shall emit a critical audit chain entry and notify any remaining super admins via all configured channels.

### FR-580 Admin Monitoring Integration
The admin workbench Operations & Health and Observability sections shall embed live Grafana panels from the 21 platform dashboards where contextually useful, without requiring the admin to leave the workbench. Embedded panels shall respect the admin's scope (tenant-scoped for admins, platform-wide for super admin).

### FR-581 Admin Workbench E2E Coverage
The admin workbench shall be covered by two E2E user journeys: the existing **J01 Platform Administrator** journey (extended to cover new admin pages) and a new **J18 Super Admin Platform-Lifecycle** journey exercising tenant creation, platform settings, maintenance mode, failover test, break-glass simulation, 2PA, and audit export. Both journeys shall exercise keyboard-only navigation and axe-core scanning per FR-526.

### FR-582 Admin Workbench Mobile Layout
The admin workbench shall be usable on tablet (≥ 768 px wide) for read-mostly admin tasks (check health, acknowledge alerts, review DSRs). Full admin workflows require a desktop viewport. An information banner shall indicate when certain workflows are desktop-only.

### FR-583 Admin Error Handling and Diagnostics
All admin API errors shall return structured error responses with: machine-readable error code, human-readable message, suggested action, and a correlation ID linking to the full audit trail. The workbench shall surface errors inline with the action that triggered them, not as page-level toasts that scroll off screen.

### FR-584 Admin Feature Flag Inventory (Admin-Controlled)
In addition to flags defined in prior FRs, the admin workbench shall expose the following admin-visible and admin-controlled flags: `FEATURE_SIGNUP_ENABLED`, `FEATURE_SIGNUP_REQUIRES_APPROVAL`, `FEATURE_SOCIAL_LOGIN_ENABLED`, `FEATURE_MAINTENANCE_MODE`, `FEATURE_API_RATE_LIMITING`, `FEATURE_DLP_ENABLED`, `FEATURE_COST_HARD_CAPS`, `FEATURE_CONTENT_MODERATION`, `FEATURE_IMPERSONATION_ENABLED`, `FEATURE_TWO_PERSON_AUTHORIZATION`, `FEATURE_READ_ONLY_ADMIN_MODE`. All flag defaults are documented in the constitution and installer.

### FR-585 Super Admin Platform Tenant Mode
When `PLATFORM_TENANT_MODE=single` (the default), the Tenants page (FR-549) is hidden and all tenant-scoping UI elements are suppressed; the platform operates as a single-tenant deployment. When `PLATFORM_TENANT_MODE=multi`, the full tenancy UX is exposed. Switching modes after installation requires a super admin decision, 2PA approval, and emits a critical audit chain entry. Downgrading from `multi` to `single` is blocked if more than one tenant exists.

## 110. Public Signup, Account Activation, and OAuth UI

### FR-586 Public Signup Page
The platform shall provide a public signup page at `/signup` where anonymous users can create a local account with email and password, when self-signup is enabled via platform setting (FR-015). The page shall require email (validated against RFC 5322), full name, password, and explicit consent checkbox for AI interaction disclosure (per FR-510) and terms of service. The page shall be reachable from the login page and vice versa. When self-signup is disabled, the page shall show a clear message and a link to contact the administrator, never a 404.

### FR-587 Signup Password Policy Enforcement
The signup form shall enforce the platform password policy client-side for fast feedback (minimum length, character classes, common-password rejection via client-side wordlist), AND re-validate server-side as the authoritative check. Client-side validation is a UX optimization only; the server rejects weak passwords regardless of client validation.

### FR-588 Signup Rate Limiting and Bot Protection
The signup endpoint and page shall apply stricter rate limiting than general API endpoints: per-IP limit (default 5 attempts per hour), per-email limit (default 3 attempts per 24h against the same email), optional CAPTCHA (hCaptcha or Turnstile) activatable by admin via platform setting. Rate-limit responses return HTTP 429 with `Retry-After`.

### FR-589 Email Verification Flow
On successful signup, the platform shall send an email-verification message containing a time-bounded, single-use token (default 24h expiry). The message template is localized per user's browser `Accept-Language`. The user clicks the link, which routes to `/verify-email?token=…`; the page validates the token and transitions the account from `pending_verification` to `pending_approval` (if approval required per FR-016) or directly to `active`. Expired or already-used tokens produce a clear error with a "resend verification" action.

### FR-590 Verification Email Resend
The platform shall provide a page at `/verify-email/pending` shown immediately after signup that: informs the user the email has been sent, allows them to enter an email to resend the verification (rate-limited per FR-588), links to contact support. A resend invalidates the previous token. The user cannot log in until verification completes.

### FR-591 Admin Approval Waiting Page
When the platform is configured to require administrator approval (FR-016), after email verification the user lands on `/waiting-approval` showing: current status, estimated review time (configurable per tenant), contact administrator link. The user receives an email notification when approval is granted or rejected. The user cannot log in until approved.

### FR-592 Signup via OAuth (Google / GitHub)
The signup page shall display "Sign up with Google" and "Sign up with GitHub" buttons when those providers are enabled via admin (FR-449, FR-450). Clicking initiates the OAuth authorization flow; the callback handler auto-provisions a local account (per FR-448) and applies: the same approval requirement as local signup (if FR-016 is enabled, OAuth-provisioned users also await approval); MFA enrollment requirement consistent with local users; domain/org restrictions (FR-449, FR-450) validated before auto-provisioning. A user who attempts OAuth signup from an unauthorized domain/org sees a clear error page explaining the restriction and linking to administrator contact.

### FR-593 OAuth Callback Page
The platform shall have a dedicated frontend page at `/auth/oauth/{provider}/callback` handling OAuth callbacks with a loading state, error state with retry, and success handoff. The callback page receives auth material from the backend (via secure fragment, not query string) and completes the session establishment without exposing tokens in browser history. This replaces the previous implicit-redirect-to-login-with-fragment pattern with an explicit, auditable page.

### FR-594 OAuth Link Management UI
The platform shall provide a page at `/settings/account/connections` where authenticated users can: view which OAuth providers are currently linked to their account, link a new provider (initiating OAuth from settings, not signup), unlink a provider (blocked if it's the only authentication method available to the account without a local password). Linking/unlinking emits audit entries.

### FR-595 OAuth Admin UI Configuration
The admin workbench (FR-550, `/admin/oauth-providers`) shall surface full configuration of Google and GitHub providers: enable/disable toggle, client ID field, client secret reference to vault (secret input is write-only, never displayed), authorized redirect URI, domain restrictions (Google Workspace) / org restrictions (GitHub), group/team-to-role mapping table, test-connectivity button that performs a dry-run authorization flow. All admin changes emit audit chain entries.

### FR-596 First-Time OAuth Login Profile Completion
On a user's first successful OAuth login, if the external profile is missing platform-required fields (locale, timezone, display name preference), the platform shall present a lightweight profile completion page before granting full access. This is a one-time form; after completion the user proceeds normally.

### FR-597 Login Page OAuth Integration
The login page shall display OAuth provider buttons above or alongside the email/password form (per product design choice), each labeled with provider brand guidelines ("Continue with Google", "Continue with GitHub"). Provider buttons are hidden when no provider is enabled. Button styling complies with Google and GitHub brand guidelines.

### FR-598 Account Recovery via Linked OAuth
When a user has forgotten their password AND has an OAuth provider linked, the "Forgot password?" flow shall offer OAuth login as an alternative recovery path ("Sign in with Google to regain access"). After OAuth authentication, the user can set a new local password. This reduces support burden for lost passwords while maintaining security.

### FR-599 Signup E2E Coverage
E2E journey tests shall cover the full signup lifecycle: local email+password signup → email verification → admin approval (when enabled) → first login → workspace onboarding; Google OAuth signup → domain restriction check → auto-provisioning → first login; GitHub OAuth signup → org restriction check → auto-provisioning → first login. These scenarios extend the J02 Creator journey and the J03 Consumer journey, plus a new J19 New User Signup journey.

## 111. Multilingual README

### FR-600 Multilingual Repository README
The repository shall include a primary `README.md` at the root plus six localized variants: `README.md` (English, canonical and linked from GitHub), `README.es.md` (Spanish), `README.it.md` (Italian), `README.de.md` (German), `README.fr.md` (French), `README.zh.md` (Simplified Chinese). Each README shall be a full, self-contained introduction to the project — not a stub. The English README shall have a top-section "Read in other languages" bar linking to each localized variant, and each localized README shall have a link back to English.

### FR-601 README Content Structure
Each README shall contain the following sections, consistent across languages:
1. Project tagline and one-paragraph description
2. Badges (build status, license, supported Kubernetes versions, current version)
3. "What is Musematic?" — accessible description of the platform's purpose
4. Core capabilities (bullet list with short descriptions)
5. Quick start — 5-minute path to a running local install (kind-based)
6. Installation options overview (kind / k3s / Hetzner / managed K8s) with links to detailed guides
7. Architecture at a glance (single diagram + 3-4 paragraphs)
8. Documentation index (links to user guides, admin guides, API reference, architecture)
9. Contributing (linking to CONTRIBUTING.md)
10. License (linking to LICENSE)
11. Community and support (GitHub issues, discussions, security disclosure)

### FR-602 README Translation Management
README translations shall be treated as production artifacts: changes to the canonical English README require corresponding updates to all six variants within the same PR (or a documented grace period of 7 days during which the discrepancy is tracked as a GitHub issue). A CI check shall flag English-vs-localized drift by comparing section headings and link integrity.

### FR-603 README Asset Localization
Embedded diagrams, screenshots, and code blocks in the README shall either be language-neutral (architecture diagrams labeled in English, which all six variants can reuse) OR be localized per variant (screenshots of the UI in the target language where the UI is shown). The choice shall favor reusability; only UI screenshots require variants per language.

### FR-604 README Rendering Quality
Each README variant shall render correctly on GitHub (Markdown Flavor + GFM extensions), on GitLab (compatible subset), and in common markdown renderers (pandoc, MkDocs). Links to GitHub-specific pages (issues, discussions) remain valid even when the repo is mirrored to GitLab.

## 112. Comprehensive Documentation and Installation Guides

### FR-605 Documentation Site Structure
The platform shall publish a comprehensive documentation site structured into the following top-level sections:
- **Getting Started** — 5-minute demos, glossary, first tutorial
- **User Guide** — consumer workflows, creator workflows, workspace collaboration, workbenches
- **Administrator Guide** — admin workbench pages explained, platform settings, identity management, tenancy, compliance, incident response
- **Operator Guide** — runbooks, observability, incident response, capacity planning, backup/restore
- **Developer Guide** — building agents, SDK usage, contract authoring, MCP, A2A
- **API Reference** — auto-generated from OpenAPI 3.1 (per FR-497)
- **Architecture** — system architecture, software architecture, bounded contexts, data stores, event topology
- **Installation Guides** — kind, k3s, Hetzner with load balancer, managed K8s (GKE / EKS / AKS)
- **Configuration Reference** — all environment variables, all Helm values, all feature flags
- **Security Guide** — threat model, compliance, best practices, disclosure policy
- **Release Notes** — versioned changelog

### FR-606 Installation Guide — kind (Local Development)
The Kind installation guide shall walk through: prerequisites (Docker, Kind, Helm, kubectl versions), step-by-step cluster creation with `kind-config.yaml`, platform Helm install with `values-e2e.yaml`, observability stack install per UPD-035, seed data, accessing the UI at `localhost:8080`, uninstall/reset. Target time to completion: 15 minutes.

### FR-607 Installation Guide — k3s
The k3s installation guide shall cover a single-node k3s install suitable for small production or lab use: OS prerequisites (Ubuntu 22.04+, kernel modules), k3s install with appropriate arguments, storage class selection (local-path by default, longhorn optional), ingress controller (Traefik bundled), platform install via Helm, observability install, TLS via cert-manager + Let's Encrypt or provided certificate.

### FR-608 Installation Guide — Hetzner with Load Balancer
The Hetzner installation guide shall document a full production-grade install using Hetzner Cloud with load balancer. The guide shall cover:
- **Infrastructure provisioning** using Terraform (reusing the existing Hetzner Terraform modules): 1 control plane + 3 worker nodes on dedicated servers, private network, firewall rules, Hetzner Cloud Load Balancer in front of the ingress.
- **Kubernetes install via kubeadm** with containerd as runtime (per the existing Hetzner Terraform project).
- **Cluster networking**: MetalLB for `LoadBalancer` service type in addition to Hetzner's managed LB, Cilium or Calico for NetworkPolicy enforcement.
- **Ingress**: NGINX Ingress Controller with cert-manager issuing Let's Encrypt certificates.
- **Storage**: Longhorn for StatefulSets requiring persistent volumes.
- **Observability**: full stack via UPD-035 Helm bundle.
- **Platform install**: Helm with `values-hetzner-production.yaml` overlay.
- **DNS configuration**:
  - Development environment: `dev.musematic.ai` → frontend, `dev.api.musematic.ai` → backend API, `dev.grafana.musematic.ai` → Grafana.
  - Production environment: `app.musematic.ai` → frontend, `api.musematic.ai` → backend API, `grafana.musematic.ai` → Grafana.
- **TLS termination** at the ingress layer, with Let's Encrypt DNS-01 challenge for wildcard coverage.
- **Backup strategy** using the S3-compatible backup to Hetzner Storage Box or external S3.
- **Monitoring alarms** tied to Hetzner Cloud resource utilization (disk, CPU, memory).
- **Operational runbooks**: scaling nodes up, replacing a failed worker, rotating TLS certificates, running platform upgrades, multi-region add-on.

### FR-609 Installation Guide — Managed Kubernetes (GKE / EKS / AKS)
The managed Kubernetes installation guide shall document prerequisites for each cloud (IAM roles, VPC setup, node pool sizing), cloud-specific storage classes, cloud-native load balancers (GCP LB / AWS ALB / Azure Application Gateway), cloud-native DNS (Cloud DNS / Route 53 / Azure DNS), platform Helm install with cloud-specific overlays, observability install with cloud-native logging optional integration.

### FR-610 Environment Variables Reference
The Configuration Reference section shall contain an exhaustive table of every environment variable recognized by every platform component, with columns: variable name, service/component, required/optional, default value, description, security sensitivity classification. This table shall be machine-generated from the codebase (via a `scripts/generate-env-docs.py` pass over the code) to prevent drift.

### FR-611 Helm Values Reference
The Configuration Reference section shall contain an exhaustive reference of every Helm value in every chart (`deploy/helm/platform/values.yaml`, `deploy/helm/observability/values.yaml`, and sizing preset overlays), with default values, accepted types, and descriptions. This reference shall be machine-generated using `helm-docs` from YAML annotations.

### FR-612 Feature Flag Reference
The Configuration Reference section shall list every feature flag with: flag name, default, scope (platform / tenant / workspace / user), controlled by (role), description, related FRs, and rollout history.

### FR-613 URL and Domain Scheme Documentation
The documentation shall publish the canonical URL and domain scheme:
- **Development**: `dev.musematic.ai` (frontend), `dev.api.musematic.ai` (backend API), `dev.grafana.musematic.ai` (Grafana / observability).
- **Production**: `app.musematic.ai` (frontend), `api.musematic.ai` (backend API), `grafana.musematic.ai` (Grafana / observability).
- **Per-environment** patterns for additional environments: `{env}.musematic.ai` / `{env}.api.musematic.ai` / `{env}.grafana.musematic.ai`.
- **CORS policy**: frontend calls backend on its sibling domain; no cross-environment calls.
- **Cookie domain**: `.musematic.ai` for shared sessions across subdomains; separated for `.dev.musematic.ai` vs `.musematic.ai` to prevent dev sessions leaking into production.

### FR-614 TLS and Certificate Strategy Documentation
The documentation shall describe the TLS strategy: Let's Encrypt issuance via cert-manager using DNS-01 for wildcard certificates (one per environment: `*.musematic.ai`, `*.dev.musematic.ai`), certificate renewal on k-days-before-expiry basis, alerting on renewal failure, emergency manual renewal runbook.

### FR-615 Documentation Site Technology
The documentation site shall be built using a static-site generator (Docusaurus, MkDocs Material, or equivalent) with: search (Algolia or built-in), versioning (per platform version), language toggle for sections that support translation, dark-mode support consistent with the platform UI, accessibility AA compliance.

### FR-616 Documentation Review and Staleness Detection
Every FR and every architecture decision shall be linked from the documentation. A CI check shall flag documentation that references a FR number that no longer exists, or that hasn't been updated in the same PR that modifies the referenced FR. This check runs on every PR touching `docs/` or FR files.

### FR-617 Admin and Operator Runbook Library
The Operator Guide section shall include a runbook library covering at least: platform upgrade procedure, database migration rollback, disaster recovery (restore from backup), multi-region failover and failback (from UPD-025), secret rotation (from UPD-024), capacity expansion (adding worker nodes), emergency access (super admin break-glass per FR-579), incident response procedures (linked to UPD-031 runbooks), log query cookbook (LogQL examples for UPD-034 dashboards).

### FR-618 Security and Compliance Documentation
The Security Guide section shall include: threat model (with trust boundaries across planes), compliance mapping to SOC2 / ISO27001 / GDPR / HIPAA / PCI (with evidence substrate per UPD-024), responsible disclosure policy (SECURITY.md at repo root), PGP key for security reports, security contact email, expected response time.

### FR-619 API Reference Quality
The auto-generated API reference shall include: OpenAPI 3.1 spec download, interactive Swagger UI, interactive Redoc, code samples for each endpoint in Python/Go/TypeScript/curl (generated from OpenAPI), authentication guide, rate-limit documentation, error code catalog with remediation guidance, changelog of API changes per version with backward-compatibility annotations.

### FR-620 Documentation Localization Policy
User-facing documentation (Getting Started, User Guide, Administrator Guide) shall be localized into the six supported languages (English, Spanish, Italian, German, French, Simplified Chinese). Technical documentation (Developer Guide, Architecture, API Reference) remains English-only due to translation cost and audience expectations. The documentation site clearly labels which sections are localized and which are English-only.

## 55. Agent and Fleet Factory Capabilities

### FR-300 Agent Templates and Starter Kits
The platform shall support reusable agent templates or starter kits that provide baseline scaffolding for identity, observability, lifecycle hooks, and security posture.

### FR-301 Shared SDKs and Shared Libraries
The platform shall support centrally maintained SDKs or shared libraries that standardize how agents connect to mesh services, publish events, use memory, and integrate with certified connectors.

### FR-302 Certified Connectors and Integration Points
The platform shall support centrally maintained or certified integration points so that creators do not need to build unsafe one-off integrations for common enterprise systems.

### FR-303 Agent Assembly Workflows
The platform shall support assembly workflows or equivalent composition patterns in which an agent can be constructed from modular parts such as tools, skills, personas, prompts, or policies.

### FR-304 Pre-Publication Validation and Certification Readiness
Before publication, the platform shall support validation workflows that confirm an agent or fleet is ready for policy checks, security checks, testing, and certification.

### FR-305 Fleet Templates and Reference Topologies
The platform shall support fleet templates or reference topologies so that creators can assemble tested multiagent structures without inventing orchestration patterns from scratch.

### FR-306 Fleet Stress Testing and Resilience Playbooks
The platform shall support resilience validation or playbook-driven stress testing for fleets under conditions such as load spikes, member churn, and partial failure.

### FR-307 Automated Lifecycle Management for Agents and Fleets
The platform shall support automated lifecycle actions for agents and fleets, including onboarding, retiring, replacing, version promotion, and certification-triggered recertification workflows.

## 56. Additional Functional Acceptance Criteria for Agentic Mesh Alignment

In addition to the earlier acceptance criteria, this revision shall not be considered complete unless all of the following are also true:

1. at least one agent can be discovered through a marketplace that exposes trust signals, lifecycle state, and revision identity;
2. at least one registry-backed record exists for an agent, a conversation, an interaction, and a policy or certification object;
3. at least one conversation can host more than one bounded interaction without state collision;
4. at least one workspace can act as a shared execution context for a goal-oriented collaboration pattern;
5. at least one multiagent flow uses event-driven coordination with recoverable or replayable runtime evidence;
6. at least one agent revision can be filtered or selected based on certification or policy trust signals;
7. at least one fleet can be created, inspected, and governed as a managed team abstraction;
8. consumer, creator, trust, and operator workbench roles can each access at least one dedicated product surface;
9. at least one agent or fleet can be created from reusable template or factory scaffolding rather than ad hoc assembly.

## 57. Context Engineering as a Formal Discipline

### FR-308 Context Engineering Profiles
The platform shall support named, versioned **context engineering profiles** that define how runtime context is assembled, scored, compacted, and budgeted for a given agent, workflow, or execution scope.

### FR-309 Context Quality Scoring
The platform shall compute and expose a **context quality score** for each context assembly operation, incorporating factors such as:
- relevance of retrieved sources;
- recency and freshness of included information;
- source authority ranking;
- contradiction density;
- token utilization efficiency;
- coverage of the declared task brief.

### FR-310 Context Provenance Tracking
Every element included in a runtime context assembly shall carry **provenance metadata** indicating:
- origin source;
- retrieval timestamp;
- authority score;
- policy justification for inclusion;
- version or revision of the source.

### FR-311 Context Budget Management
The platform shall enforce configurable **context budgets** at the step, execution, and agent level, measured in:
- total tokens;
- estimated cost;
- maximum number of sources;
- maximum context window utilization percentage.

### FR-312 Context Compaction Strategies
The platform shall support configurable **context compaction** strategies for scenarios where assembled context exceeds budget or window limits, including:
- relevance-weighted truncation;
- summarization of older segments;
- priority-based source eviction;
- hierarchical compression preserving key facts.

### FR-313 Context A/B Testing
The platform shall support comparative evaluation of different context engineering profiles against the same task to measure their impact on output quality, cost, and latency.

### FR-314 Context Drift Detection
The platform shall monitor and alert when the quality or relevance of assembled context degrades over time for recurring workflows or agent patterns.

## 58. Agent Capability Maturity and Self-Assessment

### FR-315 Agent Capability Maturity Levels
The platform shall define and enforce a **capability maturity classification** for agents, aligned with the established agent complexity spectrum:
- **Level 0 — Core Reasoning Engine**: LLM-only, no tools, no memory, no environment interaction, no context engineering; responds solely from pre-trained knowledge;
- **Level 1 — Connected Problem-Solver**: tool use, external data access, multi-step action sequences; minimal context curation;
- **Level 2 — Strategic Problem-Solver**: active context engineering (selecting, packaging, compressing information per step), strategic planning, self-correction, proactive assistance, workflow management;
- **Level 3 — Collaborative Multi-Agent**: cross-agent context engineering, inter-agent communication, delegation, debate, fleet participation, autonomous coordination, self-improvement.
Context engineering proficiency (FR-417) shall be a primary differentiator between levels.

### FR-316 Maturity-Gated Capabilities
The platform shall support **maturity-gated capability access** so that agents at lower maturity levels cannot access features reserved for higher levels without explicit policy override.

### FR-317 Runtime Maturity Self-Report
Agent runtimes shall be able to **self-report** their effective capability maturity level based on their actual configuration, available tools, memory access, and collaboration capabilities.

### FR-318 Maturity-Aware Marketplace Filtering
The marketplace shall support filtering and sorting agents by their declared or assessed capability maturity level.

### FR-319 Maturity Progression Tracking
The platform shall track and visualize how an agent's capability maturity evolves across revisions and certification milestones.

## 59. Self-Correction and Iterative Refinement

### FR-320 Self-Correction as a Native Runtime Capability
The platform shall support **self-correction loops** as a native runtime capability, not only as an optional prompt-engineering technique.

### FR-321 Configurable Self-Correction Policies
Self-correction shall be governed by configurable policies including:
- maximum correction iterations;
- quality convergence threshold;
- cost cap for correction loops;
- mandatory correction for high-risk outputs;
- human escalation trigger when convergence fails.

### FR-322 Self-Correction Trace Persistence
Each self-correction iteration shall persist:
- the original draft output;
- the critique or evaluation result;
- the revised output;
- the convergence metric;
- the iteration number.

### FR-323 Multi-Agent Review Loops
The platform shall support self-correction patterns involving **separate producer and reviewer agents**, where the reviewer provides structured feedback that the producer incorporates in subsequent iterations.

### FR-324 Convergence Detection
The platform shall detect when self-correction iterations reach **quality convergence** or **diminishing returns** and automatically terminate the loop rather than exhausting the iteration budget.

### FR-325 Self-Correction Analytics
The platform shall provide analytics on self-correction effectiveness, including:
- average iterations to convergence;
- cost of correction per execution;
- improvement delta per iteration;
- convergence failure rate.

## 60. Advanced Reasoning and Deliberation

### FR-326 Chain-of-Thought Persistence
The platform shall persist **chain-of-thought reasoning traces** as first-class execution artifacts, separate from final outputs, enabling post-hoc inspection, replay, and forensic analysis.

### FR-327 Tree-of-Thought Branching Support
The platform shall support **tree-of-thought** style execution where multiple reasoning paths are explored concurrently, evaluated, and the best path selected for continuation.

### FR-328 Reasoning Mode Selection
The platform shall support automatic reasoning mode selection based on task metadata, policy constraints, and budget envelope. Available modes: DIRECT (single-pass, no extended reasoning), CHAIN_OF_THOUGHT (CoT — step-by-step decomposition), TREE_OF_THOUGHT (ToT — branching exploration of multiple paths), REACT (reasoning + acting with interleaved tool use), CODE_AS_REASONING (program-aided reasoning), DEBATE (Chain of Debates with multiple agents engaging in structured rounds), and SELF_CORRECTION (iterative refinement loop). Mode selection shall also consider the Scaling Inference Law: the configurable compute budget allocated to "thinking time" that determines how deeply the agent reasons. Higher compute budgets enable wider ToT branching, more CoT steps, more debate rounds, and more self-correction iterations at the cost of increased latency and token usage.

### FR-329 Reasoning Budget Allocation
The platform shall support allocating **reasoning budgets** as distinct resource envelopes, including:
- max reasoning tokens;
- max deliberation rounds;
- max thinking time;
- max cost for reasoning operations.

### FR-330 Reasoning Depth Adaptation
The platform shall support **adaptive reasoning depth** where the system automatically allocates more reasoning resources to harder problems and fewer to simpler ones.

### FR-331 Code-as-Reasoning Support
The platform shall support **program-aided language model** patterns where agents can generate and execute code as part of their reasoning process, using sandbox execution for computation and returning results to the reasoning chain.

### FR-332 Reasoning Quality Evaluation
The platform shall support evaluating the quality of reasoning traces, not only final outputs, using:
- logical consistency checks;
- step validity scoring;
- hallucination detection in intermediate steps;
- comparison against reference reasoning chains;
- trajectory-based evaluation (FR-411) assessing path efficiency, tool appropriateness, reasoning coherence, and cost-effectiveness of the full action sequence.
Reasoning quality data shall feed into the adaptation pipeline (FR-408) and the cost intelligence dashboard (FR-340).

## 61. Resource-Aware Optimization and Cost Intelligence

### FR-333 Dynamic Model Switching
The platform shall support **dynamic model switching** based on real-time task classification, selecting lightweight models for simple queries and more powerful models for complex reasoning tasks.

### FR-334 Contextual Pruning and Summarization
The platform shall support **automatic context pruning** that strategically minimizes token consumption by summarizing or selectively retaining only the most relevant information from interaction history.

### FR-335 Proactive Resource Prediction
The platform shall support **proactive resource prediction** that forecasts computational and cost requirements before execution begins, enabling pre-approval and budget validation.

### FR-336 Cost-Sensitive Multi-Agent Exploration
In multi-agent scenarios, the platform shall support **cost-sensitive exploration** that balances collaboration thoroughness against communication and computation costs.

### FR-337 Learned Resource Allocation Policies
The platform shall support **learned resource allocation** where the system adapts model selection, context strategies, and reasoning depth over time based on historical performance and cost data.

### FR-338 Graceful Degradation Under Resource Constraints
The platform shall support **graceful degradation** behavior when resource limits are reached, falling back to simpler models, reduced context, or cached results rather than failing completely.

### FR-339 Energy and Sustainability Metrics
The platform should track and expose **energy consumption and sustainability metrics** for agent executions where infrastructure data is available, supporting green AI objectives.

### FR-340 Cost Intelligence Dashboard
The platform shall provide a **cost intelligence dashboard** showing:
- cost per agent, workflow, and workspace;
- cost trends over time;
- cost-per-quality ratio by model and strategy;
- optimization recommendations;
- budget utilization and forecasting.

## 62. Agent-Builds-Agent Automation

### FR-341 AI-Assisted Agent Composition
The platform shall support **AI-assisted agent composition** where an authorized user can describe desired capabilities in natural language and receive a generated agent scaffold including tool selection, prompt configuration, policy suggestions, and context engineering profile.

### FR-342 Agent Blueprint Generation
The platform shall support generating **agent blueprints** from task descriptions, including:
- recommended model configuration;
- suggested tools and connectors;
- proposed policy attachments;
- estimated capability maturity level;
- context engineering profile recommendation.

### FR-343 Fleet Blueprint Generation
The platform shall support generating **fleet blueprints** from high-level mission descriptions, including:
- recommended topology;
- suggested member agent roles;
- orchestration pattern recommendation;
- delegation and escalation rules.

### FR-344 Agent Composition Validation
AI-generated agent compositions shall undergo the same **validation, policy checking, and certification readiness** workflows as manually created agents before they can be published.

### FR-345 Composition Audit Trail
Every AI-assisted composition decision shall produce an **audit trail** documenting:
- the original user request;
- the AI reasoning for each composition choice;
- alternatives considered and rejected;
- human overrides applied.

## 63. Scientific Discovery and Co-Scientist Patterns

### FR-346 Hypothesis Generation Workflows
The platform shall support workflows in which agents can **autonomously generate hypotheses** from provided data, literature, or prior experimental results.

### FR-347 Hypothesis Critique and Refinement
The platform shall support **multi-agent hypothesis critique** where dedicated reviewer agents evaluate generated hypotheses for:
- logical consistency;
- novelty;
- testability;
- alignment with existing evidence.

### FR-348 Tournament-Style Hypothesis Ranking
The platform shall support **Elo-based or tournament-style ranking** of competing hypotheses, where hypotheses are compared pairwise through simulated debates or structured evaluation criteria. Additionally, a **Hypothesis Proximity Graph** (computed from hypothesis embeddings in Qdrant, stored as edges in Neo4j) shall cluster similar hypotheses to identify redundant ideas and underrepresented areas of the hypothesis landscape. The generation agent shall be biased toward underrepresented clusters to improve landscape coverage. Inspired by Google AI Co-Scientist's Proximity Agent architecture.

### FR-349 Experiment Design Workflows
The platform shall support workflows where agents can **design experiments** to test ranked hypotheses, subject to governance, sandbox, and safety constraints.

### FR-350 Generate-Debate-Evolve Cycles
The platform shall support iterative **generate-debate-evolve** cycles where hypotheses are continuously generated, debated among agents, refined, and re-ranked until convergence or human review.

### FR-351 Discovery Evidence Provenance
All discovery workflow outputs shall carry **full provenance chains** linking hypotheses to the evidence, reasoning, and agents that produced them.

## 64. Privacy-Preserving Collaboration

### FR-352 Differential Privacy in Memory Operations
The platform shall support **differential privacy** mechanisms for memory operations where configured, adding controlled noise to aggregate queries over sensitive memory stores.

### FR-353 Privacy-Preserving Agent Collaboration
The platform shall support collaboration patterns where agents can **contribute to shared computations without exposing their individual data or memory contents** to other agents.

### FR-354 Data Minimization in Context Assembly
The context assembly pipeline shall support **data minimization policies** that ensure only the minimum necessary information is included in runtime context, particularly for cross-workspace or cross-tenant operations.

### FR-355 Privacy Impact Assessment Hooks
The platform shall support hooks for **privacy impact assessment** that can evaluate and flag context assemblies or memory operations that may violate configured privacy policies.

### FR-356 Anonymized Telemetry and Analytics
Where agent telemetry or analytics cross workspace or tenant boundaries, the platform shall support **anonymization or aggregation** before data leaves its original scope.

## 65. Marketplace Intelligence and Recommendation

### FR-357 Agent Recommendation Engine
The marketplace shall support an **intelligent recommendation engine** that suggests agents based on:
- the user's task description;
- historical usage patterns;
- workspace context and goals;
- collaboration fit with currently active agents;
- cost-performance profile preferences.

### FR-358 Automated Agent Matching
The platform shall support **automated agent matching** for workspace goals and workflow steps, where the system proposes the most suitable agent based on capability, trust, availability, and cost.

### FR-359 Usage-Based Quality Signals
The marketplace shall aggregate **usage-based quality signals** including:
- invocation success rate;
- average response quality scores;
- self-correction frequency;
- user satisfaction ratings;
- certification compliance rate.

### FR-360 Marketplace Trending and Popular Agents
The marketplace shall surface **trending and popular agents** based on recent usage patterns, satisfaction scores, and community feedback.

### FR-361 Contextual Discovery Suggestions
The marketplace shall offer **contextual discovery suggestions** within workbenches, conversations, and workflow editors, recommending agents that could assist with the current task.

## 66. Fleet-Level Learning and Adaptation

### FR-362 Fleet Performance Profiles
The platform shall maintain **fleet-level performance profiles** that aggregate individual agent metrics into fleet-wide indicators of effectiveness, reliability, and efficiency.

### FR-363 Fleet Performance Tournaments
The platform shall support **fleet-level performance tournaments** where alternative fleet configurations, topologies, or member compositions can be compared against standardized benchmarks.

### FR-364 Fleet Behavioral Adaptation
The platform shall support **fleet-level behavioral adaptation** where orchestration rules, delegation patterns, or escalation thresholds are adjusted based on observed fleet performance data.

### FR-365 Cross-Fleet Knowledge Transfer
The platform shall support **controlled knowledge transfer** between fleets through approved pattern promotion, shared memory namespaces, or cross-fleet trajectory sharing.

### FR-366 Fleet Personality Profiles
The platform shall support configurable **fleet personality profiles** that define:
- communication style between members;
- decision-making speed vs. thoroughness tradeoff;
- risk tolerance;
- escalation sensitivity;
- autonomy level.

## 67. Advanced Communication Patterns

### FR-367 Broadcast and Multicast Messaging
The platform shall support **broadcast** (one-to-all) and **multicast** (one-to-many) messaging patterns within fleets and across workspace-scoped agent groups.

### FR-368 Conversation Branching and Merging
The platform shall support **conversation branching** where a conversation can fork into parallel exploration threads and later **merge** results back into the primary conversation.

### FR-369 Acknowledgment and Delivery Tracking
The platform shall support **message acknowledgment and delivery tracking** for agent-to-agent communications, enabling reliable coordination and timeout-based escalation.

### FR-370 Structured Negotiation Protocols
The platform shall support **structured negotiation protocols** where agents can propose, counter-propose, accept, or reject collaborative task assignments through typed message exchanges.

### FR-371 Priority-Aware Message Routing
The platform shall support **priority-aware message routing** where high-priority messages can preempt lower-priority ones in agent processing queues.

### FR-372 Communication Pattern Templates
The platform shall support reusable **communication pattern templates** for common interaction styles such as request-response, publish-subscribe, scatter-gather, and saga coordination.

## 68. Agent Simulation and Digital Twin Mode

### FR-373 Agent Simulation Mode
The platform shall support a **simulation mode** where agents can execute against synthetic or historical data without triggering real external actions, enabling what-if analysis and behavioral prediction.

### FR-374 Fleet Simulation
The platform shall support **fleet-level simulation** where entire fleet topologies can be tested against simulated workloads, failure scenarios, and coordination challenges.

### FR-375 Agent Digital Twins
The platform shall support **digital twin** representations of production agents that mirror their configuration, context, and behavioral history, enabling safe experimentation and comparison.

### FR-376 Simulation Comparison Analytics
The platform shall provide **simulation comparison analytics** that contrast simulated outcomes against production reality or alternative configurations.

### FR-377 Behavioral Prediction
The platform shall support **behavioral prediction** capabilities where the system can forecast likely agent or fleet behavior for a given scenario based on historical patterns and current configuration.

### FR-378 Simulation Governance
Simulation executions shall be subject to governance policies including:
- resource and cost limits for simulations;
- data access restrictions in simulation mode;
- audit logging of simulation runs;
- clear separation between simulation artifacts and production artifacts.

## 69. AgentOps and Behavioral Lifecycle

### FR-379 Behavioral Versioning
The platform shall support **behavioral versioning** that tracks not only code and configuration changes but also behavioral changes as observed through evaluation metrics, reasoning patterns, and output quality over time.

### FR-380 Governance-Aware CI/CD
The platform shall support **governance-aware CI/CD pipelines** where agent deployments are gated by:
- policy conformance checks;
- evaluation suite results;
- certification status;
- trust-tier qualification;
- behavioral regression tests.

### FR-381 Canary Deployment for Agents
The platform shall support **canary deployment** patterns for agents where new revisions receive a controlled percentage of traffic and are automatically promoted or rolled back based on performance thresholds.

### FR-382 Behavioral Regression Detection
The platform shall detect and alert on **behavioral regressions** when a new agent revision produces statistically worse outcomes, higher costs, or more safety violations than the previous revision.

### FR-383 Agent Health Scoring
The platform shall compute and maintain an **agent health score** combining:
- uptime and availability;
- response quality metrics;
- self-correction effectiveness;
- safety violation frequency;
- cost efficiency;
- user satisfaction signals.

### FR-384 Automated Retirement and Replacement
The platform shall support **automated agent retirement** workflows triggered by sustained health degradation, certification expiry, or policy non-compliance, with automatic replacement by designated successors.

## 70. Semantic and Behavioral Testing

### FR-385 Semantic Similarity Testing
The platform shall support **semantic similarity testing** where agent outputs are evaluated against reference outputs using embedding-based similarity scoring rather than exact string matching.

### FR-386 Adversarial Testing Suites
The platform shall support **adversarial testing suites** that deliberately probe agents with:
- ambiguous inputs;
- edge cases;
- prompt injection attempts;
- contradictory instructions;
- malformed data;
- resource exhaustion scenarios.

### FR-387 Statistical Robustness Testing
The platform shall support **statistical robustness testing** where the same test is executed multiple times and outcomes are evaluated as distributions rather than single pass/fail verdicts.

### FR-388 Behavioral Drift Detection
The platform shall support **behavioral drift detection** that monitors agent outputs over time and alerts when response patterns deviate significantly from established baselines.

### FR-389 Multi-Agent Coordination Testing
The platform shall support **multi-agent coordination testing** that evaluates:
- collective task completion quality;
- inter-agent communication coherence;
- emergent coordination behavior;
- conflict resolution effectiveness;
- overall fleet goal achievement.

### FR-390 Human-AI Collaborative Grading
The platform shall support **human-AI collaborative grading** where automated evaluators generate initial scores and human reviewers can override, confirm, or adjust grades with feedback that improves the automated evaluators over time.

### FR-391 Test Case Generation
The platform shall support **AI-assisted test case generation** where the system can automatically generate test scenarios, edge cases, and adversarial inputs based on agent configuration and declared capabilities.


## 72. MCP (Model Context Protocol) Full Integration

### FR-392 MCP Server Mode
The platform shall expose registered tools as MCP-compatible endpoints, implementing the MCP server protocol so that external MCP clients can dynamically discover and invoke platform tools. The server shall expose three MCP resource types: tools (executable functions), resources (data endpoints), and prompts (interaction templates).

### FR-393 MCP Client Mode
The platform shall support connecting to external MCP servers as tool sources. Agent configuration shall include an `mcp_servers` list specifying external MCP server URLs. At runtime, the platform shall discover available tools from each configured MCP server and make them available to the agent through the standard tool gateway, subject to visibility and policy enforcement.

### FR-394 MCP Tool Policy Integration
All MCP tool invocations — both inbound (external clients using platform tools) and outbound (platform agents using external MCP tools) — shall pass through the tool gateway with the same policy validation, visibility checks, budget tracking, and output sanitization as native tools.

### FR-395 MCP Resource and Prompt Exposure
The platform shall support exposing agent context sources as MCP resources (read-only data endpoints) and agent interaction patterns as MCP prompts (templated interaction starters), enabling external MCP clients to access platform knowledge bases and use pre-defined agent interaction patterns.

### FR-396 MCP Error Handling
MCP interactions shall implement structured error handling: tool execution failures, unavailable servers, invalid requests, and authentication failures shall be communicated back to the requesting agent in a format it can interpret and act upon (retry, fallback, or escalation).

## 73. A2A Protocol Enhancement

### FR-397 Agent Card Auto-Generation
The platform shall auto-generate A2A-compliant Agent Cards (JSON) from registry metadata for every published agent. The Agent Card shall include: agent name (FQN), description (from purpose), endpoint URL, version, capabilities (streaming, push notifications, state transition history), authentication schemes, default input/output modes, and skills (derived from agent capabilities and tool bindings).

### FR-398 A2A Task Lifecycle
A2A task requests shall follow the standard lifecycle: `submitted` → `working` → `input-required` → `completed` / `failed` / `canceled`. Each state transition shall be logged and observable. The `input-required` state shall trigger the Attention pattern to notify the requesting client.

### FR-399 A2A Streaming and Push Notifications
The A2A gateway shall support Server-Sent Events (SSE) for streaming task progress updates to external clients. Optionally, push notification endpoints may be configured for asynchronous completion callbacks.

### FR-400 A2A Multi-Turn Conversations
A2A interactions shall support multi-turn conversations where the external client and platform agent exchange multiple messages within a single task context. Task state and conversation history shall be maintained across turns.

## 74. Checkpoint and Rollback Pattern

### FR-401 Execution Checkpoint Creation
The execution engine shall support explicit checkpoint creation at configurable points during workflow execution. A checkpoint captures the complete execution state: all completed step outputs, current context, reasoning traces, accumulated costs, and pending step queue. Checkpoints are stored as immutable snapshots in the execution journal.

### FR-402 Checkpoint-Based Rollback
When an execution encounters a failure or undesirable outcome, the platform shall support rolling back to any previous checkpoint. Rollback restores the execution state to the checkpoint and allows re-execution from that point with modified inputs, different agent selection, or adjusted parameters. All rollback actions are recorded in the audit trail.

### FR-403 Automatic Checkpoint Policies
Workflows shall support automatic checkpoint policies: checkpoint before every tool invocation, checkpoint before external agent calls, checkpoint at branch points, or checkpoint at configurable intervals. The default policy shall be checkpoint before every tool invocation.

## 75. Advanced Reasoning Enhancements

### FR-404 Chain of Debates (CoD)
The platform shall support Chain of Debates as a reasoning technique where multiple agents engage in structured debate rounds to collaboratively reason toward a solution. Each debate round consists of: position statement by each agent, critique by opposing agents, rebuttal, and synthesis. Debate rounds continue until consensus or a configurable round limit is exceeded. Debate transcripts are persisted as reasoning artifacts.

### FR-405 Scaling Inference Law Support
The platform shall support configurable inference-time compute allocation for reasoning tasks. Agents or workflows shall be able to specify the amount of "thinking time" (computational budget) allocated to a reasoning step. Higher compute allocation enables more deliberate reasoning (more CoT steps, wider ToT branching, more self-correction iterations) at the cost of increased latency and token usage.

### FR-406 ReAct Framework Integration
The platform shall natively support the ReAct (Reasoning + Acting) pattern where agents alternate between reasoning steps (thinking about what to do) and action steps (executing tools, querying data). Each ReAct cycle shall be recorded: the reasoning step (thought), the action taken (tool call), and the observation (tool result).

### FR-407 Reasoning Trace Structured Export
Reasoning traces (CoT, ToT, ReAct, CoD) shall be exportable in a structured format (JSON) capturing: each reasoning step with timestamp, the reasoning technique used, branch/debate identifiers, tool calls made during reasoning, quality scores per step, total token consumption, and compute budget utilization.

## 76. Agent Self-Improvement and Adaptation

### FR-408 Agent Configuration Adaptation Pipeline
The platform shall support a formal adaptation pipeline where agent performance is evaluated, improvement opportunities are identified from behavioral data, and configuration adjustments (approach text, model parameters, context engineering profile, tool selection) are proposed as a new agent revision candidate. Proposed changes require human approval before promotion.

### FR-409 Experience-Based Knowledge Accumulation
Agents shall accumulate knowledge from successful executions into their long-term memory. Successful patterns (tool sequences, reasoning strategies, context compositions) that consistently produce high-quality results shall be flagged for promotion to the agent's knowledge base, subject to the pattern promotion workflow (FR-160).

### FR-410 Self-Correction History as Learning Input
The self-correction service shall feed convergence data (which correction strategies work, which fail, average iterations to convergence per agent) back into the adaptation pipeline. Agents that consistently require many self-correction iterations may have their approach or model configuration adjusted.

## 77. Trajectory-Based Evaluation

### FR-411 Trajectory Evaluation as a Scorer Type
The evaluation framework shall support trajectory evaluation as a distinct scorer type. The TrajectoryScorer receives the full execution journal, reasoning traces, and task plan for an execution. It evaluates: path efficiency (steps taken vs estimated optimal), tool call appropriateness, reasoning coherence, and cost-effectiveness.

### FR-412 Trajectory Comparison Methods
Trajectory evaluation shall support multiple comparison methods: exact match, in-order match (correct actions in order, allowing extra steps), any-order match, precision, and recall. The comparison method is configurable per evaluation suite.

### FR-413 Multi-Agent Trajectory Evaluation
For multi-agent executions, trajectory evaluation shall assess: cooperation effectiveness (correct information handoff between agents), plan adherence, agent selection quality (right agent for each subtask), and scalability impact (did adding agents improve or degrade performance).

## 78. LLM-as-Judge Formalization

### FR-414 LLM-as-Judge Configurable Rubrics
The evaluation framework shall support LLM-as-Judge with configurable rubrics. Each rubric defines: criteria (correctness, helpfulness, safety, style, faithfulness), scale per criterion (e.g., 1-5), examples of each score level, and structured output format. Built-in rubric templates shall be provided. Custom rubrics shall be definable per evaluation suite.

### FR-415 LLM-as-Judge Model Selection
The judge model may be different from the agent's model. The evaluation suite configuration shall specify which model to use as the judge, allowing a more capable or specialized model to evaluate outputs.

### FR-416 LLM-as-Judge Calibration
LLM-as-Judge evaluations shall support calibration runs: the same judgment is executed N times (configurable, default 3), and the score distribution (mean, stddev, percentiles) is reported to quantify the reliability of the judge's assessment.

## 79. Context Engineering as Agent Capability Differentiator

### FR-417 Context Engineering as Core Agent Skill
Context engineering shall be recognized as the core skill that differentiates agent capability levels: Level 0 (no context engineering), Level 1 (tool-assisted but minimal curation), Level 2 (active context curation — selecting, packaging, compressing information per step), Level 3 (cross-agent context engineering in collaborative systems). Agent maturity assessment (FR-315) shall incorporate context engineering proficiency.

### FR-418 Context Quality as Performance Predictor
The platform shall track the correlation between context quality scores (FR-309) and agent output quality. Context quality shall be treated as a leading indicator of agent performance, with analytics showing: context quality trends per agent, correlation with execution success rate, and recommendations for context profile optimization.

## 80. Agent Contract Model

### FR-419 Formalized Agent Agreements
The platform shall support defining formalized agent agreements (contracts) that specify: the task scope, expected outputs, quality thresholds, time constraints, cost limits, escalation conditions, and success criteria. These contracts are machine-readable and enforceable at runtime, extending the policy framework (FR-050) with task-specific terms.

### FR-420 Contract Compliance Monitoring
During execution, the platform shall monitor agent behavior against its active contract. Deviations from contract terms (exceeding cost limits, failing quality thresholds, missing time constraints) shall trigger: warning alerts, automatic throttling, escalation to human, or execution termination, depending on the contract's enforcement policy.

### FR-421 Contract-Based Evaluation
Evaluation suites shall support contract-based evaluation where an agent is assessed against the terms of its contract rather than (or in addition to) generic quality metrics. Contract compliance rate shall be a first-class KPI.



## 81. Agent FQN (Fully Qualified Name) System

### FR-422 Agent Namespace Management
The platform shall support a namespace system for agent identity. Each namespace shall be unique across the platform and represent an organizational boundary (department, team, or external organization). Namespaces shall be created via API and UI, associated with one or more workspaces, and governed by ownership and administrative permissions.

### FR-423 Fully Qualified Name (FQN) as Primary Agent Identity
Every agent shall have a Fully Qualified Name composed of `{namespace}:{local_name}` (e.g., `finance-ops:kyc-verifier`). The FQN shall be unique across the platform and serve as the primary scheme for discovery, policy attachment, certification binding, and visibility configuration. Within a namespace, local names shall be unique. Each FQN may have multiple running instances, each with a UUID.

### FR-424 FQN-Based Discovery and Pattern Matching
Agent discovery shall support FQN pattern matching using exact match or namespace-level wildcards (e.g., `finance-ops:*`). Discovery results shall be filtered by the requesting agent's visibility configuration (FR-425).

## 82. Zero-Trust Default Visibility

### FR-425 Zero-Trust Default Agent Visibility
By default, a newly registered agent shall see **zero agents and zero tools**. Visibility must be explicitly granted through the agent's visibility configuration, which lists allowed agent FQN patterns and tool FQN patterns. This zero-trust posture enforces the principle of least privilege for all agent-to-agent interactions.

### FR-426 Workspace-Level Visibility Grants
Workspaces shall support workspace-wide visibility grants that apply to all agents within the workspace. These grants supplement (not replace) per-agent visibility configurations. Agents see the union of their per-agent visibility and their workspace's grants.

### FR-427 Visibility Enforcement at Discovery Time
Visibility filtering shall be enforced at the registry query level, not as a post-filter. An agent cannot discover the existence of agents or tools outside its visibility scope—unauthorized entities are invisible, not just inaccessible.

## 83. Goal ID (GID) and Workspace Goal Management

### FR-428 Goal ID as First-Class Correlation Dimension
Goal-oriented workspaces shall use a Goal ID (GID) as the primary tracking dimension for all activity related to a shared objective. The GID shall be a first-class field in the correlation context alongside workspace_id, conversation_id, interaction_id, execution_id, and fleet_id. All messages, interactions, and executions triggered by a workspace goal shall carry the GID.

### FR-429 Workspace Goal Message Model
Workspace goals shall support a structured message model: each message carries workspace_id, goal_id, message_id, timestamp, participant_id (agent FQN or user_id), content, and optionally an interaction_id linking to a triggered interaction chain. Goal messages form the super-context that the context engineering service pulls for any agent acting within that goal.

### FR-430 Agent Response Decision in Workspaces
When a message is posted to a workspace goal, each subscribed agent shall independently decide whether to respond, using configurable decision mechanisms: LLM-based relevance assessment, allowlist/blocklist by sender FQN, keyword matching, cosine similarity of message embedding against the agent's purpose, or "best match" mode where only the highest-relevance agent responds. The decision and its rationale shall be logged for observability.

### FR-431 Goal Lifecycle States
Workspace goals shall have a defined lifecycle: `READY` (created, awaiting first message) → `WORKING` (at least one message present, agents may be processing) → `COMPLETE` (manually set by authorized user or after configurable timeout). In the COMPLETE state, no new messages may be added and no processing occurs.

## 84. Agent Attention Pattern

### FR-432 Agent-Initiated Attention Requests
Agents shall signal urgent need for human input or peer assistance via AttentionRequest events published to a dedicated channel (`interaction.attention` Kafka topic). Attention requests carry: source_agent (FQN), target (agent FQN or user_id), urgency_level (low/medium/high/critical), context_summary, related_execution_id, related_interaction_id, related_goal_id. The attention channel is distinct from operational alerts—it is agent-initiated and context-specific.

### FR-433 Configurable User Alert Settings
Users shall configure their alert preferences for interactions they create. Configurable settings include: which interaction state transitions generate alerts (e.g., working→pending, any→complete, any→failed), alert delivery method (in-app notification, email, webhook), and per-interaction overrides of default settings. Alerts are generated by the registry when state transitions match the user's preferences.

## 85. Judge and Enforcer Agent Roles

### FR-434 Judge Agent Role
The platform shall support `judge` as a formal agent role type. Judge agents receive signals from observer agents and evaluate them against established rules, standards, or ethical guidelines. Judges emit structured verdicts: COMPLIANT, WARNING, VIOLATION, or ESCALATE_TO_HUMAN, with the policy evaluated, evidence considered, rationale, and recommended enforcement action.

### FR-435 Enforcer Agent Role
The platform shall support `enforcer` as a formal agent role type. Enforcers receive verdicts from judge agents and execute enforcement actions: block the action, quarantine the agent (stop its runtime), notify a human operator, revoke a certification, trigger recertification, or log and continue. All enforcement actions are recorded in the audit trail with full policy basis.

### FR-436 Observer → Judge → Enforcer Pipeline Configuration
Fleets and workspaces shall support configurable governance chains specifying: which observer agents feed signals, which judge agents evaluate, which enforcer agents act, and which policies the judge evaluates against. Default chains shall be assigned on fleet/workspace creation.

## 86. Secrets Isolation from LLM

### FR-437 Secrets Never in LLM Context Window
The platform shall guarantee that secrets (API keys, database credentials, tokens, passwords) never enter the LLM's context window. Secrets shall be resolved by the Runtime Controller or tool gateway and injected directly into tool execution code, bypassing the agent's LLM entirely. The LLM receives only secret reference names, never values.

### FR-438 Tool Output Secret Sanitization
Before tool output is returned to the LLM context, the tool gateway shall scan for known secret patterns (API keys, JWT tokens, connection strings, password strings) and redact them with `[REDACTED:secret_type]`. Redaction events shall be logged for security audit.

## 87. Natural-Language Agent Purpose and Approach

### FR-439 Mandatory Natural-Language Purpose Declaration
Every agent shall have a mandatory `purpose` field: an explicit, detailed, natural-language definition of what the agent is designed to do. The purpose must be operational and specific—not vague. It must be intelligible to humans AND interpretable by LLMs. Vague purposes like "optimize user experience" shall be flagged during validation. The purpose is the baseline for governance, certification, and deviation detection.

### FR-440 Natural-Language Approach Field
Every agent may have an optional `approach` field: a step-by-step natural-language strategy describing how the agent fulfills its purpose. The approach is directly interpretable by the agent's LLM and is included in the system prompt context by the context engineering service.

## 88. Enterprise Identity and Reliability

### FR-441 IBOR (Identity Book of Record) Integration
The platform shall integrate with enterprise Identity Book of Record (IBOR) systems for agent identity management. Agent FQNs, roles, and permissions shall be synchronizable with the organization's identity infrastructure (LDAP, AD, Keycloak, Okta). This ensures agents are subject to the same lifecycle controls as human users.

### FR-442 Five-Nines Reliability Target
The platform shall target "five-nines" (99.999%) accuracy for critical agent operations, measured as: correct task completion rate, correct tool selection rate, and correct policy compliance rate. This target applies to certified production agents. Reliability metrics shall be tracked per agent and per fleet in ClickHouse and visible on the operator dashboard.

## 89. Runtime Warm Pool and Decommissioning

### FR-443 Runtime Warm Pool Management
The Runtime Controller shall maintain a configurable warm pool of pre-initialized runtime pods per workspace or agent type. Warm pool reduces agent launch latency from cold-start (~10s) to <2 seconds. Warm pods are recycled after a configurable idle timeout. Pool size is configurable per workspace. Utilization metrics shall be reported to the operator dashboard.

### FR-444 Agent Decommissioning Lifecycle
The platform shall support formal agent decommissioning as the final lifecycle phase. Decommissioning shall: mark the agent as decommissioned in the registry; shut down all running instances; remove from marketplace discovery; preserve configuration, history, and audit trail for compliance; and prevent re-activation without explicit re-registration. Decommissioning is distinct from deletion—data is retained.

## 90. Certification Enhancements

### FR-445 Third-Party Certification Support
The platform shall support third-party certification where external certifiers (compliance auditors, regulatory bodies, industry partners) can: register as certifiers; access agent profiles and test environments with scoped permissions; issue certifications recorded alongside internal certifications; have their certifications visible in marketplace trust signals.

### FR-446 Ongoing Surveillance and Periodic Reassessment
Certification shall include an ongoing surveillance program with: periodic reassessments on a configurable schedule (e.g., quarterly); automated compliance checks that run continuously; immediate recertification triggers when material changes are detected (revision change, policy change, behavioral regression); and certification expiry with configurable duration and renewal workflow.


## 91. S3-Compatible Object Storage

### FR-447 Provider-Agnostic S3 Object Storage
The platform shall use S3-compatible object storage as the canonical store for all binary and large artifacts, including: agent packages, execution artifacts, reasoning traces, sandbox outputs, evidence bundles, simulation artifacts, and backups. The platform shall access object storage exclusively through standard S3 API operations (PutObject, GetObject, DeleteObject, ListObjects, HeadBucket) and shall not depend on any vendor-specific extension, admin API, or operator. Any S3-compatible endpoint shall work without code changes — configuration (endpoint URL, region, access key, secret key, bucket prefix, addressing style) shall be sufficient to switch providers. Self-hosted MinIO shall remain available as an optional development and lab convenience but shall not be required for production deployments.

## 92. OAuth2 Social Login (Google and GitHub)

### FR-448 OAuth2/OIDC Social Login Framework
The platform shall support user authentication via external OAuth2/OIDC identity providers as an alternative to local username/password authentication. The framework shall: support multiple concurrent providers (each independently enabled/disabled by administrators); map external identity claims (email, name, avatar, groups) to platform user profiles; handle first-login auto-provisioning (create platform user on first successful OAuth login, subject to tenant policy); support account linking (existing local user can link their account to one or more OAuth providers); and maintain a clear separation between the OAuth token (used only for authentication) and the platform session token (used for all subsequent API access).

### FR-449 Google OAuth2 Login
The platform shall support Google as an OAuth2 identity provider. Configuration shall include: Google OAuth2 client ID and client secret (stored in vault, never in config files); authorized redirect URI; optional restriction to specific Google Workspace domains (e.g., only `@company.com` addresses allowed); and optional mapping of Google Workspace groups to platform workspace roles. The login flow shall use the standard Authorization Code Grant with PKCE.

### FR-450 GitHub OAuth2 Login
The platform shall support GitHub as an OAuth2 identity provider. Configuration shall include: GitHub OAuth2 client ID and client secret (stored in vault); authorized redirect URI; optional restriction to specific GitHub organizations (e.g., only members of `my-org` allowed); and optional mapping of GitHub teams to platform workspace roles. The login flow shall use the standard Authorization Code Grant.

### FR-451 Social Login Administration
Administrators shall be able to: enable or disable each social login provider independently; configure provider-specific settings (client ID, client secret, domain/org restrictions) via API and UI; enforce that social login users must also enroll in MFA (configurable per provider); set the default role for auto-provisioned social login users; and view which users authenticated via which provider in the audit log.

### FR-452 Social Login Security Controls
Social login shall enforce: CSRF protection via the OAuth2 `state` parameter; PKCE (Proof Key for Code Exchange) for all authorization code flows; token validation (ID token signature verification, issuer verification, audience verification, expiry check); rate limiting on the callback endpoint to prevent abuse; and audit logging of all social login attempts (success and failure) with provider name and external identity reference.

## 93. End-to-End Testing on Kubernetes (kind)

### FR-453 Ephemeral Kind-Based E2E Test Environment
The platform shall provide an ephemeral end-to-end test environment that runs on a local Kubernetes-in-Docker (kind) cluster. The environment shall: be provisionable with a single command (target: `make e2e-up` or equivalent) in under 10 minutes on a developer laptop (16GB RAM); deploy the complete platform stack including all control plane, satellite services, data stores, and frontend; use the same Helm charts used in production deployments (no test-only bypass paths); be fully destroyable (`make e2e-down`) leaving no artifacts on the host; support multiple parallel clusters on the same host via unique cluster names for CI parallelism.

### FR-454 E2E Test Stack Composition
The E2E environment shall deploy all platform data stores and services using kind-optimized configurations: PostgreSQL (single-instance, in-cluster), Redis (single-instance, in-cluster), Kafka (single-broker with KRaft, no Zookeeper), Qdrant (single-node), Neo4j (single-node), ClickHouse (single-node), OpenSearch (single-node), S3-compatible object storage (MinIO container for E2E convenience, configured via the same generic S3 client as production), Python control plane (all profiles), Go satellite services (runtime controller, reasoning engine, sandbox manager), frontend (Next.js in dev mode). All resource requests and limits shall be scaled down for developer laptop constraints while preserving production-equivalent behavior.

### FR-455 E2E Test Data Seeding
The E2E environment shall support deterministic test data seeding including: default admin user with known credentials; test workspaces and namespaces; representative agents covering all role types (executor, planner, orchestrator, observer, judge, enforcer); test tools (mock HTTP tools, mock code-execution tools); test fleets; test policies; pre-created certification chains; sample workspace goals; mock LLM provider with deterministic responses (for tests that must not hit real LLMs). Seeding shall be idempotent and resettable between test runs.

### FR-456 E2E Test Suite Coverage by Bounded Context
The platform shall maintain E2E test suites organized by bounded context, covering at minimum: authentication (local, MFA, Google OAuth, GitHub OAuth, session lifecycle); registry and FQN (namespace CRUD, agent registration with FQN, FQN resolution, pattern discovery, visibility filtering, zero-trust default); policies and tool gateway (policy evaluation, tool access control, output sanitization); trust (SafetyPreScreener, certification workflow, contract compliance, third-party certifier, ongoing surveillance, decommissioning); governance (Observer → Judge → Enforcer pipeline, verdict issuance, enforcement execution); interactions (conversation lifecycle, workspace goals with GID, agent response decision, attention requests, user alerts); workflows (execution, checkpoints, rollback, re-prioritization); fleets (orchestration, coordination); reasoning (DIRECT, CoT, ToT, ReAct, CoD, self-correction, compute_budget enforcement); evaluation (TrajectoryScorer, LLM-as-Judge with calibration, A/B testing); AgentOps (adaptation pipeline proposal/approval); scientific discovery (hypothesis proximity graph); A2A (Agent Card generation, server mode, client mode, SSE streaming); MCP (client discovery, server exposure); runtime controller (warm pool, secrets injection); IBOR integration; generic S3 storage (upload, download, lifecycle).

### FR-457 E2E Test Framework and Execution
E2E tests shall be written using **pytest** with an async test fixture that provides a preconfigured HTTP client, WebSocket client, and database session targeting the kind cluster. Tests shall: be runnable individually or by suite; produce JUnit XML output for CI; produce HTML reports with step-by-step trace; capture platform logs, Kafka events, and database state on failure; execute in deterministic order within a suite; support parallel execution across suites when isolated. The test harness shall provide reusable fixtures for common setup (create workspace, register agent, launch execution) to keep test code focused on the behavior being verified.

### FR-458 E2E CI/CD Integration
The E2E test suite shall run in CI on every pull request and nightly on main. CI shall: provision a fresh kind cluster per run; execute all E2E suites; block merges on test failure; publish test reports as build artifacts; retain failure logs and state dumps for 30 days; support manual re-run on transient infrastructure failures with automatic issue creation after three consecutive failures.

### FR-459 E2E Chaos and Failure Scenarios
The E2E test suite shall include chaos scenarios that deliberately inject failures to verify platform resilience: killing agent runtime pods mid-execution (verify checkpoint recovery), killing reasoning engine pod (verify reconnection and replay), killing Kafka broker briefly (verify producer retry and no event loss), revoking S3 credentials (verify clear error propagation), network partition between control plane and data stores (verify circuit breaker behavior), policy engine timeout (verify fail-closed default). Each chaos scenario shall have a clear expected recovery behavior and assertion.

### FR-460 E2E Performance Smoke Tests
The E2E test suite shall include lightweight performance smoke tests: agent launch latency (target <2s warm pool, <10s cold), simple execution round-trip (target <5s for trivial agent), concurrent execution throughput (target 10 simultaneous executions without queue backing up), reasoning trace capture overhead (target <50ms added per step). These are smoke-level checks, not full load tests — their purpose is to detect performance regressions on every PR, not to benchmark production.

## 94. User Journey E2E Tests

### FR-461 User Journey Test Suite
The platform shall maintain E2E test suites organized by user journey (in addition to the bounded-context suites in FR-456). Each journey simulates a complete user workflow from login through a multi-step business process, crossing at least 4 bounded contexts per journey. Journeys shall cover the following personas and workflows: Platform Administrator (bootstrap to production-ready), Agent Creator (idea to published agent), Consumer (discover, execute, track), Workspace Collaborator (multi-agent goal solving), Trust Officer (policy to enforcement), Operator (monitor, diagnose, recover), Evaluator (quality assessment and improvement loop), External Integrator (A2A and MCP), Research Scientist (hypothesis to experiment), Privacy Officer (data subject request lifecycle), Security Officer (SBOM, vulnerability, rotation workflows), Finance Owner (budget setup, chargeback, anomaly response), SRE (multi-region failover and maintenance), Model Steward (model catalog approval, fallback verification), Accessibility User (screen-reader and keyboard-only flows), Compliance Auditor (hash-chain verification, audit export), and Dashboard Consumer (log-metric-trace correlation).

### FR-462 Journey Test Assertions at Every Boundary Crossing
Each journey test shall include explicit assertions at every bounded-context boundary crossing — not just at the start and end. For example, the Consumer journey shall assert: login response, marketplace search results, conversation creation, execution creation, WebSocket event reception, reasoning trace content, result structure, alert delivery, and conversation history. Each journey shall have a minimum of 15 assertion points.

### FR-463 Journey Test Independence and Parallelism
Journey tests shall be fully independent: each journey creates its own workspace, namespaces, agents, and test data. No journey shall depend on state created by another journey. All 9 journeys shall be runnable in parallel on the same kind cluster without interference. Journey-specific cleanup shall be performed after each test.

### FR-464 Journey Test Narrative Output
Journey tests shall produce human-readable narrative output describing each step and its result, beyond standard pass/fail. The HTML test report shall display each journey as a sequence of named steps with status indicators, making it possible for a non-developer to understand what the platform did and where it failed.

### FR-465 Journey Test OAuth Flow Coverage
Journey tests shall exercise the full OAuth2 social login flow with mock identity providers. The Creator journey shall authenticate via GitHub OAuth, the Consumer journey via Google OAuth, and the Admin journey via local auth with MFA. Mock OAuth providers shall simulate the authorization code flow with PKCE, token exchange, and ID token validation without hitting real Google or GitHub servers.

## 95. Data Protection and Privacy Regulation Compliance

### FR-466 Data Subject Rights (GDPR / CCPA)
The platform shall provide mechanisms to fulfill data subject rights under GDPR, CCPA, and equivalent regulations. Supported rights shall include: access (export all personal data about a subject), rectification (correct inaccurate data), erasure (right to be forgotten — hard-delete user data and cascade to all derived artifacts), restriction of processing (suspend automated processing), portability (export in machine-readable format), and objection to automated decision-making. All rights shall be exposable via admin API and UI.

### FR-467 User Data Deletion and Cascade
When a user's data is deleted via a right-to-be-forgotten request, the platform shall cascade the deletion to: user profile and credentials; sessions and OAuth links; authored conversations (anonymized or deleted per policy); authored agents' attribution (anonymized); evaluation reviewer comments (anonymized); audit trail entries that contain PII (anonymized, preserving audit integrity via tombstone records). The deletion shall be logged as a tombstone record with a cryptographic hash proving completion. Referenced artifacts outside the platform (external A2A calls, MCP invocations) shall be flagged for manual follow-up.

### FR-468 Data Residency and Regional Deployment
The platform shall support data residency constraints. Administrators shall be able to configure: the deployment region for each data store (PostgreSQL, Qdrant, Neo4j, ClickHouse, OpenSearch, S3 storage); per-workspace region restrictions (all data for a workspace resides in its configured region); cross-region transfer blocks (reject A2A calls or MCP invocations that would move data across restricted boundaries). Region configuration shall be auditable and enforced at query-time, not just at installation.

### FR-469 Sensitive Data Classification and DLP
The platform shall support classification of data as sensitive (PII, PHI, financial, confidential) via metadata tags. A Data Loss Prevention (DLP) stage shall scan: outbound agent responses, tool invocation payloads, log events, artifact persistence, and marketplace publications. DLP rules shall be configurable per organization. Detected sensitive data shall be redacted, blocked, or flagged for review based on policy. DLP events shall be logged and visible on the operator dashboard.

### FR-470 Privacy Impact Assessment Workflow
The platform shall support formal Privacy Impact Assessments (PIAs) for agents, workspaces, and workflows that process sensitive data. PIA workflow shall include: identification of data categories processed, legal basis for processing, retention policy, third-party transfers, risks and mitigations, and approval by designated privacy officer. PIAs shall be linked to agents and reviewable in the trust workbench.

## 96. Security Compliance and Supply Chain

### FR-471 Software Bill of Materials (SBOM)
The platform shall generate and publish a Software Bill of Materials (SBOM) for every release in SPDX and CycloneDX formats. The SBOM shall include: all direct and transitive dependencies (Python, Go, npm, container images), their versions, licenses, and known CVE references at build time. SBOMs shall be published as release artifacts and retained for the lifetime of the release.

### FR-472 Vulnerability Scanning and Patch Management
The platform build pipeline shall include vulnerability scanning of: container images (Trivy, Grype), dependencies (npm audit, pip-audit, govulncheck), static code analysis (Bandit, gosec, ESLint security rules), and Helm chart configurations. Scan results shall be published per build. CVEs above a configured severity threshold shall block the release. A patch management workflow shall track CVEs affecting deployed versions and provide remediation guidance with severity-based SLAs.

### FR-473 Penetration Testing and Red Team Exercises
The platform shall support scheduled penetration testing and red team exercises. The trust subsystem shall track: pen test schedules, findings, remediation status, and attestation reports. Critical findings shall trigger immediate certification review. Red team reports shall be available to auditors under appropriate RBAC controls.

### FR-474 Secret and Credential Rotation
The platform shall support automated secret rotation for: database credentials, Kafka credentials, S3 credentials, OAuth provider client secrets, model provider API keys, and internal service mTLS certificates. Rotation frequency shall be configurable per secret type with safe defaults (90 days maximum for long-lived secrets). Rotation shall be zero-downtime via dual-credential windows.

### FR-475 Just-in-Time Credentials for Privileged Operations
Privileged operations (HostOps broker actions, cross-tenant admin tasks, emergency production access) shall use Just-in-Time (JIT) credentials that are: issued on approval, scoped to a specific operation, time-bounded (maximum 1 hour by default), and automatically revoked. JIT issuance, use, and revocation shall be audited in detail.

### FR-476 Audit Log Immutability
Audit log entries shall be written to append-only storage with cryptographic chain-of-custody (each entry hashed and linked to the previous entry's hash). Tampering with historical entries shall be detectable via hash chain verification. The platform shall support export of audit logs with verifiable signatures for regulatory submission. Audit log retention shall be configurable with a minimum of 7 years for certified workspaces.

### FR-477 Compliance Certifications Pre-Work
The platform shall support the operational requirements needed for common compliance certifications (SOC2 Type II, ISO 27001, HIPAA, PCI-DSS): evidence collection workflows, automated control mapping, access review workflows, change management tracking, and compliance dashboard. The platform does not itself issue certifications but provides the evidence substrate for auditor review.

## 97. Multi-Region and High-Availability Deployment

### FR-478 Multi-Region Active-Passive Deployment
The platform shall support active-passive multi-region deployment for disaster recovery. Configuration shall include: primary region (active), secondary region(s) (passive, continuously replicated), RPO target (default <15min), RTO target (default <1h), and failover procedure. Data replication shall cover PostgreSQL (streaming replication), object storage (cross-region replication), Kafka (MirrorMaker 2), and ClickHouse (replicated tables).

### FR-479 Multi-Region Active-Active Considerations
The platform documentation shall explicitly describe which subsystems can run active-active (stateless services: API, workflow engine, runtime controller) and which cannot without additional conflict resolution (PostgreSQL as primary, global registry of FQN namespaces). Active-active deployments shall require a documented conflict resolution strategy and shall not be enabled by default.

### FR-480 Zero-Downtime Platform Upgrades
Platform upgrades shall be performable without downtime: rolling upgrades for stateless services (API, workflow engine, satellite services), schema migrations with backward-compatible steps (additive columns before writes, rename via dual-write, drop only after verification), and agent runtime versioning that allows new and old runtimes to coexist during the upgrade window. Upgrade procedures shall be documented with rollback steps.

### FR-481 Maintenance Mode
The platform shall support a maintenance mode that: blocks new executions and conversations, allows in-flight work to complete, returns a clear maintenance message to UI and API callers, and can be scheduled with a maintenance window visible to users. Maintenance mode shall not affect read-only operations (marketplace browsing, audit log access).

### FR-482 Capacity Planning and Forecasting
The platform shall provide capacity planning signals: historical usage trends, projected usage based on growth curves, resource utilization alerts ahead of saturation, and cost forecasts. The operator dashboard shall surface capacity alerts with recommended actions (scale up, throttle, restrict new workspace creation).

## 98. Model Provider Resilience and Governance

### FR-483 Multi-Model Provider Support
The platform shall support multiple LLM providers concurrently (OpenAI, Anthropic, Google, Azure OpenAI, AWS Bedrock, Cohere, Mistral, self-hosted models via vLLM or TGI). Provider selection shall be configurable per agent, per step, and per workspace. Provider credentials shall be managed per workspace and rotatable (FR-474).

### FR-484 Model Fallback on Provider Failure
When a model provider returns an error (timeout, rate limit, 5xx, content policy block that is retryable), the platform shall support configurable fallback to an alternative provider or model. Fallback policies shall specify: retry count, backoff strategy, alternative providers in priority order, and acceptable quality degradation. Fallback events shall be logged and visible in execution traces.

### FR-485 Approved Model Catalog
Administrators shall be able to maintain an **approved model catalog** listing models permitted for use in production. Each catalog entry shall include: provider, model identifier, approved use cases, prohibited use cases, context window limits, cost per token, quality tier, and approval metadata (who approved, when, expiry). Agents shall be blocked from using models not in the catalog.

### FR-486 Model Card and Capability Declaration
Each approved model shall have a **model card** declaring its capabilities, training data cutoff, known limitations, safety evaluations, and bias assessments. Model cards shall be consultable by trust reviewers during agent certification and by consumers via agent profiles.

### FR-487 Prompt Injection Model-Level Defense
For models that support it, the platform shall use provider-level safety features (system prompts with isolation markers, tool-use scoping, input classifiers) in addition to the platform's SafetyPreScreener. Multiple layers of defense shall not be bypassable by a single compromised layer.

## 99. User Experience and Accessibility

### FR-488 WCAG 2.1 AA Accessibility Compliance
The web UI shall conform to WCAG 2.1 Level AA accessibility standards: keyboard navigation for all interactive elements, screen reader support with ARIA labels, sufficient color contrast ratios, text resizability up to 200% without loss of functionality, focus indicators, no reliance on color alone to convey information, and accessible form validation messages.

### FR-489 Internationalization and Localization
The web UI shall support internationalization (i18n) of all user-facing strings. Initial supported languages shall include English (primary), Spanish, French, German, Japanese, and Chinese (Simplified). Translation pipeline shall support professional translation workflows. Locale-specific formatting (dates, numbers, currencies) shall follow browser locale preferences with per-user override. Right-to-left (RTL) language support (Arabic, Hebrew) shall be planned but not required for v1.

### FR-490 Dark Mode and Theme Support
The web UI shall support light mode (default), dark mode, and system-preference-follow. Theme choice shall persist per user. High-contrast theme variants shall be available for accessibility.

### FR-491 Keyboard Shortcuts and Command Palette
The web UI shall provide a command palette (Cmd/Ctrl+K) for rapid navigation and action execution, and configurable keyboard shortcuts for common operations (new conversation, search marketplace, open workspace, toggle theme). Shortcuts shall be discoverable via help overlay (press `?`).

### FR-492 Mobile and Responsive Design
The web UI shall be responsive and usable on tablets and mobile phones for read-mostly use cases (view executions, respond to approval requests, review alerts). Full creator and operator workflows require a desktop viewport. A progressive web app (PWA) manifest shall be published.

### FR-493 User Preferences and Settings
Each user shall be able to configure personal preferences persisted in the database: default workspace, notification preferences (FR-433 extended to cover channels and quiet hours), UI theme, language, time zone, and data export download format.

## 100. Notification Channels and Outbound Integration

### FR-494 Multi-Channel Notification Delivery
User alerts and attention requests shall support delivery via multiple channels: in-app WebSocket (default), email (SMTP), webhook (user-configurable URL with signing secret), Slack (via incoming webhook or app), Microsoft Teams, SMS (via Twilio or equivalent, optional). Each user shall be able to configure channel preferences per alert type.

### FR-495 Webhook Signing and Delivery Guarantees
Outbound webhooks shall be signed with HMAC-SHA256 using a per-webhook secret. Delivery shall include: at-least-once semantics with idempotency keys, retry with exponential backoff on 5xx or timeout (max 3 retries over 24h), dead-letter queue for undeliverable events, and delivery status visible to the configuring user.

### FR-496 Outbound Callback Registration
The platform shall provide APIs for external systems to register callback URLs for platform events. Registration shall require: URL, events of interest, signing secret, active/paused state, retry policy override (within system limits). Callbacks shall be scoped per workspace.

## 101. API Governance and Developer Experience

### FR-497 OpenAPI Specification and Generated SDKs
The platform shall publish an OpenAPI 3.1 specification covering all public REST endpoints. The specification shall be served at `/api/openapi.json` and rendered via an embedded Swagger UI or Redoc at `/api/docs`. Generated SDKs for Python, Go, TypeScript, and Rust shall be published to their respective package registries on each release.

### FR-498 API Versioning Policy
Public APIs shall be versioned via URL path (`/api/v1/`, `/api/v2/`). Breaking changes require a new major version. Old versions shall be supported for at least 12 months after a new version is released. Deprecation shall be announced via changelog, API response headers (`Sunset`, `Deprecation`), and email to API consumers.

### FR-499 Rate Limiting per API Consumer
API rate limiting shall apply per authenticated principal (user, service account, external A2A client). Limits shall be configurable per subscription tier with sensible defaults. Rate limit responses shall include `X-RateLimit-*` headers and a Retry-After hint.

### FR-500 API Request and Response Logging for Debugging
Administrators shall be able to enable per-user or per-workspace detailed API request/response logging for debugging. Logging shall be time-bounded (maximum 4 hours), require justification, and be fully audited. Logged payloads shall be redacted for secrets and PII.

## 102. Cost Governance and Chargeback

### FR-501 Cost Attribution at Every Execution
Every agent execution shall record detailed cost attribution: model provider cost (tokens × price), infrastructure cost (compute seconds × rate), storage cost (bytes × rate × duration), allocated overhead (platform per-execution surcharge). Attribution shall be stored in ClickHouse for aggregation.

### FR-502 Chargeback and Showback
The platform shall support workspace-level chargeback (billed to workspace owner) and showback (reported but not billed). Reports shall be exportable per period (daily, weekly, monthly) with cost breakdown by agent, fleet, model provider, user, and workflow.

### FR-503 Budget Alerts and Hard Caps
Each workspace shall support configurable cost budgets with: soft alerts at configurable thresholds (50%, 80%, 100%), hard caps that block further executions when exceeded (with admin override), and forecasted end-of-period spend visible on the operator dashboard.

### FR-504 Cost Tracking Dashboard
The platform shall provide a cost tracking dashboard showing: real-time spend, historical spend trends, cost per agent / fleet / user, cost anomalies (sudden increases), and cost-effectiveness metrics (quality per dollar). Administrators shall be able to drill down to individual executions.

## 103. Operational Runbooks and Incident Response

### FR-505 Incident Response Integration
The platform shall integrate with common incident response systems (PagerDuty, OpsGenie, VictorOps). Configurable alert rules shall trigger incidents for: sustained error rate spike, SLA breach, certification failure, security event (unauthorized access attempt, credential misuse), chaos scenario triggering unexpected behavior.

### FR-506 Runbook Integration
Common operational scenarios shall have runbooks accessible from the operator dashboard: pod failure, database connection issue, Kafka lag, model provider outage, certificate expiry, S3 quota breach, governance verdict storm. Runbooks shall include: symptom identification, diagnostic commands, remediation steps, escalation path.

### FR-507 Incident Post-Mortem Templates
The platform shall provide post-mortem templates aligned with blameless post-mortem practices: timeline reconstruction from audit log + execution journal + Kafka events, impact assessment, root cause analysis, action items, and distribution list. Post-mortems shall be linkable to affected executions and certifications for historical context.

## 104. Content Safety and Fairness

### FR-508 Output Content Moderation
The platform shall integrate content moderation for agent outputs: toxicity classification, hate speech detection, violence/self-harm detection, sexually explicit content detection, PII leakage detection. Moderation policies shall be configurable per workspace. Moderation events shall be logged.

### FR-509 Bias and Fairness Evaluation
The evaluation framework shall support bias and fairness metrics for agents: demographic parity, equal opportunity, calibration across groups (where applicable). Fairness evaluations shall be runnable on-demand and as part of certification workflows.

### FR-510 Consent and Disclosure
When users interact with agents, the platform shall disclose: that they are interacting with an AI agent (not a human), what data is being collected, how outputs may be used (training, evaluation), and the agent's certification status. Disclosure shall be clear and non-dismissible for first-time interactions.

## 105. Tags, Labels, and Organization

### FR-511 Tagging and Labeling Across Entities
Workspaces, agents, fleets, workflows, policies, certifications, and evaluation suites shall support tags (free-form) and labels (key-value pairs). Tags shall be searchable across entity types. Labels shall be usable in policy expressions and filtering.

### FR-512 Saved Views and Filters
Users shall be able to save frequently-used filter combinations as named views (e.g., "Production agents in finance-ops with active certifications"). Saved views shall be personal or shared per workspace.

## 106. Observability Helm Bundle and Deployment Topology

### FR-513 Unified Observability Helm Chart
The platform shall ship a single umbrella Helm chart `deploy/helm/observability/` that installs the complete observability stack in one command. The umbrella chart shall declare sub-chart dependencies on the upstream Prometheus community chart (kube-prometheus-stack or equivalent providing Prometheus, Alertmanager, node-exporter, kube-state-metrics), Grafana, Jaeger, Loki, Promtail, and OpenTelemetry Collector. Sub-charts shall be version-pinned, overridable via values, and installable into a dedicated `platform-observability` namespace with network-policy isolation.

### FR-514 Observability Stack Lifecycle Management
The observability chart shall support independent installation, upgrade, and uninstallation from the rest of the platform. A platform operator CLI command (`platform-cli observability install|upgrade|uninstall|status`) shall wrap Helm invocations and verify that each component is healthy post-install (Prometheus scraping platform targets, Grafana datasources reachable, Jaeger accepting spans, Loki accepting log pushes).

### FR-515 Grafana Data Source Auto-Provisioning
The Helm chart shall auto-provision all required Grafana data sources (Prometheus, Loki, Jaeger) via Grafana provisioning ConfigMaps. Data sources shall be configured with correct intra-cluster URLs, derived-field links (e.g., `trace_id` in Loki logs → Jaeger trace view), and default dashboards set per data source. Grafana shall be reachable behind an Ingress (or NodePort in dev) with platform SSO integration available via OAuth plugin.

### FR-516 Dashboard and Alert Provisioning via ConfigMaps
All 21 platform dashboards (7 existing from feature 047 + 14 new from UPD-034) and all alert rules (Prometheus + Loki) shall be delivered as Kubernetes ConfigMaps with the `grafana_dashboard: "1"` / `prometheus-rule: "1"` labels. Grafana sidecar and Prometheus Operator shall discover and load them automatically. Dashboards and alerts shall be versioned with the platform release.

### FR-517 Log Retention Configuration via Helm Values
Helm values shall expose: Loki hot retention (default 14 days), Loki cold retention in S3 (default 90 days), Prometheus metric retention (default 30 days), Jaeger trace retention (default 7 days), Alertmanager silence retention (default 120 days). Each value shall be tenant-override-able via a per-installation `values-tenant.yaml` overlay.

### FR-518 Observability Resource Sizing Presets
Helm values shall ship three sizing presets — `minimal` (single-node dev/kind, ≤1 GB RAM for the whole stack), `standard` (small production, HA Prometheus, single-binary Loki), `enterprise` (horizontal Prometheus via Thanos, distributed Loki with S3 chunks, Grafana HA). Operators shall select the preset via `values.yaml`; each preset shall have documented capacity limits (metrics cardinality, logs/sec, traces/sec).

## 107. Extended User Journey E2E Tests (Audit-Pass and Observability)

### FR-519 Extended Journey Coverage for Audit-Pass Features
In addition to the 9 journeys defined in FR-461, the platform shall provide 7 additional user journey E2E tests covering the audit-pass features: Privacy Officer (DSR lifecycle end-to-end), Security Officer (SBOM and vulnerability and rotation workflows), Finance Owner (budget and chargeback and anomaly response), SRE (multi-region replication and failover and maintenance), Model Steward (model catalog approval and fallback verification), Accessibility User (WCAG AA keyboard and screen-reader only flows), Compliance Auditor (hash-chain integrity and audit export), and Dashboard Consumer (correlated log-metric-trace debugging). Each journey shall meet the same criteria as FR-462 (minimum 15 assertion points) and FR-463 (independence and parallelism).

### FR-520 Existing Journey Extension for New Features
The existing 9 user journeys from FR-461 shall be extended to exercise audit-pass and observability capabilities wherever they naturally fit:
- **Administrator journey**: configure DLP rules, set a workspace budget, seed the approved model catalog with at least one entry per provider, verify the observability stack is reachable and all dashboards load.
- **Creator journey**: agent creation flow triggers a PIA when sensitive data categories are declared; model binding validated against approved catalog; new agent appears in the Privacy & Compliance dashboard if it processes PII.
- **Consumer journey**: after execution, verify cost attribution record exists; verify content moderation pass event is logged; verify the corresponding log entry reaches Loki within 15 seconds with the correct `user_id` label.
- **Workspace Goal journey**: label the goal with tags (UPD-033), verify tag-based policy expression is evaluated; verify the goal appears in the Goal Lifecycle dashboard.
- **Trust journey**: extend to cover bias/fairness evaluation run + result persistence (UPD-032); verify verdict appears in the Governance Pipeline dashboard.
- **Operator journey**: extend to open an incident via PagerDuty webhook mock (UPD-031), consult a runbook inline, generate a post-mortem with timeline reconstruction; verify the Incident Response dashboard reflects the active incident.
- **Evaluator journey**: verify fairness scorer is available; verify LLM-as-Judge uses a catalog-approved model; verify model fallback triggers when the primary model returns a rate-limit error.
- **External Integrator journey**: verify A2A webhook is HMAC-signed (UPD-028); verify rate-limit headers are present on API responses (UPD-029); verify OpenAPI schema is served at `/api/openapi.json`.
- **Scientific Discovery journey**: verify hypothesis evaluation runs a fairness check when demographic data is involved; verify evaluation results are cost-attributed.

### FR-521 Journey Test — Privacy Officer
The Privacy Officer journey shall simulate a data subject request lifecycle: user submits a DSR via the self-service portal (or officer creates one on behalf), officer reviews and validates identity, officer executes the erasure, cascade deletion propagates across PostgreSQL/Qdrant/Neo4j/ClickHouse/OpenSearch/S3, tombstone record is created with cryptographic proof hash, DSR is marked complete, audit chain entry records the operation, notification is sent to the subject. Minimum 20 assertion points crossing auth, accounts, privacy_compliance, audit, security_compliance, notifications bounded contexts.

### FR-522 Journey Test — Security Officer
The Security Officer journey shall simulate a security compliance cycle: officer publishes SBOM for current release, officer reviews vulnerability scan results, officer triages a critical CVE finding, officer schedules a secret rotation with dual-credential window, officer issues a JIT credential to an on-call operator for a specific operation, officer verifies audit chain integrity and exports signed audit log for a regulatory period. Minimum 20 assertion points crossing auth, security_compliance, audit, notifications bounded contexts.

### FR-523 Journey Test — Finance Owner
The Finance Owner journey shall simulate a cost-governance cycle: owner configures a monthly workspace budget with soft thresholds and hard cap, owner sets up chargeback routing, triggers an execution that crosses the 50% and 80% soft thresholds (verify alerts fire), extends budget after hard cap is reached with admin override, reviews the end-of-period forecast, triggers a cost anomaly (sudden model-cost spike) and reviews the anomaly feed, exports a chargeback report. Minimum 18 assertion points crossing auth, workspaces, cost_governance, notifications, analytics.

### FR-524 Journey Test — SRE / Multi-Region Operator
The SRE journey shall simulate a multi-region operations cycle: operator reviews replication lag across all data stores, schedules a maintenance window with graceful drain, executes a quarterly failover test to the secondary region, verifies in-flight executions complete gracefully, verifies new executions route to the secondary, performs failback, verifies no data loss via reconciliation queries, reviews RPO/RTO metrics for the event. Minimum 18 assertion points crossing auth, multi_region_ops, workflow, workspaces.

### FR-525 Journey Test — Model Steward
The Model Steward journey shall simulate a model catalog governance cycle: steward reviews and approves a new model entry with full card (capabilities, limitations, training cutoff, safety assessments), deprecates an older model with a grace period, configures a fallback policy for a critical agent (primary + two fallbacks with quality-tier constraints), triggers a primary provider outage (mock 429 rate-limit), verifies fallback is used correctly, verifies the fallback event is logged and visible in the Model Catalog dashboard, verifies cost attribution reflects the fallback provider's price. Minimum 18 assertion points crossing auth, model_catalog, trust, workflow, cost_governance.

### FR-526 Journey Test — Accessibility User
The Accessibility User journey shall simulate an end-to-end workflow completed by a user operating only keyboard + screen reader: user logs in (Tab/Shift+Tab navigation, Enter to submit), navigates the marketplace with arrow keys, starts a conversation with an agent, sends a message, observes execution progress via ARIA live region announcements, reviews the reasoning trace via keyboard navigation, logs out. Every interactive element MUST be reachable via keyboard; every status change MUST be announced via ARIA; color contrast ratios MUST be verified against WCAG AA thresholds. Run with axe-core in headless-browser automation asserting zero AA violations on every visited page. Minimum 15 assertion points.

### FR-527 Journey Test — Compliance Auditor
The Compliance Auditor journey shall simulate an audit preparation cycle: auditor logs in, requests audit trail export for a specific period via admin API, platform generates export with cryptographic signature covering the hash chain, auditor verifies chain integrity end-to-end (every entry's hash matches its predecessor), auditor queries specific events (authentication, DSR, policy violations, JIT grants), auditor reviews the compliance evidence dashboard for SOC2/ISO27001 controls, auditor exports evidence bundle for regulatory submission. Minimum 16 assertion points crossing auth, audit, security_compliance, privacy_compliance.

### FR-528 Journey Test — Dashboard Consumer / Log-Metric-Trace Correlation
The Dashboard Consumer journey shall simulate an SRE debugging a production issue using the observability stack: SRE observes a `HighErrorLogRate` alert, opens the Cross-Service Error Overview dashboard, identifies the top failing service, drills down to Loki logs filtered by service, picks an error log entry with a `trace_id`, clicks through to Jaeger to view the full distributed trace, correlates the trace with Prometheus metrics for the same time window, identifies root cause, verifies the resolution by watching the alert close. Minimum 15 assertion points exercising the integrated observability experience.

### FR-529 Journey Test Narrative Reports with Dashboard Snapshots
Extended journey tests (FR-521 through FR-528) shall produce HTML reports including: step-by-step narrative with pass/fail indicators, screenshots of relevant Grafana dashboards taken at key moments, links to Loki log queries, links to Jaeger trace views. Reports shall be downloadable as artifacts from CI and viewable directly in the browser.

### FR-530 Journey Tests Run Against Ephemeral Observability Stack
All journey tests (original + extended) shall run against a kind cluster that includes the full observability stack (Prometheus + Grafana + Loki + Jaeger + Alertmanager) provisioned via the same Helm chart used in production. No mocking of observability backends — assertions about dashboard data, log presence, and metric values use real queries against the running Loki/Prometheus.

### FR-531 Updated Bounded-Context E2E Suites for New Bounded Contexts
The bounded-context E2E suites (FR-456) shall be extended with new suites covering the bounded contexts introduced by the audit pass: `privacy_compliance` (DSR, cascade deletion, DLP, PIA, residency), `security_compliance` (SBOM, vuln scan ingestion, pen test, rotation, JIT, audit chain), `cost_governance` (attribution, chargeback, budget enforcement, forecast, anomaly), `multi_region_ops` (region config, replication monitoring, maintenance mode), `model_catalog` (catalog CRUD, card publication, fallback), `localization` (preferences, locale files). Each new suite shall follow the same style as existing suites (FR-457) and integrate with the Mock LLM Provider and dev-only `_e2e` endpoints.

### FR-532 Chaos Scenario Expansion
The chaos scenario catalog (FR-459) shall be expanded with scenarios specific to the new bounded contexts and the observability stack: Loki ingestion outage (logs buffered, alerts on drop), Prometheus scrape failure (metrics gap visible), model provider total outage (fallback exhaustion behavior), residency enforcement misconfiguration (query rejection), budget hard cap reached mid-execution (graceful termination or admin override flow), audit chain storage failure (fail-closed behavior preserves integrity).

## 108. Log Aggregation with Loki (Structured Logging and Dashboards)

### FR-533 Loki Log Aggregation Backend
The platform shall deploy Grafana Loki in the `platform-observability` namespace as the centralized log aggregation backend. Loki shall use S3-compatible object storage (via the generic S3 client from FR-447) for chunk storage, enabling retention beyond what in-cluster disk can hold. Loki shall be reachable only from within the cluster; external access is exclusively via Grafana proxy.

### FR-534 Promtail Log Collection DaemonSet
The platform shall deploy Promtail as a DaemonSet on every node. Promtail shall auto-discover pods in all platform namespaces (`platform-control`, `platform-execution`, `platform-simulation`, `platform-data`, `platform-observability`, `platform-ui`) and ship their container stdout/stderr logs to Loki. Promtail shall run as non-root with read-only access to log paths.

### FR-535 Structured JSON Logging Contract
All platform services (Python control plane, Go satellite services, Next.js frontend server, frontend client via error reporting) shall emit structured JSON logs to stdout with the following mandatory fields: `timestamp` (ISO 8601 with timezone), `level` (debug|info|warn|error|fatal), `service` (service identifier), `bounded_context`, `message`. Optional but strongly recommended fields: `trace_id`, `span_id`, `correlation_id`, `workspace_id`, `goal_id`, `user_id`, `execution_id`, `agent_id`. Non-structured logging (plain text `print`, `fmt.Println`) shall be treated as a code review violation.

### FR-536 Correlation ID Propagation via Context
`trace_id`, `correlation_id`, `workspace_id`, `goal_id`, and `user_id` shall propagate automatically through async boundaries via Python ContextVars (control plane), Go `context.Context` (satellite services), and Next.js request context (frontend server). Middleware at HTTP ingress and Kafka consumption shall populate these at entry. Manual passing of correlation IDs shall not be required in business logic.

### FR-537 Log Retention — Hot and Cold Tiers
Loki shall retain logs for at least 14 days hot (in-cluster, fast queries) and at least 90 days cold (S3-archived, slower queries but regulatorily retained). Retention durations shall be configurable per tenant via Helm values. Log data in both tiers shall be queryable via LogQL with unified semantics (the tier transition is transparent to the query author).

### FR-538 Sensitive Data Redaction in Log Ingestion
Promtail shall apply redaction patterns to incoming log lines before shipping to Loki, masking at minimum: bearer tokens (`Bearer <alphanumeric>`), API keys matching known patterns (`sk-...`, `ghp_...`, AWS key format), email addresses in error contexts, Social Security Numbers, credit-card-like sequences. Redaction patterns shall be additive via Helm values. Redaction failures shall not block ingestion; they shall be counted and reported.

### FR-539 Grafana Data Source Integration
Grafana shall have Loki configured as a data source alongside Prometheus and Jaeger, with derived-field configuration that renders a `trace_id` in a Loki log entry as a clickable link opening the corresponding trace in Jaeger. Similarly, a Prometheus metric data point with a matching label set shall offer a "View related logs" action that opens Loki filtered by the same labels and time range.

### FR-540 Five Log-Focused Grafana Dashboards
The platform shall ship five log-focused dashboards: (1) **Control Plane Service Logs** — unified view of Python bounded contexts with log volume, error rate, recent errors, filters by workspace/goal/user; (2) **Go Satellite Service Logs** — runtime-controller / sandbox-manager / reasoning-engine / simulation-controller; (3) **Frontend Web Logs** — Next.js server logs + client-side error reporting with correlated API errors; (4) **Audit Event Stream** — real-time audit chain feed with entries by type and hash verification status; (5) **Cross-Service Error Overview** — aggregated errors across all services with clustering.

### FR-541 Nine Metric+Log Dashboards for Audit-Pass Bounded Contexts
The platform shall ship nine metric-and-log dashboards covering the audit-pass bounded contexts: **Privacy & Compliance** (DSRs, DLP events, PIAs, residency), **Security Compliance** (SBOM, CVEs, pen-tests, rotations, JIT, audit chain integrity), **Cost Governance** (spend, budgets, anomalies, forecasts), **Multi-Region Operations** (replication lag, RPO/RTO, maintenance windows), **Model Catalog & Fallback** (usage, fallback events, provider health), **Notifications Delivery** (channels, webhook status, DLQ), **Incident Response & Runbooks** (active incidents, MTTR, post-mortems, runbook access), **Goal Lifecycle & Agent Responses** (goal states, response decisions, attention requests), **Governance Pipeline** (observer signals, verdicts, enforcement actions).

### FR-542 Dashboard Load Performance and Filtering
All dashboards (7 existing + 14 new) shall load and render initial data within 5 seconds on seeded demo data. All dashboards shall support: time range picker, workspace filter variable, auto-refresh (default 30s), drill-down links to related dashboards and raw Loki/Jaeger queries. Default time range shall be one hour to prevent expensive 90-day-scope queries.

### FR-543 Loki-Based Alert Rules
The platform shall ship Loki-based alert rules via Loki Ruler (or Prometheus-compatible AlertManager routing), covering at minimum: `HighErrorLogRate` (per-service error rate exceeding threshold), `SecurityEventSpike` (auth/privacy/security BC errors), `DLPViolationSpike` (DLP block rate), `AuditChainAnomaly` (hash mismatch or gap), `CostAnomalyLogged` (cost anomaly messages). Alert rules shall fire through the same Alertmanager used for Prometheus alerts, with consistent routing and silencing.

### FR-544 Low-Cardinality Loki Label Discipline
Loki label cardinality shall be bounded. Labels permitted: `service`, `bounded_context`, `level`, `namespace`, `pod`, `container`, `region`. High-cardinality values such as `workspace_id`, `user_id`, `goal_id`, `execution_id`, `trace_id` shall live in the JSON payload of each log line, NOT as Loki labels. LogQL queries filter high-cardinality values via line-filter predicates over the JSON payload.

### FR-545 Log Volume Observability
Log ingestion rate (lines per second per service, bytes per second per service, rejected-log count) shall be exposed as Prometheus metrics from both Promtail (client-side) and Loki (server-side). An operator dashboard panel shall surface these rates and alert on sustained flooding (a service exceeding 1 MB/s sustained triggers operator review).

## 113a. HashiCorp Vault Integration Legacy Draft

The prior draft in this location used stale FR-621 through FR-638 numbering. It is superseded by the canonical Section 113 added after FR-682, covering FR-683 through FR-700.

## 114. OAuth Provider Environment-Variable Bootstrap and Super Admin UI

### FR-639 OAuth Provider Environment-Variable Seeding
The platform installer shall support provisioning OAuth providers (Google, GitHub) non-interactively via environment variables, mirroring the super-admin-bootstrap pattern from FR-004. When the following variables are present at install time, the installer creates and enables the corresponding provider without requiring a super admin to configure it later via the UI:

**Google OAuth:**
- `PLATFORM_OAUTH_GOOGLE_ENABLED`: `true`/`false` (default: `false`).
- `PLATFORM_OAUTH_GOOGLE_CLIENT_ID`: Google OAuth client ID (non-sensitive).
- `PLATFORM_OAUTH_GOOGLE_CLIENT_SECRET`: Google OAuth client secret. Written to Vault at `secret/data/musematic/{env}/oauth/google/client-secret`.
- `PLATFORM_OAUTH_GOOGLE_CLIENT_SECRET_FILE`: alternative path to a file containing the secret.
- `PLATFORM_OAUTH_GOOGLE_REDIRECT_URI`: full callback URL (e.g., `https://app.musematic.ai/auth/oauth/google/callback`).
- `PLATFORM_OAUTH_GOOGLE_ALLOWED_DOMAINS`: comma-separated list of Google Workspace domains permitted to sign up (e.g., `company.com,subsidiary.com`). Empty list permits any domain.
- `PLATFORM_OAUTH_GOOGLE_GROUP_ROLE_MAPPINGS`: JSON mapping of Workspace groups to platform roles (e.g., `{"admins@company.com":"admin","users@company.com":"user"}`).
- `PLATFORM_OAUTH_GOOGLE_REQUIRE_MFA`: `true`/`false` whether Google-authenticated users must additionally enroll platform MFA.
- `PLATFORM_OAUTH_GOOGLE_DEFAULT_ROLE`: role assigned to auto-provisioned users when no group mapping applies (default: `user`).

**GitHub OAuth:**
- `PLATFORM_OAUTH_GITHUB_ENABLED`: `true`/`false` (default: `false`).
- `PLATFORM_OAUTH_GITHUB_CLIENT_ID`: GitHub OAuth app client ID.
- `PLATFORM_OAUTH_GITHUB_CLIENT_SECRET`: GitHub OAuth client secret, written to Vault.
- `PLATFORM_OAUTH_GITHUB_CLIENT_SECRET_FILE`: alternative path to a secret file.
- `PLATFORM_OAUTH_GITHUB_REDIRECT_URI`: full callback URL.
- `PLATFORM_OAUTH_GITHUB_ALLOWED_ORGS`: comma-separated list of GitHub organizations whose members may sign up.
- `PLATFORM_OAUTH_GITHUB_TEAM_ROLE_MAPPINGS`: JSON mapping of GitHub team slugs (`org/team-slug`) to platform roles.
- `PLATFORM_OAUTH_GITHUB_REQUIRE_MFA`: `true`/`false`.
- `PLATFORM_OAUTH_GITHUB_DEFAULT_ROLE`: fallback role (default: `user`).

### FR-640 OAuth Bootstrap Idempotency
The OAuth provider seeder shall be idempotent, following the same pattern as FR-004b:
- If a provider with the given type already exists, the seeder updates its configuration to match the environment variables (merge semantics, preserving any runtime-adjusted fields not set via env vars).
- If a provider exists AND `PLATFORM_OAUTH_{PROVIDER}_FORCE_UPDATE=false` (the default), the seeder skips the update to avoid overriding manual configuration.
- If `PLATFORM_OAUTH_{PROVIDER}_FORCE_UPDATE=true`, the seeder overwrites existing configuration and emits a critical audit chain entry.

### FR-641 OAuth Bootstrap Validation
The installer shall validate OAuth provider configuration before persisting:
- Redirect URI must be a valid HTTPS URL (HTTP permitted only when `ALLOW_INSECURE=true`).
- Client ID format validated per provider (Google: ends in `.apps.googleusercontent.com`; GitHub: alphanumeric).
- Client secret minimum length enforced per provider.
- When `ALLOWED_DOMAINS` or `ALLOWED_ORGS` is empty, the installer emits a warning in the log (security best practice is to restrict).
- Group/team role mappings validated as parseable JSON with known role names.

### FR-642 Helm Values for OAuth Bootstrap
The platform Helm chart shall expose OAuth bootstrap values:

```yaml
oauth:
  google:
    enabled: false
    clientId: ""
    clientSecretRef:              # ExistingSecret reference (preferred)
      name: ""
      key: ""
    clientSecretVaultPath: ""     # Alternative: path in Vault
    redirectUri: ""
    allowedDomains: []
    groupRoleMappings: {}
    requireMfa: false
    defaultRole: user
  github:
    enabled: false
    clientId: ""
    clientSecretRef:
      name: ""
      key: ""
    clientSecretVaultPath: ""
    redirectUri: ""
    allowedOrgs: []
    teamRoleMappings: {}
    requireMfa: false
    defaultRole: user
```

When `clientSecretRef` is set (Kubernetes Secret reference) the installer reads the secret at startup. When `clientSecretVaultPath` is set AND Vault mode is active, the installer references the Vault path directly without copying the secret. At least one of the two must be set per enabled provider.

### FR-643 OAuth Provider Super Admin Configuration Page (Extended)
The super admin page at `/admin/oauth-providers` (introduced in UPD-036 FR-548, FR-595) shall be extended to expose the full set of configuration options per provider. For each provider the page shall display:
- Current status: enabled/disabled, last edited by / when, last successful authentication.
- Client ID (editable).
- Client secret: write-only input with "Rotate" action; current secret never displayed. Rotation writes a new Vault version and retains history per FR-625.
- Redirect URI (editable with URL validation).
- Allowed domains (Google) or allowed orgs (GitHub) — editable list with add/remove.
- Group/team role mappings — editable table with validation.
- Require MFA toggle.
- Default role selector.
- Source badge indicating how the provider was originally configured: `env_var` (bootstrap), `manual` (via UI), `imported` (via config export/import per FR-572).
- **Test connectivity** button performing a mock OAuth dry-run against the provider's discovery endpoint, returning success/failure with diagnostic info.
- **Reseed from environment** button (super admin only) that re-reads the `PLATFORM_OAUTH_*` variables and updates the provider — useful for GitOps flows where env vars change.

### FR-644 OAuth Provider Configuration History
All changes to OAuth provider configuration shall be stored as an append-only history table with: who changed what, when, and why (change justification required). The admin page shall include a "History" tab showing recent changes with diffs.

### FR-645 OAuth Provider Configuration Export/Import
OAuth provider configuration shall be included in the configuration export bundle (FR-572) with sensitive fields (client secrets) referenced by Vault path only, never inline. Import of a bundle restores provider configuration minus the secrets, which must be present in Vault at the canonical paths before import succeeds.

### FR-646 OAuth Per-Provider Rate Limiting
Per-provider rate limits on OAuth flows (authorize redirects, callback exchanges, group fetches) shall be configurable via the admin page: requests per minute per IP, requests per minute per user, global quota per provider. Exceeded limits return HTTP 429 with Retry-After.

### FR-647 OAuth Environment Variable CI Validation
A CI check shall validate that every `PLATFORM_OAUTH_*` variable referenced in code or documentation is present in the environment variables reference (auto-generated per FR-610). Drift between code and documentation fails the build.

### FR-648 OAuth Bootstrap E2E Coverage
The new E2E journey **J19 New User Signup** (UPD-037) and the existing **J01 Platform Administrator** journey shall be extended to cover env-var OAuth bootstrap:
- Install the platform with `PLATFORM_OAUTH_GOOGLE_ENABLED=true` and valid credentials.
- Verify Google provider exists in the registry on first startup.
- Verify secret is retrievable from Vault at the canonical path.
- Verify the login page shows "Continue with Google" button.
- Verify super admin's `/admin/oauth-providers` page displays the provider with source badge `env_var`.
- Verify a Google OAuth login flow succeeds end-to-end.
- Repeat for GitHub.

## 115. User-Facing Notification Center and Self-Service Security

### FR-649 Notification Center Inbox
The platform shall provide a user-facing notification center at `/notifications` where authenticated users can see all notifications addressed to them (in-app, email, webhook, Slack, Teams, SMS deliveries routed to the user). The inbox shall support: filtering by channel / severity / event type / date range / read state, full-text search, pagination (default 50 per page, configurable up to 200), bulk mark-as-read / delete, individual drill-down to the originating event with links to the related resource (execution, goal, incident, alert, agent). Notifications shall be retained for a configurable period (default 90 days) after which they are archived and purged.

### FR-650 Global Notification Bell
The platform shell (navigation bar) shall include a `<NotificationBell>` component with: unread count badge updated in real time via WebSocket subscription (UPD-034 correlation channel), quick-preview dropdown showing the 5 most recent notifications with action links, "See all" link to `/notifications`, sound indicator (user-configurable) when a critical notification arrives, visual state (normal / unread / attention) reflecting urgency.

### FR-651 Notification Preferences per User
Users shall have a preferences page at `/settings/notifications` controlling: which event types they subscribe to, which channels deliver each event type (granular matrix: event × channel), digest mode per channel (immediate / hourly / daily), quiet hours per channel (do-not-disturb window with timezone awareness), per-workspace notification opt-out, mute rules with expiry. Admin-configured mandatory notifications (incidents, security events) cannot be fully disabled but frequency can be reduced to digest.

### FR-652 Self-Service API Keys and Personal Access Tokens
Authenticated users shall have a page at `/settings/api-keys` where they can: list their own service-account API keys and personal access tokens, create new ones with scope restrictions and expiry (default 90 days, max 1 year configurable per tenant), rotate existing keys, revoke individual keys with immediate effect, view last-used timestamp and source IP (truncated for privacy). The page shall show the created key value exactly once with a prominent copy action and a warning that the value cannot be retrieved later. Key creation requires MFA step-up when MFA is enabled.

### FR-653 MFA Self-Service Enrollment
Users shall have a page at `/settings/security/mfa` for managing multi-factor authentication: view enrollment status (enrolled / not enrolled / pending), enroll a TOTP authenticator with QR code and secret display, regenerate and view (once) a set of one-time backup/recovery codes, disable MFA with password + current TOTP step-up (blocked when admin policy enforces MFA), switch between TOTP providers. Enrollment events emit audit chain entries. The page shall comply with WCAG AA and be localized in all six supported languages.

### FR-654 User Session Management Self-Service
Users shall have a page at `/settings/security/sessions` showing their own active sessions with: device type / user-agent summary, IP address geolocation (city-level, privacy-preserving), session creation timestamp, last-active timestamp, MFA status at creation, revoke action per session and "Revoke all other sessions" bulk action. Current session shall be visually distinguished. Revocation takes effect within 60 seconds across all pods.

### FR-655 Consent Management Self-Service
Users shall have a page at `/settings/privacy/consent` showing: all consents granted (AI disclosure, terms of service version, marketing, analytics, data-sharing with external processors), consent granted-at timestamp and version, consent revocation action per individual consent (with consequences explained — e.g., revoking AI disclosure consent may limit feature availability), consent history. Consent events are written to the audit chain. When a policy change occurs (new terms version), users see a consent-refresh prompt on next login.

### FR-656 Self-Service Data Subject Request Submission
Users shall have a page at `/settings/privacy/dsr` to submit their own data-subject requests per FR-466 and UPD-023: access (download a ZIP of my data), rectification (request correction), erasure (right to be forgotten with clear explanation of irreversibility), portability (export in machine-readable format), restriction of processing, objection to automated decisions. Submission triggers the same workflow as admin-initiated DSRs, with the subject field pre-filled. Users can view their pending and past requests with status.

### FR-657 Self-Service Security Page Audit Chain Integration
Every self-service security action (key creation / rotation / revocation, MFA enrollment / disablement, session revocation, consent changes, DSR submission) emits an audit chain entry linked to the user principal. The user shall be able to view their own audit trail at `/settings/security/activity` filtered to their account actions only; admin impersonation events shall be shown to the impersonated user.

## 116. Workspace Owner Workbench and Connector Self-Service

### FR-658 Workspace Owner Dashboard
The platform shall provide a workspace owner dashboard at `/workspaces/{id}` accessible to users with `workspace_owner` or `workspace_admin` role on that workspace. The dashboard shall display: workspace health summary (active goals, executions in flight, agent count, member count), budget consumption gauge with forecast (reusing UPD-027 cost primitives scoped to this workspace), quota usage per resource (agents, fleets, executions, storage), tag/label summary, recent audit activity scoped to the workspace, DLP violations count (if FR-469 is enabled for the workspace). All metrics respect workspace visibility rules (per FR-002) and the owner cannot see resources shared from outside their workspace.

### FR-659 Workspace Members Management
The workspace owner dashboard shall include a members page at `/workspaces/{id}/members` where the owner can: invite new members by email or by selecting existing platform users, assign workspace roles (owner, admin, member, viewer), remove members, configure per-member visibility overrides, view each member's recent activity, transfer ownership to another member (with 2PA confirmation per FR-561). Member changes emit audit chain entries.

### FR-660 Workspace Settings Page
The workspace owner dashboard shall include a settings page at `/workspaces/{id}/settings` where the owner can configure: workspace name, description, region residency (FR-468), visibility defaults (zero-trust or explicit grants), tag restrictions, archival policy, data retention policy per resource type, per-workspace DLP rules activation, per-workspace budget and hard caps (FR-503). Destructive actions (archive, delete, region change) use typed confirmation per FR-577 and emit audit chain entries.

### FR-661 Workspace-Owned Connectors
Workspace owners shall be able to configure connectors (Slack, Telegram, Email, Webhook) scoped to their workspace at `/workspaces/{id}/connectors`. The platform shall clearly distinguish: **platform-owned connectors** (configured by super admin in `/admin/connectors`, shared across tenants) and **workspace-owned connectors** (configured by workspace owner, scoped to the workspace only). Agents in the workspace can use either based on policy. Workspace-owned connector credentials are stored in Vault at `secret/data/musematic/{env}/workspaces/{workspace_id}/connectors/{connector_id}`.

### FR-662 Connector Setup Wizards
Each connector type shall have a dedicated setup wizard guiding the workspace owner through: (1) prerequisites check (e.g., Slack app created in Slack workspace, Telegram bot created via BotFather, webhook URL chosen); (2) credential entry with inline validation; (3) test connectivity action that attempts a real connection without sending user-visible messages; (4) scope configuration (which agents / fleets can use the connector, which events trigger outbound messages); (5) activation. Setup wizards are localized in all six supported languages.

### FR-663 Connector Activity and Diagnostics
The connectors page shall show per-connector activity logs: recent deliveries (success / failure counts 24h / 7d), failed deliveries with error detail and retry action, DLQ inspection for the webhook connector, audit trail of configuration changes. Rotation of connector credentials follows the same dual-credential window pattern as UPD-024 secret rotation.

### FR-664 IBOR Connector Management for Admins
The admin workbench (UPD-036 `/admin/ibor`) shall be extended with a full-featured configuration UI for LDAP, OIDC, and SCIM connectors. Each connector form shall support: connection test with diagnostics (DNS resolution, TLS handshake, bind/auth attempt, sample query), mapping wizard from external attributes to platform user fields (email, name, groups, custom claims), sync schedule configuration (cron expression with validation), sync trigger with real-time progress, sync history with per-sync metrics (users added / updated / deactivated, errors, duration), error detail drill-down. IBOR connector secrets are stored in Vault at `secret/data/musematic/{env}/ibor/{connector_id}/credentials`.

### FR-665 Workspace Visibility Explorer
The workspace owner dashboard shall include a visibility explorer at `/workspaces/{id}/visibility` showing: graph of what the workspace's agents can see (other agents, tools, workspaces), grants received from other workspaces, grants given to other workspaces, visibility audit log. The explorer supports filtering and search. This surfaces the zero-trust visibility model (FR-002) in a comprehensible way.

### FR-666 Workspace Owner Workbench E2E Coverage
A new E2E journey **J20 Workspace Owner** shall exercise the owner workbench end-to-end: invite a member, configure a workspace-owned Slack connector, test connectivity, set a budget with hard cap, adjust quota, archive a no-longer-needed goal, review visibility grants, transfer ownership with 2PA. Journey crosses workspaces, notifications, connectors, auth, policies, cost_governance, audit bounded contexts with 20+ assertion points.

## 117. Creator-Side UIs — Context Engineering and Agent Contracts

### FR-667 Context Engineering Profile Editor
The creator workbench shall include a context engineering profile editor at `/agent-management/{fqn}/context-profile` where authorized users can: create a new profile, edit profile sources (list of data sources the agent can pull from — memory, knowledge graph, execution history, tool outputs, external APIs), configure retrieval strategies (semantic similarity with Qdrant, graph traversal with Neo4j, FTS with OpenSearch, hybrid), set reranking rules, define context budget (max tokens, max documents), configure provenance tagging, test with sample queries showing which sources contributed. The editor shall validate against the platform's context profile JSON schema before save.

### FR-668 Context Profile Provenance Viewer
The profile editor shall include a provenance viewer showing, for a test query or past execution: which sources returned results, their relevance scores, whether they were included in the final context, their provenance tags, sensitivity classifications (PII, PHI, financial per UPD-023). The viewer links each source to its origin (memory entry, graph node, execution trace) for deep inspection.

### FR-669 Context Profile Version Management
Context profiles shall be versioned. The editor shall show version history with diffs, support rollback to a previous version, and allow comparing two versions side-by-side. When an agent's revision is promoted, its context profile version is pinned to that revision for reproducibility.

### FR-670 Agent Contract Authoring Page
The creator workbench shall include a contract authoring page at `/agent-management/{fqn}/contract` where authorized users can: create a contract with scope (tools allowed, resources allowed, budget limits), expected outputs (schema, quality thresholds), behavioral constraints (forbidden actions, required approvals), escalation rules (when to request human attention, per FR-432 and UPD-009), and failure modes (what the agent does on contract violation). The editor shall support both YAML and JSON syntax, live schema validation, and auto-completion.

### FR-671 Contract Preview and Test
The contract page shall include a preview step that simulates a sample execution against the contract, showing: which contract clauses were triggered, which were satisfied, which were violated, and the resulting action (continue / warn / throttle / escalate / terminate). Users can run preview with saved sample inputs or provide ad-hoc inputs. Previews are non-destructive (no real LLM calls unless explicitly enabled) using the mock LLM provider (FR-458).

### FR-672 Contract Library and Templates
The contract page shall offer a library of starter templates (e.g., "Customer support agent contract", "Code review agent contract", "Research agent contract") authored by the platform team and trusted creators. Templates are forkable; users start from a template and adjust. Templates are versioned independently and can be updated centrally with notification to users who forked from them.

### FR-673 Contract Attachment and Enforcement
Contracts attached to agents or fleets shall be enforced at runtime per FR-420 (contract monitor). The creator page shall show, for an attached contract: its enforcement status (enforced / advisory / disabled), its attachment scope (per agent revision, per workspace, platform-wide), and a link to observe recent enforcement events in the governance dashboard (D21 from UPD-034).

### FR-674 Creator-Side UI E2E Coverage
The J02 Creator journey (UPD-022, extended in UPD-035, UPD-036, UPD-037) shall be further extended to cover context engineering profile creation and contract authoring as part of the publication flow. A creator must successfully: author a profile, test it, attach it to the agent revision, author a contract, preview it, attach it, and proceed to certification. Journey assertion points increase to at least 25 for the full Creator flow.

## 118. Public Status Page, Maintenance Banner, and User-Visible Platform State

### FR-675 Public Platform Status Page
The platform shall publish a public status page at `status.musematic.ai` (or `{env}.status.musematic.ai` for non-production) showing: current overall platform status (operational / degraded / partial outage / full outage), per-component status (API, WebSocket, workflow execution, reasoning engine, marketplace, observability, Vault), active incidents with last update timestamp, scheduled maintenance windows, recent resolved incidents (7-day history), historical uptime per component (30-day rolling view), subscribe-to-updates via email / RSS / webhook / Atom. The page is static (generated from health endpoints via a scheduled job) and does not require login.

### FR-676 Platform Status Banner for Logged-In Users
The main application shell shall include a `<PlatformStatusBanner>` component that renders at the top of every authenticated page when platform state is anything other than operational. Banner variants: maintenance window scheduled (info), maintenance in progress (warning with blocking indicator on affected features), incident active (warning or critical per severity), degraded performance (info). Banner shows a concise title, link to the incident detail on the status page, optional ETA, and a dismiss-for-this-session action that re-surfaces on next navigation. Severity determines color and prominence per accessibility best practices (not color alone).

### FR-677 Maintenance-Mode User Experience
When maintenance mode (FR-502) is active, the UI shall NOT show generic errors. Instead: the status banner shows maintenance in progress, affected actions are disabled with clear tooltips ("This action will be available again after the maintenance window ends at HH:MM"), read-only operations remain functional, attempts to submit blocked actions show a graceful modal explaining the state and offering to retry later. The user is never left to guess what happened.

### FR-678 Incident Subscription Management
Users and anonymous visitors to the public status page shall be able to subscribe to platform-level status updates via: email subscription (confirm-opt-in), RSS / Atom feed URLs, outbound webhook for integration with their own monitoring, Slack incoming webhook URL. Subscriptions can be limited to specific components (e.g., only API status). Management UI for authenticated users lives at `/settings/status-subscriptions`.

### FR-679 Simulation Scenario Editor
The evaluation and testing workbench shall include a simulation scenario editor at `/evaluation-testing/simulations/scenarios/{id}` where authorized users can: define scenario parameters (agents involved, workflow template, tool mock set, input distributions), configure digital twin fidelity (which subsystems are mocked, which are real), set success criteria and assertions, schedule runs. The editor complements the existing simulation pages (new / compare / [runId]) with a missing creation surface for reusable scenarios.

### FR-680 Digital Twin Visualization
The simulation detail page (`/evaluation-testing/simulations/[runId]`) shall be extended with a digital twin visualization panel showing: which components ran as mocks vs real, divergence points between simulation and production, simulated time vs wall-clock time, trace comparison to a reference production execution if available. This surfaces the digital twin concept (§14 in system architecture) for operators and creators.

### FR-681 Scientific Discovery Session Detail
The scientific discovery workbench (`/discovery/`) shall be extended with: a session detail page at `/discovery/{session_id}` beyond the network view (currently the only page), a hypothesis library browser at `/discovery/{session_id}/hypotheses` with ranking and filtering, an experiment launcher at `/discovery/{session_id}/experiments/new` to propose and run an experiment testing a hypothesis, an evidence inspector at `/discovery/{session_id}/evidence/{evidence_id}` for deep-inspection of supporting data. These complete the discovery workbench surface that today is limited to a single network view.

### FR-682 Status Page and Platform State E2E Coverage
A new E2E journey **J21 Platform State** shall exercise the visibility layer: trigger a synthetic incident, verify public status page reflects it within 60 seconds, verify logged-in users see the banner, verify subscribed user receives email notification, verify RSS feed contains the entry, resolve the incident, verify all surfaces update. The simulation scenario editor and discovery session detail are covered by extensions to J07 Evaluator and J09 Scientific Discovery journeys respectively.

## 113. HashiCorp Vault Integration

**Section 113 — HashiCorp Vault Integration** (FR-683 through FR-700 — NEW per spec correction §6 — appended after FR-682):

- **FR-683**: The platform MUST support a `vault` deployment mode that integrates with HashiCorp Vault as a real secret backend (not a placeholder), in addition to the existing `mock` mode and a NEW transitional `kubernetes` mode that reads from Kubernetes Secrets.
- **FR-684**: The platform MUST support three Vault authentication methods — `kubernetes`, `approle`, `token` — with `token` rejected at startup unless `ALLOW_INSECURE=true` AND `PLATFORM_ENVIRONMENT=dev` per constitutional Rule 10.
- **FR-685**: The platform MUST consolidate secret resolution behind a single `SecretProvider` Protocol exposed at `apps/control-plane/src/platform/common/secret_provider.py` with methods `get(path, key) -> str`, `put(path, values: dict) -> None`, `delete_version(path, version) -> None`, `list_versions(path) -> list[int]`, `health_check() -> HealthStatus`. All bounded contexts that resolve secrets MUST use this Protocol; direct calls to `VaultResolver` are prohibited.
- **FR-686**: A Go-side `SecretProvider` interface with equivalent semantics MUST exist at `services/shared/secrets/provider.go` and MUST be the resolution path for every Go satellite that reads platform credentials.
- **FR-687**: A CI check MUST fail the build on any direct call to `os.getenv(...)` (Python) or `os.Getenv(...)` (Go) for variable names matching the secret patterns `*_SECRET`, `*_PASSWORD`, `*_API_KEY`, `*_TOKEN`, except inside the `SecretProvider` implementation files. The check is implemented as an extension to UPD-039's `scripts/generate-env-docs.py` deny-list per constitutional Rule 37.
- **FR-688**: When Vault is unreachable, the platform MUST (a) serve cached values within the cache TTL; (b) serve stale values past TTL up to `maxStalenessSeconds`; (c) refuse critical reads (auth, OAuth callback, IBOR sync) on cache miss with a clear error; (d) NEVER invoke a hardcoded fallback credential path; (e) emit a Prometheus alert within 60 seconds.
- **FR-689**: The KV v2 path scheme `secret/data/musematic/{env}/{domain}/{resource}` MUST be the canonical organisation; `{env}` ∈ {production, staging, dev, test, ci}; `{domain}` ∈ {oauth, model-providers, notifications, ibor, audit-chain, connectors, accounts}; `{resource}` is BC-defined.
- **FR-690**: Vault token lifecycle MUST be honoured: lease renewal at 50% of token TTL (40% under detected clock skew); re-authentication on revocation; lease revocation on SIGTERM (graceful pod shutdown).
- **FR-691**: The platform MUST cache resolved secrets in a per-pod in-process LRU with default TTL `60s` and default max staleness `300s` (both tunable via Helm values); cache flushes MUST be triggerable via `platform-cli vault flush-cache` AND via the `/admin/security/vault` cache-flush admin action.
- **FR-692**: Secret rotation MUST be implemented via Vault's native KV v2 versioning: `vault kv put` writes a new version; both the prior and new versions MUST be readable for the dual-credential window (default 60s, matching cache TTL); the prior version MUST be destroyed via `vault kv metadata delete` after the window. The existing `RotatableSecretProvider` (UPD-024) is rewired onto this path; semantics preserved.
- **FR-693**: A migration tool `platform-cli vault migrate-from-k8s` MUST mirror Kubernetes Secrets into Vault at canonical paths; MUST be idempotent (re-running migrates only missing items); MUST emit a manifest documenting source → destination → SHA-256 of value → success/failure (NEVER plaintext).
- **FR-694**: A Vault Helm sub-chart at `deploy/helm/vault/` MUST wrap the upstream `hashicorp/vault` chart with platform-specific defaults and 3 sizing presets: `dev` (single pod, in-memory, no persistence — for kind), `standalone` (single pod with persistent storage — for small production), `ha` (3 pods with Raft — for production HA).
- **FR-695**: Vault policies MUST be committed at `deploy/vault/policies/*.hcl` per bounded context (auth, model_catalog, notifications, runtime, security_compliance, ibor, accounts) and attached to the `musematic-platform` Kubernetes auth role; deny-by-default per Rule 10 means a BC with no committed policy receives no Vault read capability.
- **FR-696**: Database / Transit / PKI secret engines MAY be optionally configured per documented operator-guide instructions; KV v2 is the only REQUIRED engine. The audit chain (UPD-024 / security_compliance BC) MAY use Transit for sign/verify in a follow-up — UPD-040 does NOT make that wiring mandatory.
- **FR-697**: Prometheus metrics `vault_lease_count`, `vault_renewal_success_total`, `vault_renewal_failure_total`, `vault_auth_failure_total`, `vault_read_total`, `vault_write_total`, `vault_cache_hit_total`, `vault_cache_miss_total`, `vault_cache_hit_ratio`, `vault_serving_stale_total`, `vault_policy_denied_total` MUST be exposed by every control-plane and Go-satellite pod that integrates with Vault.
- **FR-698**: The `/admin/security/vault` page (delivered by UPD-036; backend contracts owned by UPD-040) MUST surface connection / auth / token-expiry / lease-count / per-BC read rate / cache-hit-rate panels and MUST expose cache-flush + connectivity-test admin actions per constitutional Rule 30 (every admin endpoint role-gated).
- **FR-699**: The migration tool's manifest MUST be verifiable post-hoc via `platform-cli vault verify-migration --manifest=path/to/manifest.json`; rollback (re-flipping `PLATFORM_VAULT_MODE` to `kubernetes`) MUST be operator-driven and documented in the operator guide (FR-617's runbook library).
- **FR-700**: The auto-generated env-var reference (UPD-039 / FR-610) MUST classify `PLATFORM_VAULT_TOKEN`, `PLATFORM_VAULT_APPROLE_SECRET_ID`, and any future Vault-backed credential env vars as `sensitive` with the `Never log; never persist outside Vault.` annotation per constitutional Rule 31 (bootstrap secrets never logged).

## 71. Final Comprehensive Acceptance Criteria

In addition to all earlier acceptance criteria, this complete revision shall not be considered done unless all of the following are also true:

1. at least one agent or workflow uses a named context engineering profile with quality scoring and budget enforcement;
2. at least one agent has a declared capability maturity level that is visible in the marketplace and enforced by policy;
3. at least one self-correction loop can execute, persist iteration traces, detect convergence, and terminate automatically;
4. at least one execution persists chain-of-thought reasoning traces and makes them available for forensic inspection;
5. at least one resource-aware routing decision dynamically selects a model based on task complexity classification;
6. at least one AI-assisted agent composition workflow can generate an agent blueprint from a natural-language task description;
7. at least one hypothesis generation and tournament-ranking workflow can execute with full provenance chains;
8. at least one privacy-preserving collaboration pattern is enforced during cross-workspace agent coordination;
9. at least one marketplace recommendation is generated based on usage-based quality signals and workspace context;
10. at least one fleet-level performance profile aggregates member metrics and exposes them through the operator workbench;
11. at least one conversation branching and merging operation completes without data loss;
12. at least one simulation execution runs against synthetic data with clear separation from production artifacts;
13. at least one governance-aware CI/CD pipeline gates an agent deployment on evaluation results and behavioral regression checks;
14. at least one semantic similarity test evaluates agent output quality using embedding-based scoring;
15. at least one adversarial test suite probes an agent with prompt injection and edge-case scenarios.
