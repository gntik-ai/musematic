# REST API

The REST API reference is generated from `docs/api-reference/openapi.json`. The snapshot comes from the FastAPI control plane and includes `x-codeSamples` entries for Python, Go, TypeScript, and curl on major operations per FR-619.

## Authentication

Most endpoints require a bearer access token issued by the Auth bounded context. Send it on every request:

```http
Authorization: Bearer <access-token>
```

OAuth login and callback routes live in `apps/control-plane/src/platform/auth/router_oauth.py`. Public signup, email verification, and invitation acceptance routes are intentionally unauthenticated; account lifecycle, admin, audit, cost, incident, and multi-region routes require role checks. Service-to-service automation should use a service account API key only where the target endpoint documents that contract.

## Rate Limits

Musematic applies global API rate limiting when `FEATURE_API_RATE_LIMITING=true`, OAuth callback throttling in `platform.auth.dependencies_oauth`, signup and resend limits from FR-588, and domain-specific limits such as memory write quotas.

| Surface | Default Source | Behavior | Client Remediation |
| --- | --- | --- | --- |
| OAuth authorize/callback | `AUTH_OAUTH_RATE_LIMIT_MAX`, `AUTH_OAUTH_RATE_LIMIT_WINDOW` | Returns `429` after repeated auth attempts. | Back off and preserve the original redirect target. |
| Signup and verification resend | `ACCOUNTS_RESEND_RATE_LIMIT` plus FR-588 controls | Uses anti-enumeration responses for public flows. | Show the same confirmation text and avoid account existence hints. |
| Platform API gateway | `FEATURE_API_RATE_LIMITING`, per-principal overrides | Returns `rate_limit_exceeded` with retry headers when configured. | Honor `Retry-After` and retry idempotent reads only. |
| Memory writes | `MEMORY_RATE_LIMIT_PER_MIN`, `MEMORY_RATE_LIMIT_PER_HOUR` | Rejects excessive memory writes for an agent. | Batch low-priority writes and retry after the window. |
| Webhooks and notifications | Notification channel limits | Retries with delivery state and dead-letter tracking. | Make receivers idempotent and return `2xx` only after durable acceptance. |

## Versioning

REST paths are currently rooted at `/api/v1`. Backward-compatible additions may add fields, enum values, endpoints, and optional request properties. Breaking changes require a new versioned route family or an explicit deprecation marker. Clients should ignore unknown response fields and should not depend on undocumented enum exhaustiveness.

## Major Endpoint Groups

| Group | Prefix | Purpose |
| --- | --- | --- |
| Auth and OAuth | `/api/v1/auth`, `/api/v1/oauth` | Login, MFA, token refresh, OAuth providers, callback handling. |
| Accounts | `/api/v1/accounts` | Signup, invitations, pending approvals, lifecycle actions. |
| Workspaces | `/api/v1/workspaces` | Workspace CRUD, membership, goals, visibility. |
| Registry and Discovery | `/api/v1/registry`, `/api/v1/discovery` | Agent profile ingestion, marketplace search, experiments. |
| Workflows and Execution | `/api/v1/workflows`, `/api/v1/executions` | Workflow definitions, triggers, runtime events, approvals. |
| Trust and Evaluation | `/api/v1/trust`, `/api/v1/evaluation`, `/api/v1/testing` | Certification, policies, semantic tests, moderation. |
| Operations | `/api/v1/admin`, `/api/v1/audit`, `/api/v1/cost-governance`, `/api/v1/incidents` | Administrative workbench, audit chain, cost controls, runbooks. |
| Integrations | `/api/v1/a2a`, `/api/v1/notifications`, `/api/v1/mcp` | External agents, notification routes, tool gateways. |

## Embedded OpenAPI

<redoc spec-url="../openapi.json"></redoc>

<div id="swagger-ui"></div>
<script src="https://unpkg.com/swagger-ui-dist/swagger-ui-bundle.js"></script>
<script>
window.onload = () => SwaggerUIBundle({ url: "../openapi.json", dom_id: "#swagger-ui" });
</script>

## API Changelog

| Version | Compatibility Notes |
| --- | --- |
| v1.3.0 | Adds public signup, expanded admin workbench routes, incident response, multi-region operations, cost governance, log aggregation documentation, and generated code samples. Compatible clients should continue using `/api/v1`. |
| v1.2.x | Baseline agent orchestration, workflow execution, registry, evaluation, trust, and observability APIs. |
