# Research: Workspace Goal Management and Agent Response Decision

**Phase 0 output for**: [plan.md](plan.md)
**Date**: 2026-04-18

---

## Finding 1 — WorkspaceGoal model location and existing schema

- **Decision**: Extend `workspaces/models.py`, not a file under `interactions/`.
- **Rationale**: `WorkspaceGoal` (table `workspaces_goals`) lives in the `workspaces` bounded context at `apps/control-plane/src/platform/workspaces/models.py`. The spec's Brownfield Context referenced `interactions/models/workspace_goal.py` — that path does not exist. All new columns (`state`, `auto_complete_timeout_seconds`, `last_message_at`) are added to `workspaces/models.py` via Alembic migration 046.
- **Existing columns**: `id`, `workspace_id`, `title`, `description`, `status` (GoalStatus enum: open/in_progress/completed/cancelled), `gid` (UUID correlation field), `created_by`, timestamps, soft-delete.
- **New `GoalStatus` vs new `state`**: These are two independent attributes. `GoalStatus` is administrative (managed by workspace admin). New `state` (READY/WORKING/COMPLETE) is the lifecycle state governing message acceptance and agent evaluation. They coexist per FR-001 and spec Assumption 3.

## Finding 2 — WorkspaceGoalMessage already has goal_id

- **Decision**: No new column needed on `workspace_goal_messages`. The spec's DDL `ALTER TABLE workspace_messages ADD COLUMN goal_id` names a table that does not exist. The actual table is `workspace_goal_messages` (in `interactions/models.py`) and it already carries `goal_id UUID FK → workspaces_goals.id CASCADE`.
- **Rationale**: FR-009 ("every stored message MUST carry a reference to the goal") is already satisfied structurally. The migration adds columns to `workspaces_goals` only; `workspace_goal_messages` is unchanged.
- **`last_message_at` on goal**: Needed for auto-completion timer. Added to `workspaces_goals` so the scanner can compare against it without querying the messages table for every goal.

## Finding 3 — No `workspace_agent_subscriptions` table exists

- **Decision**: Create a new `workspaces_agent_decision_configs` table (additive, does not touch existing arrays).
- **Rationale**: The spec's DDL `ALTER TABLE workspace_agent_subscriptions ADD COLUMN ...` refers to a table that does not exist. Agent subscriptions are currently stored as `subscribed_agents TEXT[]` in `WorkspaceSettings` (table `workspaces_settings`). Altering an ARRAY column to encode per-agent JSON configs would be non-atomic and error-prone. A dedicated normalized table (`workspaces_agent_decision_configs`) with `(workspace_id, agent_fqn)` unique key maps cleanly to per-subscription strategy config and provides `subscribed_at` for deterministic best-match tie-breaking (FR-016).
- **Alternatives considered**: JSONB column on `WorkspaceSettings` keyed by agent FQN — rejected because it is harder to query and lacks a `subscribed_at` ordering column; separate table in `interactions/models.py` — rejected because the record is semantically a workspace-scoped subscription attribute, not an interaction record.

## Finding 4 — Strategy pattern: follow evaluation/scorers Protocol

- **Decision**: Implement `ResponseDecisionStrategy` as a `Protocol` with `async def decide(message, goal_context, config) -> DecisionResult`, mirroring `evaluation/scorers/base.py`.
- **Rationale**: The codebase already uses a Protocol-based scorer pattern with a shared `ScoreResult` result object and a dictionary registry. Using the same pattern for response decision strategies keeps the codebase consistent (Brownfield Rule 4) and makes it trivial to add new strategies later under the same contract.
- **`DecisionResult` fields**: `decision: Literal["respond", "skip"]`, `score: float | None`, `matched_terms: list[str]`, `rationale: str`, `error: str | None`. Maps directly to the `workspace_goal_decision_rationales` columns.

## Finding 5 — LLM client pattern

- **Decision**: Use `httpx.AsyncClient(timeout=30.0)` posting to `settings.<context>.llm_api_url`.
- **Rationale**: All existing LLM calls (e.g., `evaluation/scorers/llm_judge.py`) use httpx with a 30-second timeout. The existing LLM judge pattern of building a structured prompt and parsing the JSON response is the canonical approach. No new client wrapper is needed.
- **Error handling**: On httpx error or parse failure, the strategy returns `DecisionResult(decision="skip", error=str(exc))` — FR-022 fail-safe.

## Finding 6 — Embedding client pattern

- **Decision**: Use `httpx.AsyncClient` to `settings.memory.embedding_api_url` to get a vector, then `AsyncQdrantClient.search_vectors()` to find cosine similarity.
- **Rationale**: `discovery/proximity/embeddings.py` and `memory/` services use this exact pattern. The common `AsyncQdrantClient` in `common/clients/qdrant.py` already exposes `search_vectors(collection, query_vector, limit, filter)` returning scored results.
- **Collection for embedding-similarity strategy**: Uses `platform_memory` or a new `workspace_goal_embeddings` collection depending on whether reference embeddings are goal-scoped or agent-configured. Plan uses a configurable `collection` key in `response_decision_config` JSONB (defaulting to `platform_memory`).

## Finding 7 — FQN matching for AllowBlocklistDecision

- **Decision**: Use `fnmatch.fnmatch(term, pattern)` from stdlib.
- **Rationale**: `policies/gateway.py` already uses `fnmatch` for FQN pattern matching against allow/deny tool patterns. AllowBlocklistDecision uses the same approach for message-term-against-pattern matching, keeping stdlib usage consistent.

## Finding 8 — APScheduler auto-completion scanner pattern

- **Decision**: Add `GoalAutoCompletionScanner` as an `AsyncIOScheduler` job in `main.py`, mirroring the connectors retry scanner.
- **Rationale**: `main.py` already has `_build_connectors_worker_scheduler()` which registers interval jobs that create `AsyncSessionLocal()` per run, call a service method, and commit. The auto-completion scanner follows the same pattern: an `async def _run_goal_auto_complete_scan()` closure that calls `GoalLifecycleService.scan_and_complete_idle_goals(session)` every `settings.interactions.goal_auto_complete_scan_interval_seconds` seconds (default: 60).
- **Idempotency**: Scanner queries `workspaces_goals WHERE state='working' AND auto_complete_timeout_seconds IS NOT NULL AND last_message_at + auto_complete_timeout_seconds * interval '1 second' < NOW()`, then transitions each result atomically with a `SELECT FOR UPDATE SKIP LOCKED` to prevent double-transition under concurrent scanner replicas.

## Finding 9 — Latest Alembic migration and naming

- **Decision**: New migration is `046_workspace_goal_lifecycle_and_decision`.
- **Rationale**: Latest migration file is `045_oauth_providers_and_links` with `down_revision = "044_ibor_and_decommission"`. Next sequential number is 046. Migration name follows the `NNN_short_description` pattern already established.

## Finding 10 — GID correlation context

- **Decision**: Pass `goal_id=goal.id` to `make_envelope()` when emitting state-transition events.
- **Rationale**: `CorrelationContext` already has `goal_id: UUID | None` field (feature 052). `make_envelope()` in `common/events/envelope.py` accepts `goal_id` as a keyword argument and propagates it to the envelope. All lifecycle events (`workspace.goal.state_changed`) will carry `goal_id` in the envelope correlation context.
- **Kafka topic**: Emit on existing `workspace.goal` topic (already in the Kafka Topics Registry). No new topic needed for lifecycle events; goal_id in envelope distinguishes events by goal.

## Finding 11 — `workspace_goal_decision_rationales` location

- **Decision**: Add `WorkspaceGoalDecisionRationale` model to `interactions/models.py`.
- **Rationale**: Decision rationales are produced by the interactions bounded context when processing messages against goals. The `workspace_goal_messages` table (parent FK) also lives in `interactions/models.py`. Keeping rationale records in the same context avoids cross-boundary model imports. The FK to `workspaces_goals.id` is acceptable (already established by `workspace_goal_messages`).

## Finding 12 — Feature flag requirement (Brownfield Rule 8)

- **Decision**: The response decision engine is always-on (no flag needed); the auto-completion scanner requires a feature flag `FEATURE_GOAL_AUTO_COMPLETE` (default: false).
- **Rationale**: The lifecycle state transition and decision strategies do not change any existing default behavior (they are new columns with safe defaults: `state='ready'`, no auto-complete by default). The auto-completion scanner is a new background behavior that changes observable platform behavior and MUST be behind a feature flag per Brownfield Rule 8 for gradual rollout.
