# Implementation Plan: A2A Protocol Gateway

**Branch**: `065-a2a-protocol-gateway` | **Date**: 2026-04-19 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/065-a2a-protocol-gateway/spec.md`

## Summary

Implement the A2A Protocol Gateway as a new Python bounded context (`a2a_gateway/`) in the control plane. The gateway handles two directions: **server mode** (external A2A clients discover and invoke platform agents via auto-generated Agent Cards and a standard task lifecycle) and **client mode** (platform agents invoke registered external A2A endpoints through a policy-checked internal service interface). SSE streaming and multi-turn conversations are layered on top of the core task lifecycle. All inbound and outbound interactions pass through the existing auth, authorization, policy enforcement, output sanitization, and audit surfaces. Three new PostgreSQL tables (`a2a_tasks`, `a2a_external_endpoints`, `a2a_audit_records`) and one Kafka topic (`a2a.events`) are added via Alembic migration 052.

## Technical Context

**Language/Version**: Python 3.12+  
**Primary Dependencies**: FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, aiokafka 0.11+, redis-py 5.x async, httpx 0.27+, PyJWT 2.x — all already in requirements.txt  
**Storage**: PostgreSQL 16 (3 new tables via Alembic 052) + Redis (Agent Card cache + rate limiting)  
**Testing**: pytest + pytest-asyncio 8.x, ruff 0.7+, mypy 1.11+ strict  
**Target Platform**: Linux, Kubernetes  
**Project Type**: Web service — new bounded context in existing FastAPI monolith  
**Performance Goals**: Task acceptance ≤ 500ms p95 (SC-011); SSE event latency ≤ 1s p95 (SC-007); error rejection ≤ 100ms p95 (SC-010)  
**Constraints**: A2A external-only (FR-026 + Principle XIV); HTTPS-only outbound (FR-016); no revocation caching (FR-028); output sanitization on all responses (FR-010)  
**Scale/Scope**: New bounded context, ~10–12 source files, 1 migration, 1 Kafka topic

## Constitution Check

*All principles checked against this feature design.*

| Gate | Status | Notes |
|------|--------|-------|
| **Principle I** — Modular monolith | ✅ PASS | New bounded context inside existing Python monolith |
| **Principle III** — Dedicated data stores | ✅ PASS | PostgreSQL for durable state; Redis for cache/rate-limit hot state; no in-memory shared state |
| **Principle IV** — No cross-boundary DB access | ✅ PASS | Reads registry via internal service interface; creates interactions via InteractionsRepository |
| **Principle VI** — Policy is machine-enforced | ✅ PASS | ToolGatewayService enforces inbound authz and outbound policy; no markdown-only enforcement |
| **Principle VIII** — FQN addressing | ✅ PASS | agent_fqn used throughout; A2A name field derived from FQN |
| **Principle IX** — Zero-trust default visibility | ✅ PASS | Inbound requests pass through authorization check before any agent invocation |
| **Principle XI** — Secrets never in LLM context | ✅ PASS | OutputSanitizer applied to all A2A responses (FR-010) |
| **Principle XIV** (A2A external-only) | ✅ PASS | FR-026 explicitly bars internal A2A use; gateway is sole ingress/egress |
| **Brownfield Rule 2** — Alembic migrations | ✅ PASS | All DDL in migration 052 |
| **Brownfield Rule 4** — Use existing patterns | ✅ PASS | Service/repo/schema pattern; EventEnvelope; AsyncRedisClient; ToolGatewayService |
| **Reminder 25** — No MinIO in app code | ✅ PASS | No object storage needed for A2A gateway |
| **Reminder 29** — No MinIO in app code | ✅ PASS | N/A for this bounded context |

## Project Structure

### Documentation (this feature)

```text
specs/065-a2a-protocol-gateway/
├── plan.md              ✅ This file
├── research.md          ✅ Phase 0 output
├── data-model.md        ✅ Phase 1 output
├── quickstart.md        ✅ Phase 1 output
├── contracts/
│   └── rest-api.md      ✅ Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks — not yet created)
```

### Source Code

```text
apps/control-plane/
├── migrations/versions/
│   └── 052_a2a_gateway.py              # NEW: 3 tables + 2 enums
└── src/platform/
    ├── a2a_gateway/                    # NEW bounded context
    │   ├── __init__.py
    │   ├── models.py                   # A2ATask, A2AExternalEndpoint, A2AAuditRecord + enums
    │   ├── schemas.py                  # Pydantic request/response schemas
    │   ├── repository.py               # DB operations for all 3 tables
    │   ├── card_generator.py           # Build Agent Card JSON from AgentProfile + AgentRevision
    │   ├── server_service.py           # Inbound task lifecycle (server mode)
    │   ├── client_service.py           # Outbound call orchestration (client mode)
    │   ├── external_registry.py        # External Agent Card cache (Redis + DB fallback)
    │   ├── streaming.py                # SSE StreamingResponse generator
    │   ├── exceptions.py               # A2A-specific exceptions
    │   ├── events.py                   # Kafka event publishing (a2a.events topic)
    │   └── router.py                   # FastAPI endpoints (8 routes)
    ├── main.py                         # MODIFY: mount a2a_gateway_router
    └── policies/
        └── gateway.py                  # EXISTING: reused for outbound policy check
```

## Complexity Tracking

No constitution violations. All existing surfaces reused.

## Phase 0: Research

**Status**: ✅ Complete — see [research.md](research.md)

Key decisions:
- D-001: New `a2a_tasks` table + FK to interactions (not interaction extension)
- D-002: Starlette `StreamingResponse` for SSE (no new library)
- D-003: Outbound policy via `ToolGatewayService.validate_tool_invocation(tool_fqn="a2a:{endpoint_id}")`
- D-004: Agent Card from `AgentProfile.fqn/purpose` + `AgentRevision.manifest_snapshot`
- D-005: Inbound auth via `AuthService.validate_token()` — no revocation caching
- D-006: Redis key `cache:a2a_card:{sha256(url)[:16]}` + DB durable fallback
- D-007: New `a2a_audit_records` table; dual-write denials to `PolicyBlockedActionRecord`
- D-008: Rate limiting via `AsyncRedisClient.check_rate_limit("a2a", str(principal_id), ...)`
- D-009: Multi-turn backed by Conversation + one Interaction per turn; `input_required` → `InteractionState.waiting`
- D-010: New Kafka topic `a2a.events` with 7 event types
- D-011: Migration `052_a2a_gateway.py`
- D-012: Protocol version from `PlatformSettings.A2A_PROTOCOL_VERSION`

## Phase 1: Design & Contracts

**Status**: ✅ Complete

- [data-model.md](data-model.md) — 3 new tables, 2 new enums, Redis keys, Kafka events
- [contracts/rest-api.md](contracts/rest-api.md) — 8 HTTP endpoints + internal service interface
- [quickstart.md](quickstart.md) — 25 acceptance scenarios (S1–S25)
