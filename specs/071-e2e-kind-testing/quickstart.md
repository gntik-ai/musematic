# Quickstart & Acceptance Scenarios: E2E on kind

**Feature**: 071-e2e-kind-testing
**Date**: 2026-04-20

Six walkthroughs (Q1–Q6), one per user story, with exact commands and expected outputs. These become the basis of the CI green path and the local dev-onboarding doc.

## Prerequisites

```bash
docker --version           # ≥ 24
kind version               # ≥ 0.23
kubectl version --client   # ≥ 1.28
helm version               # ≥ 3.14
python --version           # ≥ 3.12
pip install -r tests/e2e/requirements.txt
```

The `make e2e-check` target runs all of the above and prints actionable install instructions on failure.

---

## Q1 — Developer provisions the full platform on kind (US1 / MVP)

```bash
cd tests/e2e
make e2e-up
```

**Expected output** (abridged):

```
Checking prerequisites...                       ✓
Creating kind cluster 'amp-e2e'...              ✓  (85s)
Loading platform images into cluster...         ✓  (118s)
  - ghcr.io/musematic/control-plane:local
  - ghcr.io/musematic/runtime-controller:local
  - ghcr.io/musematic/reasoning-engine:local
  - ghcr.io/musematic/sandbox-manager:local
  - ghcr.io/musematic/ui:local
Installing platform via Helm...                 ✓  (287s)
  Release: amp
  Namespace: platform
Waiting for all pods Ready...                   ✓  (42s)
Seeding baseline data...                        ✓  (48s)
  users: 5, namespaces: 3, agents: 6, tools: 2,
  policies: 3, certifiers: 2, fleets: 1, goals: 4

E2E environment ready:
  UI:  http://localhost:8080
  API: http://localhost:8081
  WS:  ws://localhost:8082
  Admin: admin@e2e.test / e2e-test-password

Total time: 9m 20s
```

**Verification**:

```bash
curl -s http://localhost:8081/api/v1/healthz | jq .
# { "status": "ok", "version": "..." }

curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8081/api/v1/agents | jq '.items | length'
# 6
```

**Teardown**:

```bash
make e2e-down
# Deleting cluster 'amp-e2e'...  ✓

docker ps  # no stray containers
kind get clusters  # "No kind clusters found."
```

---

## Q2 — Bounded-context suites run on the cluster (US2)

```bash
cd tests/e2e
make e2e-test
```

**Expected output** (abridged):

```
============ test session starts ============
collected 58 items

suites/auth/test_local_auth.py ..........      [  5%]
suites/auth/test_mfa.py ........               [ 10%]
suites/auth/test_google_oauth.py ......        [ 15%]
suites/auth/test_github_oauth.py ......        [ 20%]
suites/auth/test_session_lifecycle.py .....    [ 25%]
suites/registry/test_namespace_crud.py ....    [ 28%]
suites/registry/test_fqn_registration.py ...   [ 30%]
...
suites/ibor/test_ibor_sync.py ...              [100%]

========== 58 passed in 8m 12s ==========

Reports written to tests/e2e/reports/:
  junit.xml
  report.html
```

**Deliberate-failure check** (verifies no cross-suite cascade):

```bash
# Temporarily break the registry service
kubectl -n platform set env deploy/amp-control-plane BREAK_REGISTRY=1
make e2e-test

# Expected: only suites/registry/* tests fail; auth, trust, governance, etc. still pass.
```

---

## Q3 — Chaos scenarios validate recovery (US3)

```bash
cd tests/e2e
make e2e-chaos
```

**Expected output**:

```
============ test session starts ============
collected 6 items

chaos/test_runtime_pod_kill.py .              [ 16%]
chaos/test_reasoning_engine_kill.py .         [ 33%]
chaos/test_kafka_broker_restart.py .          [ 50%]
chaos/test_s3_credential_revoke.py .          [ 66%]
chaos/test_network_partition.py .             [ 83%]
chaos/test_policy_timeout.py .                [100%]

========== 6 passed in 3m 45s ==========
```

**What one scenario proves** (e.g., `test_runtime_pod_kill`):

1. Start a long-running execution via `POST /api/v1/executions`.
2. Wait until execution has written its first checkpoint (observed via `kafka_consumer.expect_event("execution.events", lambda e: e["event_type"] == "checkpoint.created")`).
3. `POST /api/v1/_e2e/chaos/kill-pod` targeting runtime-controller.
4. Assert execution does NOT transition to `failed` within 30 s — instead resumes and completes with state `completed`.
5. Teardown: the killed pod is auto-rescheduled by Kubernetes (no manual teardown needed).

---

## Q4 — Performance smoke tests meet targets (US4)

```bash
cd tests/e2e
make e2e-perf
```

**Expected output**:

```
============ test session starts ============
collected 4 items

performance/test_launch_latency.py
  test_warm_launch[filled_pool]      1.24s < 2.00s (target)  ✓
  test_cold_launch                   6.87s < 10.00s (target) ✓
performance/test_execution_roundtrip.py
  test_trivial_agent_roundtrip       3.12s < 5.00s (target)  ✓
performance/test_concurrent_throughput.py
  test_10_concurrent                 12.45s wall-clock       ✓
performance/test_reasoning_overhead.py
  test_per_step_overhead            34.2ms < 50ms (target)   ✓

========== 4 passed in 1m 58s ==========

Measurements written to tests/e2e/reports/performance.json
```

**`performance.json` structure**:

```json
{
  "runs": [
    { "test": "test_warm_launch", "measured": 1.24, "threshold": 2.0, "passed": true, "unit": "seconds" },
    { "test": "test_cold_launch", "measured": 6.87, "threshold": 10.0, "passed": true, "unit": "seconds" },
    { "test": "test_trivial_agent_roundtrip", "measured": 3.12, "threshold": 5.0, "passed": true, "unit": "seconds" },
    { "test": "test_per_step_reasoning_overhead", "measured": 34.2, "threshold": 50.0, "passed": true, "unit": "milliseconds" }
  ]
}
```

---

## Q5 — CI runs E2E on every PR and nightly (US5)

**PR workflow** (`.github/workflows/e2e.yml`, triggered `on: pull_request`):

```
1. Checkout
2. helm/kind-action: create cluster 'amp-e2e' with kind-config.yaml
3. Build + load platform images
4. make e2e-up (cluster already exists — skips creation, runs install.sh)
5. make e2e-test       (suites)
6. make e2e-chaos      (chaos)
7. make e2e-perf       (performance)
8. On any failure:     make capture-state
9. Upload artifact: e2e-reports-${{ github.run_id }}
10. Report pass/fail to PR check
```

**Expected on-PR view**:

- GitHub check `e2e / pull-request` — ✓ passed (or ✗ failed with artifact link).
- Artifact `e2e-reports-1234567890` (30-day retention) downloadable from the run page.

**Nightly** (`on: schedule: cron "0 3 * * *"`):

- Runs against `main` branch.
- Same steps.
- After 3 consecutive nightly failures, workflow auto-creates a GitHub issue: `E2E nightly failing on main (3rd consecutive night)` with artifact links.

**Concurrency**: `concurrency: { group: "e2e-${{ github.head_ref || github.run_id }}", cancel-in-progress: true }` — a new commit on the same PR branch cancels the in-flight run.

---

## Q6 — Parallel clusters, deterministic mocks, production safety (US6)

### Part A — Two clusters on the same host

```bash
# Cluster A on default ports 8080/8081/8082
cd tests/e2e
make e2e-up CLUSTER_NAME=amp-e2e-a

# In another terminal, cluster B on 9080/9081/9082
make e2e-up CLUSTER_NAME=amp-e2e-b PORT_UI=9080 PORT_API=9081 PORT_WS=9082

kind get clusters
# amp-e2e-a
# amp-e2e-b

curl http://localhost:8081/api/v1/healthz  # cluster A
curl http://localhost:9081/api/v1/healthz  # cluster B
# Both OK

# Teardown both
make e2e-down CLUSTER_NAME=amp-e2e-a
make e2e-down CLUSTER_NAME=amp-e2e-b
```

### Part B — Mock LLM determinism

```bash
# Run the determinism test 10 times and diff outputs
for i in $(seq 1 10); do
  pytest suites/reasoning/test_cot.py::test_mock_llm_deterministic -v -q \
    --tb=no --log-cli-level=INFO > /tmp/run-$i.log
done

diff /tmp/run-1.log /tmp/run-2.log  # → empty (byte-identical)
for i in $(seq 3 10); do
  diff /tmp/run-1.log /tmp/run-$i.log  # → all empty
done
```

### Part C — Production safety

```bash
# Deploy platform WITHOUT E2E feature flag (production default)
helm install amp deploy/helm/platform/ \
  -f deploy/helm/platform/values.yaml \
  --set global.environment=production

# Every /api/v1/_e2e/* endpoint returns 404
for path in seed reset chaos/kill-pod chaos/partition-network mock-llm/set-response kafka/events; do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST https://platform.yourcompany.com/api/v1/_e2e/$path
done
# 404
# 404
# 404
# 404
# 404
# 404
```

**Static contract test** (`apps/control-plane/tests/unit/testing/test_router_e2e_404_when_flag_off.py`) enumerates every endpoint and asserts 404 via an in-process TestClient with `FEATURE_E2E_MODE=false`. Runs on every PR — prevents regression.

---

## Cross-cutting verification checklist

After all six walkthroughs pass:

- [ ] `kind get clusters` empty after `make e2e-down` (SC-002)
- [ ] Every bounded context has at least one E2E test (SC-003)
- [ ] Static contract test asserts 404 for all `/api/v1/_e2e/*` paths when flag off (SC-007)
- [ ] Determinism test passes 10/10 runs (SC-008)
- [ ] Two concurrent clusters run without interference (SC-009)
- [ ] Chart-identity test passes (no separate `Chart.yaml` under `tests/e2e/`, SC-010)
- [ ] CI artifact bundle contains junit.xml + report.html + state-dump.txt + pod-logs (FR-027)
- [ ] Provisioning wall-clock ≤ 10 min on reference laptop (SC-001)
- [ ] CI workflow wall-clock ≤ 45 min on `ubuntu-latest-8-cores` (SC-006)
