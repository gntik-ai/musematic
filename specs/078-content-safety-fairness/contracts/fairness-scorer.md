# Fairness Scorer Contract

**Feature**: 078-content-safety-fairness
**Modules**:
- `apps/control-plane/src/platform/evaluation/scorers/fairness.py` (NEW)
- `apps/control-plane/src/platform/evaluation/scorers/fairness_metrics.py` (NEW)

## Scorer Protocol implementation

```python
class FairnessScorer:
    """Scorer impl for the existing platform Scorer Protocol.

    Unlike per-case scorers (exact_match, regex, …), FairnessScorer is a
    suite-level scorer: its `score(...)` method is invoked once per
    (suite, agent_revision) run, with the full set of test-case outputs +
    expected outputs + group attributes already collected.
    """

    name = "fairness"

    async def score(
        self,
        actual: str,                              # ignored — interface compat
        expected: str,                            # ignored
        config: dict[str, Any],
    ) -> ScoreResult:
        ...

    async def score_suite(
        self,
        *,
        evaluation_run_id: UUID,
        agent_id: UUID,
        agent_revision_id: UUID,
        suite_id: UUID,
        cases: list[FairnessCase],
        config: FairnessScorerConfig,
    ) -> FairnessScorerResult:
        """The real entry point — invoked from evaluation/service.py."""
```

## Input shapes

```python
@dataclass(slots=True, frozen=True)
class FairnessCase:
    case_id: UUID
    actual: Any                          # model output (string / class / probability dict)
    expected: Any                        # ground truth (optional — required for equal_opportunity)
    group_attributes: dict[str, str]     # {"gender": "f", "language": "es"} — may be missing keys
    probabilities: dict[str, float] | None  # required for calibration

class FairnessScorerConfig(BaseModel):
    metrics: list[Metric] = ["demographic_parity", "equal_opportunity", "calibration"]
    group_attributes_to_evaluate: list[str] | None = None  # None → all attrs present
    fairness_band: float = 0.10
    min_group_size: int = 5
    deterministic: bool = True

class FairnessScorerResult(BaseModel):
    evaluation_run_id: UUID
    per_metric_per_attribute: list[FairnessMetricRow]
    coverage: dict[str, dict[str, int]]    # {attr: {group: count}}
    overall_passed: bool                    # True only if all per-metric passed=True
    notes: list[str]                        # e.g. "calibration unsupported on classification-only output"
```

## Metric implementations

### Demographic parity

```python
def demographic_parity(
    cases: list[FairnessCase], attr: str, *, predicted_positive_fn
) -> tuple[dict[str, float], float]:
    """Returns (per_group_rate, spread)."""
    grouped = defaultdict(list)
    for c in cases:
        if attr not in c.group_attributes:
            continue
        grouped[c.group_attributes[attr]].append(predicted_positive_fn(c.actual))
    per_group = {g: sum(v)/len(v) for g, v in grouped.items() if len(v) >= MIN_GROUP_SIZE}
    if len(per_group) < 2:
        raise InsufficientGroupsError(attr)
    spread = max(per_group.values()) - min(per_group.values())
    return per_group, spread
```

`predicted_positive_fn` defaults to `lambda actual: actual == suite.positive_class`. Configurable per suite.

### Equal opportunity

Same shape as demographic_parity but per-group rate is computed only on cases where `expected == positive_class` (true positive rate, TPR).

### Calibration

For agents that produce probability outputs:

```python
def calibration_brier(cases, attr) -> dict[str, float]:
    # Brier score: mean((predicted_prob - actual_outcome)**2) per group.
    ...
```

Pass condition: `max(per_group_brier) - min(per_group_brier) <= fairness_band` (lower is better, so spread is the relevant statistic).

## Determinism

- Aggregate computations (demographic_parity, equal_opportunity, Brier) are deterministic given the same inputs — pure NumPy / SciPy with no RNG.
- For stochastic providers (LLM-as-judge supplying labels), the scorer sets temperature 0 and a fixed seed where the provider supports it. Documented epsilon tolerance: 0.001 (per spec SC-009).

## Group-attribute privacy (rule 22, FR-031)

- The scorer NEVER logs group-attribute values as observability labels.
- Per-individual group_attributes are read from the existing `evaluation_test_cases` PostgreSQL table; access is audited (rule 9).
- Persisted output (`fairness_evaluations` row) holds only aggregates per group; per-individual data does not leave the input table.

## REST endpoints

Under `/api/v1/evaluations/fairness/*`:

| Method + path | Purpose | Role |
|---|---|---|
| `POST /api/v1/evaluations/fairness/run` | Trigger a fairness evaluation against a (suite, agent_revision); returns `evaluation_run_id`; current local implementation completes inline while preserving HTTP 202 and emits `evaluation.fairness.completed`. | `evaluator` for the workspace, `workspace_admin`, `superadmin` |
| `GET /api/v1/evaluations/fairness/runs/{evaluation_run_id}` | Get the result (per-metric, per-attribute rows, overall_passed). | same |

`POST /run` body:

```python
class FairnessRunRequest(BaseModel):
    agent_revision_id: UUID
    suite_id: UUID
    config: FairnessScorerConfig | None = None  # None → workspace defaults
```

Response:

```python
class FairnessRunResponse(BaseModel):
    evaluation_run_id: UUID
    status: Literal["pending", "running", "completed", "failed"]
    # full result populated only when status="completed"
    result: FairnessScorerResult | None
```

## Persistence

- Each (metric, attribute) row of `FairnessScorerResult.per_metric_per_attribute` becomes one `fairness_evaluations` row.
- The suite-level `evaluation_run_id` ties them together for round-tripping.
- `FairnessEvaluationCompleted` event emitted on `evaluation.events` after persistence.

## Unit-test contract

- **FS1** — score_suite produces deterministic output for deterministic input (re-run ε ≤ 0.001 — SC-009).
- **FS2** — case missing group attribute is excluded from group-aware metrics for that attr; `coverage` reflects exclusion.
- **FS3** — group with fewer than `min_group_size` cases excluded; reported in `coverage`; doesn't fail the run.
- **FS4** — single-group attribute → `notes` includes `insufficient_groups`; metric row absent for that attr.
- **FS5** — calibration on classification-only output → `notes` includes `unsupported`; calibration row absent; parity / equal_opportunity computed normally.
- **FS6** — `passed=true` iff `spread <= fairness_band` per metric per attribute.
- **FS7** — group-attribute values not present in any structlog field captured during the run.
- **FS8** — REST `POST /run` accepts request, returns immediately with `status="pending"`, scorer runs asynchronously, persistence completes within budget.
- **FS9** — `GET .../latest` returns the most recent evaluation_run_id with `overall_passed=True` for the given agent_revision_id.
- **FS10** — Audit-chain entries emitted on each metric computation (rule 9 — group-attribute access).
