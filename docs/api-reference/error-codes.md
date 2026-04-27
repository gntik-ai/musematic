# Error Codes

Musematic errors use stable machine-readable codes where the service can classify the failure. The common envelope follows FR-583: a short `code`, a human message, optional diagnostics, and a correlation identifier supplied by middleware.

| Code | HTTP / Channel | Meaning | Remediation |
| --- | --- | --- | --- |
| `admin_role_required` | 403 | Caller lacks an admin role. | Ask a super admin to grant the correct workspace or platform role. |
| `admin_read_only_mode` | 423 | Admin session is locked to read-only mode. | Re-authenticate or complete the required approval flow. |
| `superadmin_role_required` | 403 | Operation requires super admin authority. | Route the request through a break-glass or super admin workflow. |
| `platform_admin_required` | 403 | Platform-wide setting requires platform admin. | Use a platform admin token. |
| `workspace_admin_required` | 403 | Workspace setting requires workspace admin. | Switch workspace or request a role update. |
| `auditor_role_required` | 403 | Audit evidence requires auditor access. | Grant auditor role or export through an approved report. |
| `read_only_session` | 423 | Session is not permitted to mutate resources. | Start a fresh privileged session. |
| `two_person_approval_required` | 428 | Sensitive action needs 2PA. | Create or approve the paired approval request. |
| `approval_expired` | 409 | Approval window closed before execution. | Re-submit the operation with a new approval. |
| `account_pending_approval` | 403 | Account is waiting for administrator approval. | Send the user to `/waiting-approval` and avoid retry loops. |
| `account_pending_verification` | 403 | Email verification is incomplete. | Prompt resend or verification completion. |
| `pending_profile_completion` | 403 | OAuth-created account needs profile completion. | Redirect to the profile completion flow. |
| `domain_not_permitted` | 403 | Signup domain is blocked by policy. | Use an approved business domain or request an allow-list change. |
| `org_not_permitted` | 403 | OAuth organization membership is not allowed. | Join an approved organization or change provider policy. |
| `invite_required` | 403 | Signup mode is invitation-only. | Use a valid invitation token. |
| `invitation_expired` | 410 | Invitation token is expired. | Ask an admin for a new invitation. |
| `invitation_revoked` | 410 | Invitation was revoked. | Ask the inviter for a replacement invite. |
| `email_verification_token_invalid` | 400 | Verification token is missing or invalid. | Request a new verification email. |
| `email_verification_token_expired` | 410 | Verification token exceeded TTL. | Request a new token. |
| `rate_limit_exceeded` | 429 | Request exceeded configured rate limits. | Honor `Retry-After`; retry idempotent calls only. |
| `rate_limit_service_unavailable` | 503 | Rate limiter dependency failed while fail-closed. | Retry later; operators should inspect Redis. |
| `validation_error` | 422 | Request body or query parameters failed schema validation. | Fix the field noted in `details`. |
| `authorization_error` | 401 | Token is absent, invalid, or expired. | Refresh credentials and retry. |
| `websocket_denied` | 401 | WebSocket upgrade failed auth. | Send a bearer token or `?token=` query token. |
| `protocol_violation` | WebSocket | Client sent malformed JSON or unsupported message type. | Validate message shape before sending. |
| `payload_too_large` | WebSocket | WebSocket message exceeded size limits. | Send smaller messages or use REST/object storage. |
| `idle_timeout` | WebSocket | Connection exceeded heartbeat timeout. | Reconnect and handle ping/pong correctly. |
| `already_subscribed` | WebSocket | Client subscribed to an existing channel/resource pair. | Treat the response as idempotent success. |
| `cannot_unsubscribe_auto` | WebSocket | Client tried to remove an automatic channel. | Leave auto subscriptions managed by the gateway. |
| `invalid_channel` | WebSocket | Subscription channel is unknown. | Use a channel listed in the WebSocket API page. |
| `invalid_resource_id` | WebSocket | Channel resource ID is malformed or unauthorized. | Pass a valid UUID or target ID visible to the caller. |
| `WORKFLOW_YAML_INVALID` | 400 | Workflow YAML cannot be parsed. | Validate YAML before submitting. |
| `WORKFLOW_SCHEMA_INVALID` | 422 | Workflow parsed but violates schema. | Fix the reported path in the compiler error. |
| `WORKFLOW_DUPLICATE_STEP` | 422 | Workflow has repeated step IDs. | Make every step ID unique. |
| `FLEET_MEMBER_EXISTS` | 409 | Agent already belongs to the fleet. | Treat as idempotent or skip duplicate add. |
| `FLEET_MEMBER_NOT_FOUND` | 404 | Fleet member reference does not exist. | Refresh fleet state and retry with a current member ID. |
| `FLEET_LEAD_ALREADY_EXISTS` | 409 | Fleet already has a lead. | Transfer leadership before assigning another lead. |
| `FLEET_POLICY_ALREADY_BOUND` | 409 | Policy is already attached. | Avoid duplicate binding. |
| `FLEET_POLICY_BINDING_NOT_FOUND` | 404 | Policy binding cannot be found. | Refresh policy bindings. |
| `FLEET_OBSERVER_ALREADY_ASSIGNED` | 409 | Observer assignment already exists. | Treat as idempotent. |
| `FLEET_OBSERVER_ASSIGNMENT_NOT_FOUND` | 404 | Observer assignment is missing. | Refresh observers and retry. |
| `FLEET_RULES_NOT_FOUND` | 404 | Fleet orchestration rules are missing. | Create rules before execution. |
| `FLEET_GOVERNANCE_NOT_FOUND` | 404 | Fleet governance chain is missing. | Attach governance policy. |
| `MODEL_BINDING_BLOCKED` | 403 | Model policy blocked the binding. | Choose an approved model or request policy change. |
| `model_catalog_not_found` | 404 | Catalog entry is missing. | Refresh model catalog and retry. |
| `model_catalog_validation_error` | 422 | Model catalog payload is invalid. | Correct the schema fields. |
| `model_provider_credential_missing` | 503 | Provider credential is absent. | Configure the secret and rotate if needed. |
| `model_fallback_exhausted` | 503 | All configured fallback models failed. | Inspect provider health and fallback chain. |
| `provider_call_failed` | 502 | Provider returned an unrecoverable error. | Retry if idempotent and inspect provider status. |
| `provider_rate_limited` | 429 | Upstream model provider throttled requests. | Back off and consider fallback capacity. |
| `prompt_injection_blocked` | 403 | Safety prescreener blocked the prompt. | Remove unsafe instructions or request reviewer approval. |
| `model_blocked` | 403 | Model use violates policy. | Select an allowed model. |
| `tool_not_found` | 404 | Requested tool is unavailable. | Refresh tool registry and retry. |
| `agent_execution_error` | 500 | Agent runtime failed. | Inspect execution events and task artifacts. |
| `ATE_SCENARIOS_REQUIRED` | 422 | ATE run has no scenarios. | Add scenarios before running. |
| `ATE_SCENARIO_MISSING_FIELD` | 422 | ATE scenario lacks a required field. | Complete the scenario payload. |
| `POLICY_ALREADY_ATTACHED` | 409 | Policy is already attached to target. | Treat as idempotent. |
| `POLICY_ATTACHMENT_NOT_FOUND` | 404 | Policy attachment is missing. | Refresh the target's policy state. |
| `POLICY_VERSION_INVALID` | 422 | Policy version cannot be used. | Publish or select a valid policy version. |
| `DELIVERY_FAILED_PERMANENTLY` | 422 | Notification delivery is no longer retryable. | Inspect dead-letter payload and fix the receiver. |

When a code is absent, clients should fall back to HTTP status handling and log the correlation ID.
