# Implementation Plan: End-to-End Testing on kind (Kubernetes in Docker)

**Branch**: `071-e2e-kind-testing` | **Date**: 2026-04-20 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/071-e2e-kind-testing/spec.md`

## Summary

New `tests/e2e/` tree at the repository root provides an ephemeral Kubernetes-in-Docker (kind) harness that installs the platform via **the same Helm chart as production** (values-e2e.yaml overlay only), seeds deterministic baseline data, and runs pytest-based suites organized by bounded context, chaos scenarios, and performance smoke tests. A feature-flagged (`FEATURE_E2E_MODE`) dev-only router under `/api/v1/_e2e/*` is mounted in the `testing/` bounded context to provide seeding, reset, chaos injection, mock-LLM queue control, and Kafka event inspection — all endpoints return 404 in production. A mock LLM provider wired into `common/llm/` returns deterministic responses from a FIFO queue so tests are fully reproducible without real LLM API calls. CI runs the full suite on every PR and nightly on main, uploading JUnit XML, HTML reports, log tails, and a state dump for post-failure triage.

## Technical Context

**Language/Version**: Python 3.12+ (test harness + platform dev-only endpoints); YAML (Helm overlay + kind-config + GitHub Actions); Bash (Makefile + image-load scripts)
**Primary Dependencies**: kind ≥ 0.23, kubectl ≥ 1.28, helm ≥ 3.14, Docker ≥ 24 (host prerequisites); pytest 8.x, pytest-asyncio, pytest-html, pytest-timeout, httpx 0.27+, websockets, aiokafka 0.11+, asyncpg (direct DB assertion path distinct from SQLAlchemy), python-on-whales (optional, for container inspection); existing Helm chart at `deploy/helm/platform/` — no fork
**Storage**: None directly owned — the harness orchestrates existing data stores (PostgreSQL via CloudNativePG chart dependency, Redis, Kafka/Strimzi, MinIO, Qdrant, Neo4j, ClickHouse, OpenSearch) installed by the existing platform Helm chart
**Testing**: pytest is the test framework under test here; the harness itself is validated by CI green runs across 20+ suites + 6 chaos scenarios + 4 performance smoke tests. A determinism test (`test_mock_llm_deterministic.py`) ensures mock-LLM output byte-identity across 10 runs (SC-008). A chart-identity test verifies no separate `Chart.yaml` under `tests/e2e/` (SC-010).
**Target Platform**: Linux developer workstation (≥ 16 GB RAM, Docker ≥ 24, kind ≥ 0.23) for local runs; GitHub Actions `ubuntu-latest-8-cores` runner (≥ 16 GB RAM, 8 cores) for CI. macOS developer support is best-effort (Docker Desktop's memory allocation often limits kind cluster size).
**Project Type**: Test harness + platform extension. Two integration surfaces: (1) new `tests/e2e/` tree at repo root (harness only — not packaged or deployed), (2) additive code in the `testing/` bounded context (`testing/router_e2e.py`, gated mount in `main.py`) + `common/llm/mock_provider.py` + `FEATURE_E2E_MODE` flag in `common/config.py`.
**Performance Goals**: Full provisioning (cluster + Helm + seed) ≤ 10 minutes on 16 GB laptop (SC-001); CI workflow ≤ 45 minutes (SC-006); warm launch < 2 s, cold launch < 10 s, trivial round-trip < 5 s, reasoning overhead < 50 ms/step (SC-005).
**Constraints**: **Same Helm chart as production** (SC-010) — no alternate chart allowed. Zero residual artifacts after teardown (SC-002). Dev-only endpoints MUST return 404 when `FEATURE_E2E_MODE=false` (SC-007). Multiple parallel clusters supported via `CLUSTER_NAME` + port-range parameterization (SC-009). Mock LLM MUST be the only LLM path when enabled — zero real API calls.
**Scale/Scope**: 16+ bounded-context suites (auth, registry, trust, governance, interactions, workflows, fleets, reasoning, evaluation, agentops, discovery, a2a, mcp, runtime, storage, ibor — matches the constitution's context list) + 6 chaos scenarios + 4 performance smoke tests. ~60 test files, ~20 fixture/seeder files, 1 kind config, 1 Helm overlay, 1 Makefile, 1 GitHub Actions workflow. Target total test count: ≥ 50 distinct tests.

## Constitution Check

| Gate | Status | Notes |
|------|--------|-------|
| **Principle I** — Modular monolith | ✅ PASS | Dev-only endpoints live in existing `testing/` bounded context; no new context created |
| **Principle III** — Dedicated data stores | ✅ PASS | E2E overlay installs all production stores; tests assert against real stores |
| **Principle IV** — No cross-boundary DB access | ✅ PASS | Test code uses the direct `asyncpg` `db` fixture for read-only assertions; platform code still respects boundaries |
| **Principle V** — Append-only execution journal | ✅ PASS | Reset endpoint wipes execution records via repository-layer truncation, never mutates in place |
| **Principle VI** — Policy is machine-enforced | ✅ PASS | E2E tests exercise the real tool gateway, memory write gate, and approval systems |
| **Principle VII** — Simulation isolation | ✅ PASS | `platform-simulation` namespace created by the same Helm chart; simulation suite exercises isolation |
| **Principle VIII** — FQN addressing | ✅ PASS | Agent seeder registers every agent with a namespace:local_name FQN |
| **Principle IX** — Zero-trust default visibility | ✅ PASS | Overlay sets `features.zeroTrustVisibility: true` to catch regressions |
| **Principle X** — GID correlation | ✅ PASS | `workspace_goals` seeder creates goals across lifecycle states for GID assertions |
| **Principle XI** — Secrets never in LLM context | ✅ PASS | Mock LLM verifies no secret values appear in recorded prompts |
| **Principle XIII** — Attention pattern | ✅ PASS | Interactions suite tests `interaction.attention` topic end-to-end |
| **Principle XIV** — A2A external only | ✅ PASS | a2a suite tests Agent Card + server task lifecycle |
| **Principle XV** — MCP via tool gateway | ✅ PASS | mcp suite verifies client discovery and server exposure go through the gateway |
| **Principle XVI** — Generic S3, MinIO optional | ✅ PASS | Overlay uses generic S3 env vars pointing at MinIO in-cluster; identical code path as production |
| **Brownfield Rule 1** — Never rewrite | ✅ PASS | Dev-only endpoints are additive; mock LLM provider is additive alongside real providers |
| **Brownfield Rule 2** — Alembic migrations | ⚠️ N/A | No schema changes. `FEATURE_E2E_MODE` is a runtime flag only |
| **Brownfield Rule 3** — Preserve existing tests | ✅ PASS | Existing unit + integration suites unaffected; new suite runs in parallel |
| **Brownfield Rule 4** — Use existing patterns | ✅ PASS | `testing/router_e2e.py` follows FastAPI router convention; mock LLM follows existing provider interface |
| **Brownfield Rule 5** — Reference existing files | ✅ PASS | Plan cites exact files modified (`common/config.py`, `main.py`, `testing/`, `common/llm/`) |
| **Brownfield Rule 7** — Backward-compatible | ✅ PASS | Dev endpoints 404 when flag off — production API surface unchanged |
| **Brownfield Rule 8** — Feature flags | ✅ PASS | `FEATURE_E2E_MODE` is THE flag; default `false` in production |
| **Reminder 25** — No MinIO in app code | ✅ PASS | Overlay sets `S3_ENDPOINT_URL` to MinIO service; app code uses generic S3 client |
| **Reminder 26** — E2E on kind | ✅ PASS | This feature realizes Reminder 26 — same Helm charts, gated `/api/v1/_e2e/*` endpoints |

No constitution violations.

## Project Structure

### Documentation (this feature)

```text
specs/071-e2e-kind-testing/
├── plan.md                   ✅ This file
├── spec.md                   ✅ Feature specification
├── research.md               ✅ Phase 0 output
├── data-model.md             ✅ Phase 1 output (seeded entities + endpoint contracts)
├── quickstart.md             ✅ Phase 1 output (6 acceptance-scenario walkthroughs)
├── contracts/
│   ├── e2e-endpoints.md      ✅ Phase 1 output (HTTP contracts for /api/v1/_e2e/*)
│   ├── fixtures-api.md       ✅ Phase 1 output (pytest fixture surface)
│   └── helm-overlay.md       ✅ Phase 1 output (values-e2e.yaml schema)
└── checklists/
    └── requirements.md       ✅ Spec validation (all pass)
```

### Source Code (tests/e2e/ at repo root + additive platform code)

```text
# NEW — E2E harness at repo root
tests/e2e/
├── Makefile                              # e2e-up, e2e-down, e2e-test, e2e-chaos, e2e-perf, e2e-reset, e2e-logs, e2e-shell, capture-state
├── conftest.py                           # Session fixtures, autouse seeder trigger, URL constants
├── pyproject.toml                        # Harness-only Python deps (pytest, httpx, aiokafka, asyncpg, websockets)
├── README.md                             # Quickstart for contributors
├── cluster/
│   ├── kind-config.yaml                  # 1 control-plane + 2 workers + port mappings
│   ├── values-e2e.yaml                   # Helm overlay (scaled-down + flags)
│   ├── load-images.sh                    # Build + kind load docker-image for all platform images
│   ├── install.sh                        # One-shot kind create + helm install + wait-ready
│   └── capture-state.sh                  # Dump pods + events + helm status + log tails
├── fixtures/
│   ├── __init__.py
│   ├── http_client.py                    # Authenticated async httpx client
│   ├── ws_client.py                      # WebSocket client (`websockets` library)
│   ├── db_session.py                     # Direct asyncpg session (assertion-only)
│   ├── kafka_consumer.py                 # aiokafka consumer with test-window filtering
│   ├── workspace.py                      # create_workspace factory + teardown
│   ├── agent.py                          # register_agent factory with FQN
│   ├── policy.py                         # attach_policy factory
│   └── mock_llm.py                       # Helpers: set_response, get_calls, clear
├── seeders/
│   ├── base.py                           # SeederBase (idempotent); CLI entrypoint (python -m seeders.base --all|--reset)
│   ├── users.py                          # admin, operator1, operator2, end_user1
│   ├── namespaces.py                     # default, test-finance, test-eng
│   ├── agents.py                         # One agent per role_type with valid FQN + visibility
│   ├── tools.py                          # Mock HTTP tool + mock code tool
│   ├── policies.py                       # Sample allow/deny policies
│   ├── certifiers.py                     # Internal + third-party
│   ├── fleets.py                         # Small fleet (3 agents) for coordination
│   └── workspace_goals.py                # Goals in open / in_progress / completed / cancelled states
├── suites/
│   ├── auth/                             # US2 coverage — test_local_auth, test_mfa, test_google_oauth, test_github_oauth, test_session_lifecycle
│   ├── registry/                         # test_namespace_crud, test_fqn_registration, test_fqn_resolution, test_pattern_discovery, test_visibility_zero_trust, test_visibility_workspace_grants
│   ├── trust/                            # test_pre_screener, test_secret_sanitization, test_certification_workflow, test_contract_compliance, test_third_party_certifier, test_surveillance
│   ├── governance/                       # test_observer_judge_enforcer_pipeline, test_verdict_issuance, test_enforcement_actions
│   ├── interactions/                     # test_conversation_lifecycle, test_workspace_goal_lifecycle, test_gid_correlation, test_response_decision, test_attention_request, test_user_alerts
│   ├── workflows/                        # test_execution_end_to_end, test_checkpoint_rollback, test_reprioritization
│   ├── fleets/                           # test_fleet_orchestration, test_fleet_coordination
│   ├── reasoning/                        # test_cot, test_tot, test_react, test_cod, test_self_correction, test_compute_budget
│   ├── evaluation/                       # test_trajectory_scorer, test_llm_judge, test_ab_testing
│   ├── agentops/                         # test_adaptation_proposal, test_canary_deployment
│   ├── discovery/                        # test_proximity_graph
│   ├── a2a/                              # test_agent_card_generation, test_server_task_lifecycle, test_sse_streaming, test_client_mode
│   ├── mcp/                              # test_client_discovery, test_server_exposure
│   ├── runtime/                          # test_warm_pool, test_secrets_injection
│   ├── storage/                          # test_generic_s3_upload_download, test_lifecycle
│   └── ibor/                             # test_ibor_sync (uses mock LDAP)
├── chaos/                                # US3 coverage
│   ├── test_runtime_pod_kill.py
│   ├── test_reasoning_engine_kill.py
│   ├── test_kafka_broker_restart.py
│   ├── test_s3_credential_revoke.py
│   ├── test_network_partition.py
│   └── test_policy_timeout.py
├── performance/                          # US4 coverage
│   ├── test_launch_latency.py
│   ├── test_execution_roundtrip.py
│   ├── test_concurrent_throughput.py
│   └── test_reasoning_overhead.py
└── reports/                              # Generated artifacts (gitignored): junit.xml, report.html, state-dump.txt, pod-logs/

# EXTENDED — Platform control plane (additive files)
apps/control-plane/src/platform/
├── common/
│   ├── config.py                         # MODIFY: add `feature_e2e_mode: bool = False` field
│   └── llm/
│       ├── __init__.py                   # existing
│       ├── mock_provider.py              # NEW: MockLLMProvider (FIFO queue + streaming + call recording)
│       └── router.py                     # MODIFY: route to MockLLMProvider when feature_e2e_mode + mockLLM.enabled
├── testing/
│   ├── router_e2e.py                     # NEW: 6 dev-only endpoints under /api/v1/_e2e/*
│   ├── service_e2e.py                    # NEW: seeding/reset/chaos/kafka helpers (admin-scoped)
│   └── schemas_e2e.py                    # NEW: request/response shapes
├── main.py                               # MODIFY: conditionally mount router_e2e when FEATURE_E2E_MODE=true
└── tests/unit/
    ├── testing/
    │   └── test_router_e2e_404_when_flag_off.py   # NEW: static contract test enumerating endpoints
    └── common/llm/
        └── test_mock_provider.py                   # NEW: FIFO + streaming + recording + determinism

# EXTENDED — Helm (additive overlay only)
deploy/helm/platform/
└── values.yaml                           # UNMODIFIED — production values

# NEW — overlay lives under tests/e2e/cluster/values-e2e.yaml (see above)

# EXTENDED — CI
.github/workflows/
└── e2e.yml                               # NEW: PR + nightly schedule + artifact upload + auto-issue on 3 consecutive nightly failures
```

### Key Architectural Boundaries

- **Harness is not shipped.** Nothing under `tests/e2e/` is packaged into any container image or published. It exists only to orchestrate kind clusters from a developer workstation or CI runner.
- **Platform code changes are minimal and additive.** One config field, one router, one mock provider, one conditional mount. All 404-when-off by default.
- **Helm chart is production's chart.** The overlay lives under `tests/e2e/cluster/values-e2e.yaml` and is passed via `-f` to `helm install`. A chart-identity test (`test_no_separate_chart`) fails the CI if a `Chart.yaml` is ever introduced under `tests/e2e/` (SC-010 enforcement).
- **`tests/e2e/` vs `apps/control-plane/tests/e2e/`.** The existing `apps/control-plane/tests/e2e/` directory (referenced in the constitution as the per-context pytest location) is a legacy naming collision. This feature's harness lives at repository root `tests/e2e/` — it is NOT the same tree. Research D-004 documents the rename/coexistence decision.

## Complexity Tracking

No constitution violations.

**Highest-risk areas**:

1. **kind provisioning flakes under CI resource pressure.** A 16 GB runner running kind + full platform Helm chart is tight. Mitigation: `values-e2e.yaml` scales every stateful component to 1 replica with reduced resource requests; Kafka uses KRaft (no ZooKeeper); Neo4j + ClickHouse + OpenSearch are single-node; autoscaling disabled. Retry-once-on-transient-failure at cluster create step in CI workflow.
2. **Provisioning exceeds 10-minute budget.** Target: cluster create (< 90 s) + image load (< 120 s) + helm install --wait (< 300 s) + seed (< 60 s) = ~570 s ≈ 9.5 min. Mitigation: parallel image loads; `helm install --wait --timeout 10m` with per-pod readiness gates; seeder runs as single batch with bulk SQL inserts. Capture-state on timeout surfaces the bottleneck subchart.
3. **Mock LLM determinism across processes.** Multiple pods may route LLM calls; each must receive responses from the same queue in the same order. Mitigation: the queue is backed by a deterministic per-prompt-template fallback — pods never "steal" queued responses across prompts, so ordering is preserved by prompt, not globally. Determinism test (`test_mock_llm_deterministic.py`) asserts byte-identity across 10 runs (SC-008).
4. **Dev-only endpoint leak into production.** If `FEATURE_E2E_MODE` is accidentally set true in prod, chaos endpoints could take down a cluster. Mitigations: (a) `testing/router_e2e.py` requires admin-scoped bearer token in addition to flag (defense in depth); (b) static contract test (`test_router_e2e_404_when_flag_off.py`) enumerates every endpoint and asserts 404 in default config — prevents regression; (c) chart-level check refuses to install with `features.e2eMode: true` if `global.environment == "production"`.
5. **Chaos scenario cluster damage.** A NetworkPolicy or killed pod could leave subsequent suites in a broken state. Mitigation: every chaos test uses a `try/finally` teardown that explicitly reverses the injected failure (delete NetworkPolicy by label, delete any created test-scoped resources). `e2e-chaos` runs as a separate pytest invocation from `e2e-test` so a chaos failure does not poison baseline suites.

## Phase 0: Research

**Status**: ✅ Complete — see [research.md](research.md)

Key decisions:

- **D-001**: Use kind ≥ 0.23 for Kubernetes-in-Docker orchestration — not k3d, not minikube. Single cross-platform binary, native support for port mappings, well-supported `kind load docker-image`, and GitHub Actions has the `helm/kind-action` first-class step.
- **D-002**: Reuse the production Helm chart at `deploy/helm/platform/` without fork. All E2E-specific settings go into `tests/e2e/cluster/values-e2e.yaml` as a Helm values overlay. A chart-identity test enforces that no `Chart.yaml` appears under `tests/e2e/`.
- **D-003**: Use asyncpg (direct PostgreSQL client) for DB assertion fixtures — not SQLAlchemy. The harness needs raw SQL access for state checks across bounded contexts; SQLAlchemy's ORM layer adds unnecessary coupling and slows assertion latency.
- **D-004**: The harness root is `tests/e2e/` at the repository root. The existing `apps/control-plane/tests/e2e/` directory is renamed to `apps/control-plane/tests/integration/` as part of this feature (migration is mechanical — no test logic changes). Document this rename in CHANGELOG; update CI matrix.
- **D-005**: Mock LLM provider follows the existing `llm.BaseProvider` interface. It accepts responses via `POST /api/v1/_e2e/mock-llm/set-response` (FIFO queue), falls back to a default deterministic response matched by prompt template, and records every call for post-test assertions. Streaming mode yields response chunks as SSE.
- **D-006**: Dev-only endpoints require BOTH `FEATURE_E2E_MODE=true` AND an admin/service-account bearer token with explicit `e2e` scope. Defense in depth: the flag guards the router mount; the auth middleware guards each endpoint.
- **D-007**: Chaos injection uses Kubernetes NetworkPolicies + `kubectl delete pod` via the in-cluster ServiceAccount. The `testing/service_e2e.py` wraps `kubernetes` Python client calls, scoped to the platform-execution + platform-data namespaces only. The harness never touches `kube-system` or other non-platform namespaces (FR-024).
- **D-008**: CI uses GitHub Actions `ubuntu-latest-8-cores` runner with `helm/kind-action@v1` for cluster provisioning. Concurrency group `e2e-${{ github.head_ref }}` ensures in-flight runs on the same PR cancel. Nightly schedule runs with `cron: "0 3 * * *"` against main.
- **D-009**: Reports use pytest-html + JUnit XML. On failure, `capture-state.sh` dumps pod list, events (all namespaces filtered by label `app.kubernetes.io/part-of=amp`), Helm release status, and last 100 log lines per platform pod. All uploaded as a single artifact bundle.
- **D-010**: Multiple parallel clusters on the same host are supported via `CLUSTER_NAME` env var (passed through the Makefile). Port mappings in `kind-config.yaml` are Jinja-templated at `e2e-up` time from `PORT_UI`/`PORT_API`/`PORT_WS` env vars (defaults 8080/8081/8082). Two clusters can coexist with non-overlapping port ranges.
- **D-011**: Seeders are idempotent via `INSERT … ON CONFLICT DO NOTHING` (PostgreSQL) or provider-specific upsert patterns. Rerun produces no duplicate rows. `--reset` flag wipes only E2E-scoped rows (workspace names prefixed `test-`, user emails `*@e2e.test`).
- **D-012**: The performance suite captures wall-clock timings in pytest markers, asserts against named thresholds, and writes a `performance.json` artifact with measured vs. expected values. Thresholds are defined in a single `performance/thresholds.py` module for one-stop tuning.

---

## Phase 1: Design & Contracts

**Status**: ✅ Complete

- [data-model.md](data-model.md) — Seeded entity shapes (users, namespaces, agents, tools, policies, certifiers, fleets, goals), dev-only endpoint request/response schemas, mock LLM call record shape, performance threshold constants, chaos scenario inputs/outputs.
- [contracts/e2e-endpoints.md](contracts/e2e-endpoints.md) — Full HTTP contracts for the 6 dev-only endpoints (paths, methods, request bodies, response codes including 404-when-off, auth requirements).
- [contracts/fixtures-api.md](contracts/fixtures-api.md) — Pytest fixture surface: `http_client`, `ws_client`, `db`, `kafka_consumer`, `workspace`, `agent`, `policy`, `mock_llm` — signatures + scope + teardown behavior.
- [contracts/helm-overlay.md](contracts/helm-overlay.md) — Schema of `values-e2e.yaml`: every key that differs from production values, with rationale and reference to the production default.
- [quickstart.md](quickstart.md) — 6 acceptance-scenario walkthroughs (Q1–Q6, one per user story) with exact commands and expected output.
