# Research: Evaluation Framework and Semantic Testing

**Branch**: `034-evaluation-semantic-testing`  
**Status**: Complete — all unknowns resolved

---

## Decision 1: Bounded Context Split

**Decision**: Two bounded contexts — `evaluation/` and `testing/`

**Rationale**: Matches the constitution §IV repo structure exactly. `evaluation/` owns the eval lifecycle (sets, runs, verdicts, A/B, ATE, robustness, human grading). `testing/` owns test generation and operational observability (adversarial gen, drift detection, coordination testing, generated suites). Scorer implementations live in `evaluation/scorers/` since they are part of the eval engine — not in `testing/`.

**Alternatives considered**: Single `evaluation/` context for everything — rejected because it would create a single large context with 13+ tables and mixed concerns (test generation vs test execution); the constitution explicitly names both contexts in the repo structure.

---

## Decision 2: Qdrant Collection for Semantic Similarity

**Decision**: New collection `evaluation_embeddings` (1536-dim Cosine similarity, same vector size as `platform_memory`)

**Rationale**: Evaluation embeddings are transient scoring artifacts, not agent memory entries. Keeping them in a separate collection prevents memory retrieval pollution and allows independent TTL/cleanup policies. The SemanticSimilarityScorer computes embeddings for both the `actual_output` and `expected_output` of a benchmark case, stores them in Qdrant under the verdict's UUID as payload reference, then returns cosine similarity as the score.

**Alternatives considered**: Reuse `platform_memory` collection — rejected; mixes evaluation scoring artifacts with persistent agent memory and would require filtering on every memory retrieval query.

---

## Decision 3: ClickHouse for Behavioral Drift Metrics

**Decision**: New ClickHouse table `testing_drift_metrics` (MergeTree, partitioned by month) for raw score time-series. PostgreSQL table `testing_drift_alerts` for persisted alert records.

**Rationale**: The constitution §III mandates ClickHouse for all time-series analytics. Drift detection computes mean and standard deviation from historical scores — a classic OLAP aggregation. Raw metric rows go to ClickHouse; alert records (which need durable ACID semantics, workspace scoping, and acknowledgment state) go to PostgreSQL.

**Pattern reference**: Feature 022 (context-engineering) uses the same split: ClickHouse for `context_quality_scores` time-series + PostgreSQL for `context_drift_alerts`.

**Drift detection algorithm**: `SELECT avg(score), stddev(score) FROM testing_drift_metrics WHERE agent_fqn = ? AND eval_set_id = ? AND measured_at > now() - INTERVAL 30 DAY` → if current score < mean − (threshold × stddev), fire alert. Default threshold: 2.0 stddevs.

**Alternatives considered**: Store all drift data in PostgreSQL using window functions — rejected per constitution §III; never compute rollups in PostgreSQL.

---

## Decision 4: LLM-as-Judge Execution Model

**Decision**: Direct httpx calls to model provider interface, run synchronously N times for calibration. No delegation to the Go reasoning engine.

**Rationale**: The Go reasoning engine handles budget tracking, tree-of-thought branching, and self-correction convergence — not raw LLM inference calls. LLM-as-Judge is a scoring operation, not a reasoning session. The same model provider HTTP interface used by context_engineering/ (feature 022) is the correct integration point.

**Calibration**: Run judge N times sequentially (calibration_count). Collect per-criterion scores per run. Compute mean, stddev, confidence interval using Python `statistics` stdlib (no numpy/scipy dependency).

**Rubric templates**: Python constants (an enum or dict) — six built-in rubrics (correctness, helpfulness, safety, style, faithfulness-to-source, instruction-following) defined as static JSONB schemas. Custom rubrics are stored as JSONB within the EvalSet/scorer config — no separate database table needed.

**Alternatives considered**: Delegate to reasoning engine for token-budget-aware judge calls — rejected; evaluation is an offline batch operation, not a production inference path. Budget tracking is not required for judge calibration runs.

---

## Decision 5: ATE Execution Mechanics

**Decision**: ATE configs stored in PostgreSQL (`evaluation_ate_configs`). ATE execution delegates to `SimulationControllerClient` (gRPC, feature 012). Evidence artifacts stored in MinIO `evaluation-ate-evidence` bucket.

**Rationale**: The constitution §VII mandates simulation isolation. ATE runs agents in simulation sandboxes — this is exactly the SimulationController's scope. The `evaluation/` context defines what to test (config, golden pairs, scorers, thresholds); the simulation controller handles sandbox lifecycle. Evidence (full scenario outputs, logs) is object storage; the structured report summary stays in PostgreSQL `evaluation_ate_runs`.

**ATE pre-check**: Before execution, ATEService validates that all referenced scenarios exist and scorers are configured. If pre-check fails, `ATERun` is created with status `pre_check_failed` and no simulation is started.

**Reusability**: ATEConfig UUID is the stable identity. Any agent can be evaluated against the same config — each produces a separate `ATERun` row, enabling cross-agent comparison by querying `evaluation_ate_runs WHERE ate_config_id = ?`.

**Alternatives considered**: Implement ATE simulation inline without SimulationController — rejected; violates constitution §VII (simulation isolation) and duplicates Kubernetes namespace management logic.

---

## Decision 6: Trajectory Data Access

**Decision**: In-process service interface calls to `execution/` for journal events and task plan records. gRPC call to `ReasoningEngineClient` for reasoning traces.

**Rationale**: The constitution §IV prohibits cross-boundary DB table access. The `execution/` bounded context exposes `ExecutionQueryInterface` for reading journal events and task plans. The reasoning engine (Go service, feature 011) exposes trace retrieval via gRPC. `TrajectoryScorer` calls both to assemble the full trajectory artifact.

**Trajectory metrics computed**:
- `efficiency_score`: steps_taken / estimated_optimal_steps (estimated from task plan's declared subtask count)
- `tool_appropriateness_score`: correct_tool_calls / total_tool_calls (evaluated against task plan's tool selection rationale)
- `reasoning_coherence_score`: LLM-as-Judge sub-call evaluating chain-of-thought consistency (optional, configurable)
- `cost_effectiveness_score`: quality_score / token_cost_ratio (derived from execution cost in task plan record)
- `overall_trajectory_score`: weighted average of the four dimensions

**Alternatives considered**: Compute trajectory from Kafka event replay — rejected; too slow for synchronous scoring; journal is PostgreSQL-queryable via execution service interface.

---

## Decision 7: Adversarial Test Case Generation

**Decision**: LLM call via httpx to model provider. Agent config + capabilities fetched from `RegistryServiceInterface` (in-process). Generated cases stored as rows in `testing_adversarial_cases` + parent `testing_generated_suites`. Large suites (>500 cases) also archived to MinIO `evaluation-generated-suites` bucket.

**Rationale**: Test case generation is a creative LLM task. The agent's registered profile (tools, purpose, domain tags, capability declarations) provides the domain context for generating relevant adversarial inputs. This is the same registry service interface used by other contexts.

**Six adversarial categories**:
1. `prompt_injection`: inject instructions to override system prompt
2. `jailbreak`: bypass safety guardrails via roleplay/hypothetical framing
3. `contradictory`: inputs with mutually exclusive constraints
4. `malformed_data`: invalid schema, encoding issues, boundary values
5. `ambiguous`: inputs admitting multiple valid interpretations
6. `resource_exhaustion`: excessively long inputs, recursive references, pagination abuse

**Generation prompt**: Each category has a template prompt that includes agent context + category-specific adversarial patterns. The LLM generates 10 cases per category per generation run (configurable minimum: SC-004).

**Alternatives considered**: Rule-based adversarial generation (no LLM) — rejected; domain-specific adversarial cases require semantic understanding of the agent's purpose that rule-based templates cannot provide.

---

## Decision 8: Statistical Analysis (A/B and Robustness)

**Decision**: Python `statistics` stdlib only. No scipy/numpy/pandas dependency.

**Rationale**: The platform has no existing scientific computing dependency. Adding numpy/scipy for percentile and t-test functions is disproportionate overhead. Python 3.12 `statistics` module provides: `mean()`, `stdev()`, `quantiles()`, `NormalDist` (for confidence intervals). Welch's t-test can be implemented in ~20 lines of pure Python.

**A/B experiment statistics**:
- Welch's t-test (unequal variance) for comparing score distributions
- Cohen's d for effect size
- 95% confidence interval via NormalDist

**Robustness distribution**:
- `statistics.quantiles(scores, n=20)` for p5/p25/p50/p75/p95
- `statistics.mean()` and `statistics.stdev()` for mean/stddev
- Unreliable flag: `stdev > variance_threshold` (configurable, default: 0.15)

**Alternatives considered**: scipy.stats — rejected; adds ~50MB dependency for ~5 functions; pure Python achieves same results for these specific metrics.

---

## Decision 9: Kafka Topics

**Decision**: Single new topic `evaluation.events` produced by both `evaluation/` and `testing/` contexts. No new topics consumed.

**Rationale**: All evaluation and testing events share the same domain and can be filtered by event_type on the consumer side. This avoids topic proliferation. Drift alerts are push-notified through existing `notifications/` context consuming `evaluation.events`.

**Event types produced on `evaluation.events`**:
- `evaluation.run.started`, `evaluation.run.completed`, `evaluation.run.failed`
- `evaluation.verdict.scored`
- `evaluation.ab_experiment.completed`
- `evaluation.ate.run.completed`, `evaluation.ate.run.failed`
- `evaluation.robustness.run.completed`
- `evaluation.drift.detected`
- `evaluation.human.grade.submitted`

**Topics consumed**: None — evaluation is an offline batch system driven by REST API calls and APScheduler. It reads from PostgreSQL (execution journal) and ClickHouse (drift metrics) without Kafka consumer groups.

**Alternatives considered**: Separate `evaluation.events` and `testing.events` — rejected; unnecessary partition when both contexts have low event volume and share the same workspace/agent correlation dimensions.

---

## Decision 10: Alembic Migration Number

**Decision**: Migration `034` (single migration file covering all 13 PostgreSQL tables)

**Rationale**: All tables for this feature are introduced together with no dependency conflicts. Single migration reduces rollback complexity.

**Tables introduced by migration 034**:
1. `evaluation_eval_sets`
2. `evaluation_benchmark_cases`
3. `evaluation_runs`
4. `evaluation_judge_verdicts`
5. `evaluation_ab_experiments`
6. `evaluation_ate_configs`
7. `evaluation_ate_runs`
8. `evaluation_robustness_runs`
9. `evaluation_human_grades`
10. `testing_generated_suites`
11. `testing_adversarial_cases`
12. `testing_coordination_results`
13. `testing_drift_alerts`

---

## Decision 11: Runtime Profiles

**Decision**: REST API handlers run under `api` profile. Long-running eval orchestration (ATE execution, robustness N-trial loops, drift detection) run under `agentops-testing` profile via APScheduler and FastAPI BackgroundTasks.

**Rationale**: Per constitution §I, the platform runs as multiple runtime profiles from one codebase. The `agentops-testing` profile (already referenced in the constitution) is the correct home for evaluation background work.

**APScheduler jobs in `agentops-testing` profile**:
- Drift detection scanner: daily (configurable), queries ClickHouse per active (agent, eval_set) pair
- Robustness trial orchestrator: picks up pending robustness runs and spawns individual eval runs

**Alternatives considered**: Separate worker process for eval — rejected; the existing `agentops-testing` profile already exists for this exact purpose.

---

## Decision 12: SemanticSimilarityResult Storage

**Decision**: SemanticSimilarityResult is a Pydantic model serialized into `evaluation_judge_verdicts.scorer_results` JSONB field (not a separate table).

**Rationale**: `scorer_results` is a `dict[scorer_type, ScoreResult]` where each value is scorer-type-specific. For semantic scorer: `{score: float, passed: bool, threshold: float, embedding_distance: float}`. For LLM-judge: `{criteria_scores: dict, rationale: str, calibration_distribution: dict}`. This avoids a proliferation of narrow join tables.

**Qdrant vectors** (for semantic similarity): stored transiently during scoring, not permanently. The Qdrant collection `evaluation_embeddings` holds embeddings only during active evaluation runs; completed verdicts have their scores in PostgreSQL JSONB. Embeddings can be purged after run completion.

**Alternatives considered**: Separate `evaluation_semantic_results` table — rejected; adds a join for every verdict fetch with no query benefit since results are always fetched with their parent verdict.
