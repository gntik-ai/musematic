# Tasks: End-to-End Testing on kind (Kubernetes in Docker)

**Input**: Design documents from `specs/071-e2e-kind-testing/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/e2e-endpoints.md ✅, contracts/fixtures-api.md ✅, contracts/helm-overlay.md ✅, quickstart.md ✅

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US6)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the `tests/e2e/` directory skeleton and harness-level configuration at the repository root.

- [X] T001 Create tests/e2e/ directory skeleton with subdirs cluster/, fixtures/, seeders/, suites/auth/, suites/registry/, suites/trust/, suites/governance/, suites/interactions/, suites/workflows/, suites/fleets/, suites/reasoning/, suites/evaluation/, suites/agentops/, suites/discovery/, suites/a2a/, suites/mcp/, suites/runtime/, suites/storage/, suites/ibor/, chaos/, performance/, reports/
- [X] T002 Create tests/e2e/pyproject.toml with harness-only Python dependencies: pytest>=8.0, pytest-asyncio, pytest-html, pytest-timeout, httpx>=0.27, websockets, aiokafka>=0.11, asyncpg, kubernetes (Python client for chaos service)
- [X] T003 [P] Create tests/e2e/reports/.gitkeep and add tests/e2e/reports/ entry to root .gitignore

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Platform-side feature flag, mock LLM provider, dev-only router, and seeder base — all must exist before any user story work can run end-to-end.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 Add `feature_e2e_mode: bool = False` field to `PlatformSettings` in apps/control-plane/src/platform/common/config.py (sourced from env var `FEATURE_E2E_MODE`; default False for production safety)
- [X] T005 [P] Create apps/control-plane/src/platform/common/llm/mock_provider.py implementing the existing `BaseProvider` interface: per-prompt-template FIFO queue (Redis-backed `e2e:mock_llm:queue:{template}`), streaming SSE chunk mode, call recording to Redis list `e2e:mock_llm:calls`, default deterministic fallback response per template, Redis pub/sub broadcast on `e2e:mock_llm:set` for multi-pod consistency
- [X] T006 [P] Create apps/control-plane/src/platform/testing/schemas_e2e.py (Pydantic v2 models: SeedRequest/SeedResponse, ResetRequest/ResetResponse, ChaosKillPodRequest/ChaosKillPodResponse, ChaosPartitionRequest/ChaosPartitionResponse, MockLLMSetRequest/MockLLMSetResponse, KafkaEventsResponse per contracts/e2e-endpoints.md)
- [X] T007 Create apps/control-plane/src/platform/testing/service_e2e.py (SeedService calling individual domain seeders, ResetService scoped to E2E rows only with E2E_SCOPE_VIOLATION guard, ChaosService wrapping `kubernetes` Python client to kill pods and apply NetworkPolicies restricted to platform-execution and platform-data namespaces, KafkaObserver seeking by timestamp for event inspection)
- [X] T008 Create apps/control-plane/src/platform/testing/router_e2e.py (FastAPI router with 6 endpoints: POST /seed, POST /reset, POST /chaos/kill-pod, POST /chaos/partition-network, POST /mock-llm/set-response, GET /kafka/events; all depend on `require_admin_or_e2e_scope` dependency; use platform canonical error envelope for non-2xx responses per contracts/e2e-endpoints.md)
- [X] T009 Modify apps/control-plane/src/platform/main.py to conditionally `from platform.testing.router_e2e import router as e2e_router; app.include_router(e2e_router, prefix="/api/v1/_e2e", tags=["_e2e"])` only when `settings.feature_e2e_mode is True`
- [X] T010 [P] Create tests/e2e/seeders/base.py (abstract SeederBase class with idempotent `seed()` and `reset()` methods; CLI entrypoint `python -m seeders.base --all|--reset` iterating all domain seeders in dependency order)

**Checkpoint**: Platform boots with `FEATURE_E2E_MODE=false` (all `_e2e` endpoints absent). Boots with `FEATURE_E2E_MODE=true` (all 6 endpoints mounted). Seeder base CLI callable.

---

## Phase 3: User Story 1 — Developer provisions the full platform on kind (Priority: P1) 🎯 MVP

**Goal**: Single `make e2e-up` command provisions a working kind cluster with the production Helm chart, loads local images, and seeds all baseline entities within 10 minutes.

**Independent Test**: Run `make e2e-up` on a 16 GB laptop; verify UI loads at `http://localhost:8080`, API responds at `http://localhost:8081/api/v1/healthz`, and seeded agents are retrievable. Run `make e2e-down`; verify `kind get clusters` is empty.

- [X] T011 [P] [US1] Create tests/e2e/cluster/kind-config.yaml (kind Cluster spec: apiVersion kind.x-k8s.io/v1alpha4, name amp-e2e, 1 control-plane node + 2 worker nodes, extraPortMappings containerPort 30080→hostPort 8080, 30081→8081, 30082→8082 for UI/API/WS)
- [X] T012 [P] [US1] Create tests/e2e/cluster/values-e2e.yaml (complete Helm overlay per contracts/helm-overlay.md: all stateful workloads to replicaCount 1, reduced resource requests, redis cluster disabled standalone mode, kafka single broker KRaft, opensearch single-node, objectStorage provider minio with in-cluster MinIO, features.e2eMode true, features.zeroTrustVisibility true, mockLLM.enabled true, autoscaling disabled, ingress disabled, NodePort services at 30080/30081/30082)
- [X] T013 [P] [US1] Create tests/e2e/cluster/load-images.sh (build all platform images using docker build for ghcr.io/musematic/control-plane:local, runtime-controller:local, reasoning-engine:local, sandbox-manager:local, ui:local and load each via `kind load docker-image <image> --name ${CLUSTER_NAME:-amp-e2e}`)
- [X] T014 [P] [US1] Create tests/e2e/cluster/install.sh (orchestrate: prereqs check for kind≥0.23/kubectl≥1.28/helm≥3.14/docker≥24, kind create cluster --name $CLUSTER_NAME --config cluster/kind-config.yaml, source load-images.sh, helm install amp deploy/helm/platform/ -f cluster/values-e2e.yaml --namespace platform --create-namespace --wait --timeout 10m, wait for all pods Ready, call python -m seeders.base --all, print ready banner with URLs)
- [X] T015 [P] [US1] Create tests/e2e/cluster/capture-state.sh (dump: kubectl get pods -A, kubectl get events -A --field-selector involvedObject.namespace=platform, helm status amp -n platform, kubectl -n platform logs for each platform pod --tail=100; write to stdout so CI can capture)
- [X] T016 [P] [US1] Create tests/e2e/seeders/users.py (idempotent seed of 5 users: admin@e2e.test platform_admin, operator1@e2e.test workspace_admin, operator2@e2e.test workspace_admin, end_user1@e2e.test workspace_member, viewer@e2e.test viewer role; POST /api/v1/auth/register + role assignment; reset deletes users with email ending @e2e.test)
- [X] T017 [P] [US1] Create tests/e2e/seeders/namespaces.py (idempotent seed of namespaces: default, test-finance, test-eng via POST /api/v1/namespaces; skip on 409 Conflict; reset deletes test-finance and test-eng only, preserves default)
- [X] T018 [P] [US1] Create tests/e2e/seeders/agents.py (idempotent seed of 6 agents one per role_type: default:seeded-executor executor, test-eng:seeded-planner planner, test-eng:seeded-orchestrator orchestrator, test-finance:seeded-observer observer, test-finance:seeded-judge judge, test-finance:seeded-enforcer enforcer; each with deterministic 60-char purpose, 80-char approach, visibility_patterns, and active certification valid 30 days from seed time)
- [X] T019 [P] [US1] Create tests/e2e/seeders/tools.py (idempotent seed of mock-http-tool calling an in-cluster stub HTTP service and mock-code-tool running a no-op Python snippet; POST /api/v1/tools; skip on 409)
- [X] T020 [P] [US1] Create tests/e2e/seeders/policies.py (idempotent seed of default-allow permissive policy, finance-strict policy denying tool calls matching secret* keys, test-budget-cap policy enforcing max_tokens ≤ 10000; POST /api/v1/policies; skip on 409)
- [X] T021 [P] [US1] Create tests/e2e/seeders/certifiers.py (idempotent seed of internal-cert built-in certifier and third-party-cert with endpoint https://cert.e2e.test/v1/verify pointing at in-cluster stub; skip on 409)
- [X] T022 [P] [US1] Create tests/e2e/seeders/fleets.py (idempotent seed of test-eng-fleet with seeded-planner as leader, seeded-orchestrator and seeded-executor as members; POST /api/v1/fleets; skip on 409)
- [X] T023 [P] [US1] Create tests/e2e/seeders/workspace_goals.py (idempotent seed of test-workspace-alpha workspace + 4 goals gid-open-001 open, gid-inprogress-001 in_progress, gid-completed-001 completed, gid-cancelled-001 cancelled per data-model.md; skip on 409)
- [X] T024 [US1] Create tests/e2e/Makefile (targets: e2e-check verifying prerequisites, e2e-up calling install.sh, e2e-down calling `kind delete cluster --name $(CLUSTER_NAME)`, e2e-test running pytest suites/, e2e-chaos running pytest chaos/, e2e-perf running pytest performance/, e2e-reset calling python -m seeders.base --reset --all, e2e-logs tailing platform pods, e2e-shell execing into control-plane, capture-state calling capture-state.sh; CLUSTER_NAME PORT_UI PORT_API PORT_WS env vars with defaults amp-e2e 8080 8081 8082)

**Checkpoint**: `make e2e-up` provisions cluster within 10 min; all seeded entities retrievable via API; `make e2e-down` leaves no artifacts. US1 independently testable.

---

## Phase 4: User Story 2 — Bounded-context suites validate every vertical slice (Priority: P1)

**Goal**: 16+ bounded-context test suites running against the live kind cluster, each with shared fixtures for HTTP, WebSocket, database assertion, Kafka event assertion, and mock LLM control.

**Independent Test**: With a running E2E cluster, run `make e2e-test`; verify every suite passes. Inject a deliberate break in one bounded context; verify only that context's suite fails.

- [X] T025 [US2] Create tests/e2e/fixtures/http_client.py (AuthenticatedAsyncClient extending httpx.AsyncClient: login_as(email, password) POSTs /api/v1/auth/login stores tokens, auto-refresh on 401, Bearer injection on every request, current_user_id/current_workspace_id properties; session-scoped `http_client` fixture pre-logged-in as admin@e2e.test; function-scoped `http_client_workspace_member` sibling logged in as end_user1@e2e.test)
- [X] T026 [P] [US2] Create tests/e2e/fixtures/ws_client.py (WsClient wrapping websockets.connect: subscribe(channel, topic), expect_event(channel, event, timeout=10.0) returns payload, drain(timeout) consumes pending messages; function-scoped fixture using http_client.access_token)
- [X] T027 [P] [US2] Create tests/e2e/fixtures/db_session.py (session-scoped asyncpg.Connection fixture using e2e_reader credentials from E2E_DB_DSN env var; read-only SELECT-only by PostgreSQL grants; exposes fetchrow/fetchval/fetch for assertion queries only)
- [X] T028 [P] [US2] Create tests/e2e/fixtures/kafka_consumer.py (KafkaTestConsumer wrapping aiokafka.AIOKafkaConsumer with unique consumer group `e2e-test-{uuid}` per invocation, auto_offset_reset latest, subscribe(topic), expect_event(topic, predicate, timeout=10.0), collect(topic, duration), expect_no_event(topic, predicate, duration); function-scoped fixture)
- [X] T029 [P] [US2] Create tests/e2e/fixtures/workspace.py (function-scoped workspace factory: POST /api/v1/workspaces name=test-{uuid4().hex[:8]}, yield workspace dict, DELETE /api/v1/workspaces/{id} in teardown; name prefix test- matches E2E scope filter)
- [X] T030 [P] [US2] Create tests/e2e/fixtures/agent.py (AgentFactory class: register(namespace, local_name, role_type, **kwargs) POSTs /api/v1/agents, with_certification(agent_id, valid_days=30), with_visibility(agent_id, patterns); function-scoped fixture returning factory; teardown deletes all test-{workspace_hash}: prefixed agents)
- [X] T031 [P] [US2] Create tests/e2e/fixtures/policy.py (PolicyFactory class: attach(policy_name, target_agent_fqn) POSTs /api/v1/policies/bindings, detach(binding_id) DELETEs binding; function-scoped fixture; seeded policy names (default-allow, finance-strict, test-budget-cap) available by name)
- [X] T032 [P] [US2] Create tests/e2e/fixtures/mock_llm.py (MockLLMController: set_response(prompt_pattern, response, streaming_chunks=None) POSTs /api/v1/_e2e/mock-llm/set-response, set_responses(dict), get_calls(pattern=None, since=None) reads Redis ring buffer, clear_queue() empties all queues; function-scoped fixture with teardown calling clear_queue())
- [X] T033 [US2] Create tests/e2e/conftest.py (session-scoped http_client and ws_client using fixtures/; session-scoped ensure_seeded autouse fixture calling POST /api/v1/_e2e/seed scope=all; function-scoped reset_ephemeral_state autouse fixture for chaos/ and performance/ suites only; URL constants PLATFORM_UI_URL/PLATFORM_API_URL/PLATFORM_WS_URL/DB_DSN/KAFKA_BOOTSTRAP from env with localhost defaults; pytest.ini_options asyncio_mode=auto)
- [X] T034 [P] [US2] Create tests/e2e/suites/auth/test_local_auth.py (login with valid credentials returns 200 + token pair; login with wrong password returns 401; token refresh returns new access token; account lockout after N failures returns 429 with lockout_seconds; logout invalidates session)
- [X] T035 [P] [US2] Create tests/e2e/suites/auth/test_mfa.py (TOTP enrollment: GET /auth/mfa/setup returns QR data; POST /auth/mfa/verify with valid TOTP succeeds; invalid TOTP returns 401; recovery code consumed successfully; MFA bypass without code rejected)
- [X] T036 [P] [US2] Create tests/e2e/suites/auth/test_google_oauth.py (Google OIDC mock: GET /auth/google redirects to mock provider; callback with code exchanges for platform token; user linked to Google identity; second login reuses existing user)
- [X] T037 [P] [US2] Create tests/e2e/suites/auth/test_github_oauth.py (GitHub OAuth mock: GET /auth/github redirects to mock server; callback with code exchanges for platform token; user created or linked; invalid state parameter rejected)
- [X] T038 [P] [US2] Create tests/e2e/suites/auth/test_session_lifecycle.py (login creates session in Redis; refresh rotates both tokens; logout deletes session; session expiry enforced after TTL; concurrent session count capped per user config)
- [X] T039 [P] [US2] Create tests/e2e/suites/registry/test_namespace_crud.py (POST namespace returns 201; GET by id returns namespace; PATCH updates display name; DELETE returns 204; list with pagination; duplicate name returns 409)
- [X] T040 [P] [US2] Create tests/e2e/suites/registry/test_fqn_registration.py (POST agent with namespace:local_name FQN returns 201; GET by FQN returns profile; duplicate FQN returns 409; list agents by namespace; FQN format validation rejects invalid chars)
- [X] T041 [P] [US2] Create tests/e2e/suites/registry/test_fqn_resolution.py (resolve known FQN returns agent profile; resolve unknown FQN returns 404; resolve with namespace wildcard returns list; ambiguous short name returns disambiguation list)
- [X] T042 [P] [US2] Create tests/e2e/suites/registry/test_pattern_discovery.py (search *:local_name across namespaces; namespace:* returns all in namespace; *.* returns all visible; pattern with no matches returns empty list; visibility filter applied in SQL)
- [X] T043 [P] [US2] Create tests/e2e/suites/registry/test_visibility_zero_trust.py (agent with no workspace grant not visible to workspace member; admin sees all; POST visibility_grant reveals agent; revoked grant hides agent again; assert via GET /api/v1/agents not via direct DB)
- [X] T044 [P] [US2] Create tests/e2e/suites/registry/test_visibility_workspace_grants.py (workspace-level FQN pattern grants; member can see granted agent; viewer limited to read-only; cross-workspace isolation: grant in workspace A does not leak to workspace B)
- [X] T045 [P] [US2] Create tests/e2e/suites/trust/test_pre_screener.py (benign text passes pre-screener and reaches mock LLM; known prompt injection pattern in input is blocked with 400; Kafka event trust.screener.blocked published for blocked inputs via kafka_consumer)
- [X] T046 [P] [US2] Create tests/e2e/suites/trust/test_secret_sanitization.py (execution output containing a string matching API key pattern returns response with [REDACTED:secret] substitution; non-secret output passes unmodified; sanitization does not alter content type or break JSON structure)
- [X] T047 [P] [US2] Create tests/e2e/suites/trust/test_certification_workflow.py (submit agent for certification review; reviewer approves with evidence ref; certification status transitions pending→active; GET /api/v1/trust/certifications/{id} returns active cert; revoke transitions to revoked)
- [X] T048 [P] [US2] Create tests/e2e/suites/trust/test_contract_compliance.py (attach behavioral contract to seeded agent; trigger execution that violates a contract action pattern; assert trust.contract.violated Kafka event published; surveillance signal recorded)
- [X] T049 [P] [US2] Create tests/e2e/suites/trust/test_third_party_certifier.py (configure third-party certifier pointing to https://cert.e2e.test/v1/verify in-cluster stub; POST certification request; platform calls stub HTTPS endpoint; stub returns verification result; certification issued or rejected accordingly)
- [X] T050 [P] [US2] Create tests/e2e/suites/trust/test_surveillance.py (surveillance signal published via ws_client testing channel; GET trust signal stored in DB via db fixture; trust score recalculated and accessible via GET /api/v1/trust/agents/{id}/score)
- [X] T051 [P] [US2] Create tests/e2e/suites/governance/test_observer_judge_enforcer_pipeline.py (seeded observer monitors execution; action triggers verdict request; seeded judge issues governance.verdict.issued; seeded enforcer executes enforcement action; governance.enforcement.executed Kafka event published end-to-end)
- [X] T052 [P] [US2] Create tests/e2e/suites/governance/test_verdict_issuance.py (judge agent receives verdict input payload; deliberates via mock LLM response; publishes governance.verdict.issued Kafka event; verdict accessible via GET /api/v1/governance/verdicts/{id})
- [X] T053 [P] [US2] Create tests/e2e/suites/governance/test_enforcement_actions.py (enforcer agent receives governance.verdict.issued; executes deny/allow action on target; publishes governance.enforcement.executed; audit record captured in OpenSearch via db or direct log check)
- [X] T054 [P] [US2] Create tests/e2e/suites/interactions/test_conversation_lifecycle.py (POST conversation; add interaction; create branch; merge branch; close conversation; verify state transitions via GET /api/v1/interactions/conversations/{id})
- [X] T055 [P] [US2] Create tests/e2e/suites/interactions/test_workspace_goal_lifecycle.py (open goal transitions to in_progress when first interaction linked; transitions to completed when closed; GID field present in all related interaction records via db fixture)
- [X] T056 [P] [US2] Create tests/e2e/suites/interactions/test_gid_correlation.py (POST interaction with gid header; Kafka event on interaction.events topic contains matching gid via kafka_consumer; DB record via db fixture contains gid; GID propagated in downstream execution Kafka event)
- [X] T057 [P] [US2] Create tests/e2e/suites/interactions/test_response_decision.py (agent response_decision payload recorded in interaction messages; workspace alert generated when response has attention_required flag; alert retrievable via GET /api/v1/interactions/alerts)
- [X] T058 [P] [US2] Create tests/e2e/suites/interactions/test_attention_request.py (agent publishes AttentionRequest via POST /api/v1/interactions/attention; interaction.attention Kafka event published; ws_client subscribed to attention channel receives event with target_id matching admin user)
- [X] T059 [P] [US2] Create tests/e2e/suites/interactions/test_user_alerts.py (alert created via API; ws_client alerts channel subscriber receives broadcast; dismiss via POST /api/v1/interactions/alerts/{id}/dismiss removes from pending list)
- [X] T060 [P] [US2] Create tests/e2e/suites/workflows/test_execution_end_to_end.py (POST /api/v1/executions dispatches trivial execution; poll status until completed; verify final state via GET execution API; verify execution record in DB via db fixture)
- [X] T061 [P] [US2] Create tests/e2e/suites/workflows/test_checkpoint_rollback.py (dispatch execution that writes checkpoint; wait for checkpoint.created Kafka event via kafka_consumer; POST /api/v1/executions/{id}/rollback; assert execution resumes from checkpoint and completes)
- [X] T062 [P] [US2] Create tests/e2e/suites/workflows/test_reprioritization.py (dispatch low-priority execution; dispatch high-priority execution while first is queued; POST reprioritize on high-priority; verify high-priority completes before low-priority)
- [X] T063 [P] [US2] Create tests/e2e/suites/fleets/test_fleet_orchestration.py (dispatch fleet task to test-eng-fleet; seeded-planner leader delegates sub-tasks to seeded-orchestrator and seeded-executor; all sub-tasks complete; fleet execution final state completed)
- [X] T064 [P] [US2] Create tests/e2e/suites/fleets/test_fleet_coordination.py (fleet member signals progress via fleet event; aggregated fleet health updated in Redis; fleet completion event published on fleet.events topic via kafka_consumer)
- [X] T065 [P] [US2] Create tests/e2e/suites/reasoning/test_cot.py (CoT-enabled execution with mock LLM step responses; ws_client subscribed to reasoning channel receives CoT trace events in order; steps and conclusions recorded in MinIO trace artifact)
- [X] T066 [P] [US2] Create tests/e2e/suites/reasoning/test_tot.py (ToT execution: multiple branches spawned; branch states observable via ws_client reasoning channel; convergence selects highest-scoring branch; final response from winning branch)
- [X] T067 [P] [US2] Create tests/e2e/suites/reasoning/test_react.py (ReAct loop: mock LLM returns action; tool call captured via kafka_consumer on tool.events; observation injected back; next mock LLM response uses observation; loop terminates on final_answer)
- [X] T068 [P] [US2] Create tests/e2e/suites/reasoning/test_cod.py (Chain of Debates: two seeded agents assigned debate roles; multiple debate rounds via Kafka; seeded judge agent issues final verdict; verdict on governance.verdict.issued topic)
- [X] T069 [P] [US2] Create tests/e2e/suites/reasoning/test_self_correction.py (execution returns output with error marker; self-correction triggered; corrected output returned to caller; correction step recorded in execution trace)
- [X] T070 [P] [US2] Create tests/e2e/suites/reasoning/test_compute_budget.py (execution with max_tokens=100 budget; steps consume tokens; at budget limit execution halted; budget.exhausted Kafka event published via kafka_consumer; final state=budget_exhausted)
- [X] T071 [P] [US2] Create tests/e2e/suites/evaluation/test_trajectory_scorer.py (POST trajectory evaluation with execution_id; scorer evaluates full action path; score stored; GET /api/v1/evaluation/scores/{execution_id} returns score with dimensions)
- [X] T072 [P] [US2] Create tests/e2e/suites/evaluation/test_llm_judge.py (POST LLM judge evaluation; mock LLM returns structured verdict payload; verdict stored with execution_id; GET evaluation result returns judge verdict fields)
- [X] T073 [P] [US2] Create tests/e2e/suites/evaluation/test_ab_testing.py (POST A/B test config with two agent variants; dispatch N executions; verify traffic split approximately matches configured weights; metrics accumulated per variant)
- [X] T074 [P] [US2] Create tests/e2e/suites/agentops/test_adaptation_proposal.py (simulate behavioral drift by recording divergent execution outcomes; adaptation proposal generated by agentops service; proposal accessible via GET /api/v1/agentops/proposals/{id})
- [X] T075 [P] [US2] Create tests/e2e/suites/agentops/test_canary_deployment.py (POST canary deployment for seeded agent; traffic split configured; rollback triggered when error rate exceeds threshold via POST rollback; deployment returns to stable version)
- [X] T076 [P] [US2] Create tests/e2e/suites/discovery/test_proximity_graph.py (POST hypotheses to discovery; proximity clustering job runs; GET proximity clusters returns cluster with similar hypotheses linked; graph traversal returns related nodes)
- [X] T077 [P] [US2] Create tests/e2e/suites/a2a/test_agent_card_generation.py (registered agent with FQN; GET /.well-known/agent.json returns valid Agent Card JSON with skills, endpoints, auth schemes; card schema validates against A2A spec)
- [X] T078 [P] [US2] Create tests/e2e/suites/a2a/test_server_task_lifecycle.py (POST /a2a/tasks with agent FQN target; task status polled via GET /a2a/tasks/{id}; task completes with output; failed task returns error payload)
- [X] T079 [P] [US2] Create tests/e2e/suites/a2a/test_sse_streaming.py (POST streaming A2A task; consume SSE event stream; events arrive in order with correct event types; connection closes with done event on completion)
- [X] T080 [P] [US2] Create tests/e2e/suites/a2a/test_client_mode.py (platform dispatches A2A task to mock remote agent in-cluster; response received and stored as interaction; execution completes with A2A response payload)
- [X] T081 [P] [US2] Create tests/e2e/suites/mcp/test_client_discovery.py (MCP server registered in platform; GET /mcp/tools returns tool list; tool call via POST /mcp/call routed through tool gateway; tool policy enforced; result returned)
- [X] T082 [P] [US2] Create tests/e2e/suites/mcp/test_server_exposure.py (platform MCP server endpoint at /mcp/server accessible; external mock client lists tools; tool execution returns deterministic result from mock-http-tool)
- [X] T083 [P] [US2] Create tests/e2e/suites/runtime/test_warm_pool.py (warm pool fills to configured size=2; execution allocated from warm container without cold start; pool replenishment observed via ws_client testing channel; pool size metric recovers after allocation)
- [X] T084 [P] [US2] Create tests/e2e/suites/runtime/test_secrets_injection.py (secret registered in platform secrets store; execution dispatches tool that reads secret env var; mock LLM call record via mock_llm.get_calls() verifies secret value absent from recorded prompt)
- [X] T085 [P] [US2] Create tests/e2e/suites/storage/test_generic_s3_upload_download.py (execution artifact uploaded via generic S3 client configured to MinIO endpoint; downloaded artifact SHA256 matches original; presigned URL expires as configured)
- [X] T086 [P] [US2] Create tests/e2e/suites/storage/test_lifecycle.py (lifecycle policy applied on artifact bucket; artifact transitions through active→archived state; expired artifact purged after TTL; lifecycle events on storage.events topic via kafka_consumer)
- [X] T087 [P] [US2] Create tests/e2e/suites/ibor/test_ibor_sync.py (mock LDAP server running in-cluster at ldap://mock-ldap:389; IBOR sync triggered via POST /api/v1/ibor/sync; users reconciled in PostgreSQL via db fixture; ibor.sync.completed Kafka event published)

**Checkpoint**: All 16+ bounded-context suites pass with `make e2e-test`. Suite isolation verified. US2 independently testable.

---

## Phase 5: User Story 3 — Chaos scenarios validate platform recovery (Priority: P2)

**Goal**: 6 chaos tests that inject real failures via dev-only endpoints and assert specific named recovery outcomes.

**Independent Test**: With a running E2E cluster, run `make e2e-chaos`; all 6 scenarios must pass, each asserting recovery (not merely survival).

- [X] T088 [US3] Create tests/e2e/chaos/test_runtime_pod_kill.py (POST /api/v1/executions to start long-running execution; wait for checkpoint.created Kafka event via kafka_consumer; POST /api/v1/_e2e/chaos/kill-pod targeting runtime-controller in platform-execution; assert execution does NOT transition to failed within 30s; assert final state=completed; no manual teardown — Kubernetes reschedules killed pod)
- [X] T089 [P] [US3] Create tests/e2e/chaos/test_reasoning_engine_kill.py (start CoT streaming execution; wait for first reasoning trace event on ws_client; POST /_e2e/chaos/kill-pod targeting reasoning-engine; assert control plane reconnects; assert caller receives full trace without dropped events; verify trace continuity from last acked step)
- [X] T090 [P] [US3] Create tests/e2e/chaos/test_kafka_broker_restart.py (produce event burst of N messages on execution.events topic; POST /_e2e/chaos wrapping kubectl rollout restart statefulset/kafka; collect all events post-restart via kafka_consumer; assert count equals N with no duplicates; verify exactly-once delivery)
- [X] T091 [P] [US3] Create tests/e2e/chaos/test_s3_credential_revoke.py (start execution triggering S3 artifact upload; call /_e2e/chaos to rotate MinIO credentials mid-upload; assert platform surfaces S3CredentialError within 10s rather than silent timeout; finally block restores original credentials)
- [X] T092 [P] [US3] Create tests/e2e/chaos/test_network_partition.py (POST /_e2e/chaos/partition-network from-namespace=platform-execution to-namespace=platform-data ttl_seconds=30; assert circuit breaker opens within 15s: requests to platform return ServiceUnavailable immediately not hanging; wait for TTL expiry + auto-NetworkPolicy deletion; verify recovery: requests succeed again)
- [X] T093 [P] [US3] Create tests/e2e/chaos/test_policy_timeout.py (install policy with deliberately slow evaluation via /_e2e endpoint; trigger governed action; assert action denied with fail-closed response; assert audit record via db fixture contains timeout_reason field; uninstall slow policy in teardown)

**Checkpoint**: All 6 chaos scenarios pass with `make e2e-chaos`. US3 independently testable.

---

## Phase 6: User Story 4 — Performance smoke tests catch regressions (Priority: P2)

**Goal**: 4 performance smoke tests with named thresholds in a single `thresholds.py` module; `performance.json` artifact written with measured vs expected values.

**Independent Test**: With a running E2E cluster, run `make e2e-perf`; all 4 tests pass within thresholds; `tests/e2e/reports/performance.json` is written.

- [X] T094 [US4] Create tests/e2e/performance/thresholds.py (WARM_LAUNCH_MAX_SECONDS = 2.0, COLD_LAUNCH_MAX_SECONDS = 10.0, TRIVIAL_AGENT_ROUNDTRIP_MAX_SECONDS = 5.0, CONCURRENT_EXECUTION_COUNT = 10, CONCURRENT_MAX_WALL_CLOCK_SECONDS = 15.0, REASONING_OVERHEAD_MAX_MS = 50, REASONING_BASELINE_ITERATIONS = 100; all constants used by test files via import)
- [X] T095 [P] [US4] Create tests/e2e/performance/test_launch_latency.py (test_warm_launch: ensure warm pool filled, dispatch execution, measure time to first-event, assert < WARM_LAUNCH_MAX_SECONDS; test_cold_launch: drain warm pool, dispatch, measure, assert < COLD_LAUNCH_MAX_SECONDS; write both to performance.json)
- [X] T096 [P] [US4] Create tests/e2e/performance/test_execution_roundtrip.py (trivial agent with mock LLM returning constant; POST execution; measure wall-clock to completed event; assert < TRIVIAL_AGENT_ROUNDTRIP_MAX_SECONDS; append measurement to performance.json as {"test": "test_trivial_agent_roundtrip", "measured": X, "threshold": 5.0, "unit": "seconds"})
- [X] T097 [P] [US4] Create tests/e2e/performance/test_concurrent_throughput.py (dispatch CONCURRENT_EXECUTION_COUNT=10 executions simultaneously via asyncio.gather; assert all complete without failure; assert wall-clock < CONCURRENT_MAX_WALL_CLOCK_SECONDS; append measurement to performance.json)
- [X] T098 [P] [US4] Create tests/e2e/performance/test_reasoning_overhead.py (run REASONING_BASELINE_ITERATIONS executions without reasoning then with reasoning; compute mean overhead per step; assert mean_overhead_ms < REASONING_OVERHEAD_MAX_MS; append measurement to performance.json as {"test": "test_per_step_reasoning_overhead", "measured": X, "threshold": 50, "unit": "milliseconds"})

**Checkpoint**: All 4 performance smoke tests pass with `make e2e-perf`. `performance.json` written per quickstart.md Q4 schema. US4 independently testable.

---

## Phase 7: User Story 5 — CI runs E2E on every PR and nightly (Priority: P2)

**Goal**: GitHub Actions workflow that runs the full E2E suite on every PR and nightly on main, with downloadable artifacts and auto-issue creation after 3 consecutive nightly failures.

**Independent Test**: Open a PR; verify the E2E workflow triggers, completes, and uploads artifacts. Fail a step; verify artifact bundle is downloadable.

- [X] T099 [US5] Create .github/workflows/e2e.yml (triggers: on pull_request + on schedule cron "0 3 * * *"; job e2e on ubuntu-latest-8-cores timeout-minutes 45; concurrency group "e2e-${{ github.head_ref || github.run_id }}" cancel-in-progress true; steps: actions/checkout@v4, helm/kind-action@v1 with kind-config.yaml and cluster_name amp-e2e, build+load images via make load-images, make e2e-up, make e2e-test, make e2e-chaos, make e2e-perf, capture-state on failure writing to artifacts/state-dump.txt, actions/upload-artifact@v4 always with name e2e-reports-${{ github.run_id }} path tests/e2e/reports/ retention-days 30)
- [X] T100 [US5] Add nightly failure tracking to .github/workflows/e2e.yml (check-previous-failures job reading last 3 nightly run conclusions via `gh run list`; if 3 consecutive failures on main branch and trigger is schedule: `gh issue create` with title "E2E nightly failing on main (3rd consecutive night)" body containing artifact links and run URLs)

**Checkpoint**: E2E workflow triggers on every PR; artifacts uploadable on failure; nightly schedule configured; consecutive-failure auto-issue logic wired. US5 verifiable by opening a PR.

---

## Phase 8: User Story 6 — Parallel clusters, deterministic mocks, production safety (Priority: P3)

**Goal**: Multi-cluster parameterization, byte-deterministic mock LLM test, static 404 contract test, chart-identity test.

**Independent Test**: (1) Two clusters run side-by-side without collision. (2) Mock LLM determinism test passes 10/10 runs. (3) Static 404 contract test passes with `FEATURE_E2E_MODE=false`.

- [X] T101 [US6] Parameterize tests/e2e/cluster/kind-config.yaml and tests/e2e/Makefile for multi-cluster support: Makefile generates /tmp/kind-config-${CLUSTER_NAME}.yaml via envsubst from a template that substitutes CLUSTER_NAME, PORT_UI, PORT_API, PORT_WS; tests/e2e/conftest.py reads PLATFORM_API_URL/PLATFORM_WS_URL from env (defaulting to localhost:PORT_API/PORT_WS) so tests route to the correct cluster port
- [X] T102 [P] [US6] Create tests/e2e/suites/reasoning/test_mock_llm_deterministic.py (pre-populate mock LLM queue with fixed 3-response sequence via mock_llm.set_responses; dispatch same execution 10 times; collect all mock_llm.get_calls(pattern="agent_response") records; assert all response fields byte-identical across 10 runs; SC-008 enforcement)
- [X] T103 [P] [US6] Create apps/control-plane/tests/unit/testing/test_router_e2e_404_when_flag_off.py (import router_e2e.py to extract all registered paths; instantiate FastAPI TestApp with FEATURE_E2E_MODE=false; assert each path returns HTTP 404 via httpx.AsyncClient; new paths added to router_e2e.py automatically covered; SC-007 enforcement)
- [X] T104 [P] [US6] Create tests/e2e/test_chart_identity.py (from pathlib import Path; scan Path(__file__).parent.rglob("Chart.yaml"); assert list is empty with message listing offending paths; SC-010 enforcement per contracts/helm-overlay.md)

**Checkpoint**: Two parallel clusters run on same host; determinism test passes 10/10; 404 contract test passes; chart-identity test passes. US6 independently testable.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Directory rename per D-004, unit tests for platform additions, contributor documentation, and final acceptance validation.

- [X] T105 [P] Rename apps/control-plane/tests/e2e/ to apps/control-plane/tests/integration/ via git mv; update any CI matrix references to the old path; add CHANGELOG entry noting the rename per research D-004 (pre-existing integration tests under docker-compose scope, not kind harness)
- [X] T106 [P] Create apps/control-plane/tests/unit/common/llm/test_mock_provider.py (unit tests for MockLLMProvider: FIFO queue returns responses in order, queue-empty returns default deterministic fallback, streaming mode yields correct chunk sequence, call recording stores all fields defined in MockLLMCallRecord, Redis broadcast publishes to e2e:mock_llm:set channel)
- [X] T107 [P] Create tests/e2e/README.md (quickstart: prerequisites check `make e2e-check`, `make e2e-up`, `make e2e-test`, `make e2e-chaos`, `make e2e-perf`, `make e2e-down`; link to quickstart.md acceptance scenarios Q1–Q6; link to contracts/ API reference; troubleshooting tips for OOM and port collisions)
- [ ] T108 Run all 6 quickstart.md acceptance scenarios to validate complete feature: Q1 cluster up/down, Q2 bounded-context suites, Q3 chaos, Q4 performance, Q5 CI trigger and artifact check, Q6 parallel clusters + mock LLM determinism + prod-safety 404 verification

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup — **BLOCKS all user stories**
- **US1 (Phase 3)**: Depends on Phase 2 (FEATURE_E2E_MODE flag must exist; seeder base must exist)
- **US2 (Phase 4)**: Depends on Phase 2 (dev endpoints must be mountable) AND Phase 3 (cluster must be provisionable for end-to-end fixture validation)
- **US3 (Phase 5)**: Depends on Phase 3 (cluster up) and Phase 4 (dev chaos endpoints tested via fixtures)
- **US4 (Phase 6)**: Depends on Phase 3 (cluster up); independent of US2/US3
- **US5 (Phase 7)**: Depends on Phases 3–6 (CI runs all suites); can be scaffolded in parallel
- **US6 (Phase 8)**: Depends on Phase 3 (Makefile parameterization), Phase 2 (router for 404 test), Phase 4 (mock LLM for determinism test)
- **Polish (Phase 9)**: Depends on all prior phases complete

### User Story Dependencies

- **US1 (P1)**: Depends on Phase 2 only — MVP, no story deps
- **US2 (P1)**: Depends on US1 (cluster must provision) — but fixtures can be developed before cluster is provisioned
- **US3 (P2)**: Depends on US2 fixtures (chaos tests use kafka_consumer, mock_llm, http_client) and Phase 2 chaos endpoints
- **US4 (P2)**: Depends on US1 (cluster); fixtures from US2 are helpful but not required for perf smoke tests
- **US5 (P2)**: Depends on US1–US4 all working; CI workflow wires all make targets
- **US6 (P3)**: Depends on US1 (Makefile), Phase 2 (router for 404 test), US2 (mock_llm for determinism test)

### Parallel Opportunities

- All Phase 1 Setup tasks: all [P] within phase
- Phase 2: T005 and T006 and T010 are [P]; T007 follows T006; T008 follows T007; T009 follows T008
- Phase 3: T011–T023 are [P] (different files); T024 Makefile follows cluster files
- Phase 4: All suite test files T034–T087 are [P] with each other; fixtures T026–T032 are [P] with each other
- Phase 5: T089–T093 are [P] with each other (T088 must precede as baseline chaos test)
- Phase 6: T095–T098 are [P]; T094 thresholds.py first
- Phase 9: T105–T107 all [P]

---

## Parallel Example: User Story 2

```bash
# Launch all fixture files in parallel (different files):
Task: "Create tests/e2e/fixtures/ws_client.py"
Task: "Create tests/e2e/fixtures/db_session.py"
Task: "Create tests/e2e/fixtures/kafka_consumer.py"
Task: "Create tests/e2e/fixtures/workspace.py"
Task: "Create tests/e2e/fixtures/agent.py"
Task: "Create tests/e2e/fixtures/policy.py"
Task: "Create tests/e2e/fixtures/mock_llm.py"

# Then once http_client.py and conftest.py are complete, launch all suites in parallel:
Task: "Create tests/e2e/suites/auth/test_local_auth.py"
Task: "Create tests/e2e/suites/registry/test_namespace_crud.py"
Task: "Create tests/e2e/suites/trust/test_pre_screener.py"
# ... (all 54 suite test files can be written in parallel)
```

---

## Implementation Strategy

### MVP First (US1 + US2 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all user stories)
3. Complete Phase 3: US1 — Cluster provisioning and seeding
4. **STOP and VALIDATE**: `make e2e-up`, verify seeded entities, `make e2e-down`
5. Complete Phase 4: US2 — Fixtures and bounded-context suites
6. **STOP and VALIDATE**: `make e2e-up && make e2e-test`

### Incremental Delivery

1. Setup + Foundational → platform-side flag + mock LLM + router ready
2. US1 → cluster provisioning works locally (MVP!)
3. US2 → bounded-context suites pass on cluster
4. US3 → chaos scenarios pass (adds resilience confidence)
5. US4 → performance smoke tests pass (adds regression guard)
6. US5 → CI wired (enforces green-path on every PR)
7. US6 → parallel clusters + safety hardening (advanced use cases)

### Parallel Team Strategy

With two developers:
- Dev A: Phase 2 (platform endpoints + mock LLM) + Phase 3 (cluster infra)
- Dev B: Phase 4 fixtures (can be written before cluster is up, validated after)
- Both: Phase 4 suite test files (54 test files fully parallelizable by bounded context)

---

## Notes

- [P] tasks = different files, no dependencies within the phase
- [Story] label maps each task to a specific user story for traceability
- Tests in this feature ARE the deliverable — the harness is the product
- Every chaos fixture MUST include a `try/finally` teardown reversing the injected failure
- Seeders MUST be idempotent (ON CONFLICT DO NOTHING or equivalent)
- `FEATURE_E2E_MODE=false` is the absolute default — verify with T103 before closing any PR
- The production Helm chart at `deploy/helm/platform/` is never forked — T104 enforces this
