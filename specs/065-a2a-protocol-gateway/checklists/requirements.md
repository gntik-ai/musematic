# Specification Quality Checklist: A2A Protocol Gateway

**Purpose**: Validate specification completeness and quality before proceeding to planning  
**Created**: 2026-04-19  
**Feature**: [spec.md](../spec.md)

## Content Quality

- [X] No implementation details (languages, frameworks, APIs) — spec uses logical domain terms: `Agent Card`, `A2A task`, `task lifecycle`, `SSE streaming`, `policy enforcement`, `output sanitization`. The user-input brownfield file list mentions `a2a_gateway/__init__.py` and similar Python module names; those paths stay in the input context, not the spec body.
- [X] Focused on user value and business needs — each user story frames a concrete persona (external client, platform agent invoking external, security officer, SSE-consuming client, platform operator) with a delivered outcome (interoperability, security, streaming UX, caching).
- [X] Written for non-technical stakeholders — plain language: "Agent Card is the public discovery document describing available agents", "SSE streaming emits lifecycle events as they occur", "outbound calls are policy-checked before any network request".
- [X] All mandatory sections completed — User Scenarios (5 stories), Requirements (29 FRs + 7 entities), Success Criteria (14 SCs) all populated.

## Requirement Completeness

- [X] No [NEEDS CLARIFICATION] markers remain — defaults chosen explicitly: Agent Card auto-generation from registry (FR-002), propagation window 5 minutes (SC-001), outbound HTTPS-only (FR-016), public Agent Card world-readable (Assumption), cache TTL default 1 hour (Assumption), input-required idle timeout 30 minutes (Assumption), max payload 10 MB (Assumption), single pinned A2A protocol version (Assumption + FR-020), SSE as sole streaming transport (Assumption + Out of Scope), registration privileged to operators (Assumption), anonymous Agent Card discovery (Assumption).
- [X] Requirements are testable and unambiguous — each FR uses MUST/MUST NOT with verifiable conditions (FR-008 "rejected without invoking the agent"; FR-009 "denials MUST be recorded in the audit log"; FR-016 "non-HTTPS destinations MUST be denied regardless of allowed-list membership"; FR-019 "MUST NOT disclose internal stack traces, internal agent names not present in the public Agent Card, or secret values"; FR-026 "MUST NOT be used for communication between platform agents").
- [X] Success criteria are measurable — SC-001/002/003/004/005/006/009/013/014 (100%); SC-007 (p95 ≤ 1 s); SC-008 (≥ 90% cache hit rate); SC-010 (p95 ≤ 100 ms rejection latency); SC-011 (p95 ≤ 500 ms task acceptance latency); SC-012 (≥ 99% multi-turn resume rate on controlled suite).
- [X] Success criteria are technology-agnostic — phrased as user-observable outcomes (task acceptance latency, cache hit rate, fail-closed denial rate, audit completeness) without naming FastAPI, HTTP libraries, Redis, databases, or specific SDK implementations.
- [X] All acceptance scenarios are defined — 5 user stories × 5–6 Given/When/Then scenarios each (US1: 6; US2: 5; US3: 6; US4: 5; US5: 5).
- [X] Edge cases are identified — 13 edge cases: archived/revoked agent mid-task, unsupported external capability, non-existent FQN, non-cancellable mid-step, SSE duration limit, abandoned multi-turn, oversized payload, HTTP-only destination, revoked token, duplicate simultaneous tasks, incomplete registry metadata, expired external TTL mid-invocation, protocol version mismatch.
- [X] Scope is clearly bounded — explicit Out of Scope: internal A2A, version multiplexing, WebSocket streaming, custom protocol extensions, UI surface, federation handshake, cross-platform Agent Card index, automated discovery, A2A-specific billing, advanced retry policies, distributed transactions.
- [X] Dependencies and assumptions identified — Dependencies lists agent registry, authentication, authorization, interaction model, output sanitization, audit log, policy engine, caching. Assumptions cover protocol faithfulness, existing registry/auth/policy/sanitization/audit surfaces, interaction-model reuse, SSE as transport, anonymous Agent Card discovery, operator-privileged registration, configurable defaults (TTL/idle timeout/payload size), single pinned protocol version, A2A-unaware platform agents, gateway as sole A2A ingress/egress.

## Feature Readiness

- [X] All functional requirements have clear acceptance criteria — each FR maps to user-story scenarios or edge cases (FR-001–FR-005, FR-027 → US1; FR-006, FR-013, FR-014, FR-015, FR-021 → US2 + US5; FR-007–FR-010, FR-017, FR-018, FR-028 → US3; FR-011, FR-012, FR-023, FR-024 → US4; FR-016, FR-019, FR-020, FR-022, FR-025, FR-026, FR-029 → cross-cutting).
- [X] User scenarios cover primary flows — server-mode discovery + invocation (US1), client-mode invocation (US2), policy enforcement (US3), streaming + multi-turn (US4), external endpoint caching (US5).
- [X] Feature meets measurable outcomes defined in Success Criteria — 14 SCs cover Agent Card freshness, exclusion enforcement, auth+authz gating, outbound policy gating, sanitization coverage, audit completeness, streaming latency, cache hit rate, lifecycle completeness, error-rejection latency, acceptance latency, multi-turn resume rate, fail-closed denial rate, no internal regression.
- [X] No implementation details leak into specification — entities described as logical records (Agent Card, A2A Task, A2A Task Status, A2A Message, External A2A Endpoint Registration, A2A Audit Record, Agent Card Cache Entry) without FastAPI/Pydantic/SQLAlchemy/Redis names in the body.

## Notes

- All items pass on the first validation pass — no iteration required.
- A2A is strictly external-only (FR-026 + Out of Scope + Reminder 21 of the constitution) — the gateway is NOT a substitute for internal agent coordination.
- Agent Card auto-generation (FR-002) is an operator-ergonomic decision: hand-authored cards would drift from registry state; auto-gen guarantees the public surface always reflects the live registry.
- Output sanitization applies in BOTH directions (FR-010) — results going out to external clients AND results coming in from external agents into platform agent contexts — to keep secret-leak protection consistent at the boundary.
- HTTPS-only outbound (FR-016) is absolute and NOT overridable by policy — operator cannot allow-list an HTTP endpoint. Rationale: HTTP-on-the-wire for external agent calls is a data-exfiltration risk that no operational convenience justifies.
- Authentication token revocation is checked on every request (FR-028 + edge case) — session-level caching of revocation status is explicitly disallowed for A2A.
- Audit records cover BOTH success AND failure (FR-018 + SC-006) — denied calls are as audit-relevant as accepted ones; otherwise security teams cannot reconstruct a timeline of attempted-but-blocked activity.
- Multi-turn conversation idle timeout defaults to 30 minutes (Assumption) — longer than typical interactive flows, shorter than abandoned-task dwell costs.
- A2A payload size default 10 MB (Assumption) — aligns with common external-integration payload caps and prevents memory pressure from pathological external clients.
- Single pinned A2A protocol version (Assumption + FR-020) — multiplexing support is Out of Scope; if the A2A protocol evolves, a later feature can add version negotiation.
- External Agent Card TTL default 1 hour (Assumption) — balances freshness against external API pressure; ≥ 90% cache-hit target (SC-008) validates the TTL choice under real usage.
- Spec is ready for `/speckit.plan` — no clarifications needed.
