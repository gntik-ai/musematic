# Developer Guide

The Developer Guide is for contributors and integrators extending Musematic. It covers agent authoring, structured logging, MCP and A2A integrations, contracts, SDK usage, reasoning primitives, evaluation authoring, and self-correction tuning.

| Page | Scope |
| --- | --- |
| [Building Agents](building-agents.md) | Agent metadata, model bindings, packaging expectations. |
| [Agent Card Spec](agent-card-spec.md) | Required fields for discoverable agent cards. |
| [Contract Authoring](contract-authoring.md) | API, event, and workflow contract style. |
| [Tool Gateway](tool-gateway.md) | Tool authorization and result handling. |
| [MCP Integration](mcp-integration.md) | MCP notes and webhook verification. |
| [A2A Integration](a2a-integration.md) | External agent interoperability. |
| [SDK Usage](sdk-usage.md) | Client patterns and generated spec usage. |
| [Reasoning Primitives](reasoning-primitives.md) | Reasoning modes, traces, branches, budgets. |
| [Evaluation Authoring](evaluation-authoring.md) | ATE scenarios and semantic tests. |
| [Self-Correction Tuning](self-correction-tuning.md) | Convergence and correction controls. |
| [Structured Logging](structured-logging.md) | Log format and correlation conventions. |
| [Secret Provider Protocol](secret-provider-protocol.md) | Vault, Kubernetes, and mock secret resolution. |
| [Adding a New Secret](adding-a-new-secret.md) | Canonical paths, policy updates, and callsite wiring. |
| [OAuth Bootstrap Internals](oauth-bootstrap-internals.md) | Startup bootstrap, Vault writes, audit events, migrations, and Helm wiring. |
| [`/me` Endpoint Pattern](me-endpoints.md) | Self-service router rules, endpoint inventory, Rule 46 enforcement, and audit handling. |
| [Notification Preferences Internals](notification-preferences-internals.md) | Matrix data model, mandatory events, quiet hours, and digest behavior. |
