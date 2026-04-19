# Quickstart & Test Scenarios: A2A Protocol Gateway

**Feature**: 065-a2a-protocol-gateway | **Date**: 2026-04-19  
**Spec**: [spec.md](spec.md)

This document lists the acceptance scenarios that drive implementation and verification.

---

## S1 — Agent Card discovery returns valid JSON for active agents

Setup: At least one active platform agent with complete metadata (fqn, purpose, endpoint in manifest_snapshot).  
Expected:
- HTTP 200 on `GET /.well-known/agent.json`
- Response contains the agent's FQN as `name`, purpose as `description`
- `skills` array includes entries for the agent's tool bindings

## S2 — Archived agent excluded from Agent Card

Setup: One active agent, one archived agent.  
Expected:
- Only the active agent appears in the Agent Card
- No metadata about the archived agent leaks in the response

## S3 — Agent Card auto-refreshes when registry changes

Setup: Add a new agent to the registry.  
Expected:
- Agent Card reflects the new agent within the propagation window (≤ 5 minutes)
- No manual refresh required

## S4 — Inbound task accepted and mapped to interaction

Setup: Active platform agent, authenticated external principal with permission.  
Expected:
- `POST /api/v1/a2a/tasks` returns 202 with `task_id` and `a2a_state: submitted`
- An `Interaction` record is created in the backing store with `a2a_task_id` correlation
- An `a2a.task.submitted` Kafka event is emitted

## S5 — Inbound task reaches terminal state

Setup: Same as S4.  
Expected:
- `GET /api/v1/a2a/tasks/{task_id}` progresses through submitted → working → completed
- Final status includes `result` in A2A canonical format
- `A2AAuditRecord` written with `action=task_completed`

## S6 — Inbound task rejected — unauthenticated request

Setup: No Authorization header.  
Expected:
- HTTP 401 with `code: authentication_error`
- No interaction created, no audit record for the agent invocation
- Auth failure audit record written

## S7 — Inbound task rejected — insufficient authorization

Setup: Valid token, principal lacks invocation permission for the target agent.  
Expected:
- HTTP 403 with `code: authorization_error`
- No agent invocation occurs
- `PolicyBlockedActionRecord` written for the denial

## S8 — Inbound task rejected — agent not found or non-public

Setup: Task targets non-existent or archived agent FQN.  
Expected:
- HTTP 404 with `code: agent_not_found`
- No metadata about which agents exist is leaked

## S9 — Rate limit enforcement on inbound tasks

Setup: Configure rate limit of 5 requests / minute for external principals.  
Expected:
- 6th request within the window returns HTTP 429 with `retry_after_ms`
- Rate-limit breach is logged in audit records

## S10 — SSE stream delivers lifecycle events

Setup: Submit a long-running inbound task. Subscribe to SSE stream.  
Expected:
- `GET /api/v1/a2a/tasks/{task_id}/stream` returns `text/event-stream`
- Events emitted for each state transition (submitted → working → completed)
- Final event emitted when task reaches terminal state
- Stream closes after terminal event

## S11 — SSE stream reconnection with Last-Event-ID

Setup: Connect to SSE stream, disconnect mid-task, reconnect with `Last-Event-ID`.  
Expected:
- Stream resumes from the event after the last received one
- No lifecycle transitions are missed

## S12 — Multi-turn conversation — input_required state

Setup: Platform agent configured to request clarification mid-task.  
Expected:
- Task transitions to `a2a_state: input_required`
- SSE stream emits `input_required` event with clarification prompt
- `GET /api/v1/a2a/tasks/{task_id}` returns `a2a_state: input_required`

## S13 — Multi-turn conversation — follow-up resumes task

Setup: Task in `input_required` state.  
Expected:
- `POST /api/v1/a2a/tasks/{task_id}/messages` returns 202 with `a2a_state: working`
- Task completes normally after follow-up
- New Interaction record created in the backing conversation

## S14 — Multi-turn idle timeout auto-cancels task

Setup: Task in `input_required` state. No follow-up submitted within idle timeout (default 30 minutes).  
Expected:
- Task is auto-cancelled by the background scanner
- `A2AAuditRecord` written with `action=task_cancelled` and reason `idle_timeout`

## S15 — Outbound A2A call — happy path

Setup: Register an external endpoint. Platform agent calls `invoke_external_agent`.  
Expected:
- Gateway fetches external Agent Card (or uses cache)
- Policy check passes for the destination
- Task submitted to external endpoint
- Result returned to calling platform agent
- `a2a.outbound.attempted` Kafka event emitted

## S16 — Outbound call denied by policy

Setup: Configure deny-all outbound A2A policy.  
Expected:
- `A2APolicyDeniedError` raised before any network request
- `a2a.outbound.denied` Kafka event emitted
- `PolicyBlockedActionRecord` written
- No HTTP request made to external endpoint

## S17 — Outbound call denied — non-HTTPS destination

Setup: Register an endpoint with `http://` URL (this should be blocked at registration).  
Expected:
- `POST /api/v1/a2a/external-endpoints` returns HTTP 400 with `code: https_required`
- Even if somehow registered (legacy data), gateway refuses to call HTTP endpoints

## S18 — Output sanitization strips secrets

Setup: Platform agent response contains a synthetic bearer token.  
Expected:
- Token is redacted to `[REDACTED:bearer_token]` before being returned to external client
- `redaction_count > 0` in internal SanitizationResult

## S19 — External Agent Card cached and reused

Setup: Register external endpoint. Invoke twice within TTL.  
Expected:
- First invocation: cache miss → fresh fetch → Agent Card stored in Redis
- Second invocation: cache hit → no network fetch
- Cache hit rate ≥ 90% under repeated invocations (SC-008)

## S20 — External Agent Card cache refresh on TTL expiry

Setup: TTL set to 5 seconds (test override). Wait for expiry, then invoke.  
Expected:
- Fresh fetch triggered
- Redis cache updated with new card
- `card_cached_at` timestamp updated in database

## S21 — External Agent Card stale fallback on fetch failure

Setup: External endpoint returns 503 on Agent Card fetch. Cached entry exists.  
Expected:
- Cached card returned with `card_is_stale: true`
- Retry scheduled for later
- Invocation proceeds with stale card (logged warning)

## S22 — Cancellation of in-flight task

Setup: In-flight task (working state).  
Expected:
- `DELETE /api/v1/a2a/tasks/{task_id}` returns 200 with `a2a_state: cancellation_pending`
- Once internal interaction reaches safe point, task moves to `a2a_state: cancelled`
- Result discarded, audit record written

## S23 — Protocol version mismatch rejected

Setup: Submit task with unsupported A2A version header.  
Expected:
- HTTP 400 with `code: protocol_version_unsupported` and `supported: ["1.0"]`
- Response arrives within 100ms p95 (SC-010)
- No task created

## S24 — External Agent Card with unsupported authentication scheme

Setup: External Agent Card declares only `mutual_tls` authentication (not supported).  
Expected:
- `A2AUnsupportedCapabilityError` raised, invocation refused
- Incompatibility recorded in audit log

## S25 — Internal agent coordination unaffected

Setup: Run existing integration tests for internal agent-to-agent coordination.  
Expected:
- 100% of pre-existing tests pass
- A2A gateway router does NOT intercept internal Kafka/gRPC messages
