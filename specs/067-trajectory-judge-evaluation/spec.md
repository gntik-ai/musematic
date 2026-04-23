# Feature Specification: Trajectory Evaluation and LLM-as-Judge Formalization

**Feature Branch**: `067-trajectory-judge-evaluation`  
**Created**: 2026-04-19  
**Status**: Draft  
**Input**: Brownfield addition to the evaluation framework. Introduces two new first-class scorer categories — **Trajectory Scoring** (evaluates the full action path an agent took: tool choices, ordering, reasoning coherence, cost-effectiveness; supports five comparison methods against a reference path; extends to multi-agent cooperation) and **LLM-as-Judge Scoring** (evaluates outputs against configurable rubrics composed of criteria, scales, and reference examples; supports calibration runs that characterize a rubric-plus-judge combination; ships six built-in rubric templates). Both scorer categories register through the existing evaluation-framework registry, run inside the standard evaluation pipeline, and are exposed via the existing evaluation API surface plus one additional ad-hoc judge endpoint.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Evaluation Author Scores an Agent Trajectory Against a Reference Path (Priority: P1)

An evaluation author has an agent whose correctness depends on not just the final answer, but the sequence of tool calls, parameters, and reasoning steps it used to get there. They define an expected trajectory (the "golden path") and select one of the five comparison methods: exact sequence match, in-order allowing gaps, any-order, precision (did every taken step belong to the expected set?), or recall (did every expected step appear?). They run an evaluation; the trajectory scorer returns a multi-dimensional score per attempted execution — path efficiency, tool appropriateness, reasoning coherence, cost-effectiveness — alongside the comparison-method score.

**Why this priority**: Trajectory evaluation is the primary differentiator of this feature. Existing scorer types (exact_match, semantic, regex, json_schema) only evaluate final outputs. Many real failures are "right answer, wrong path" (unnecessary tool calls, wasted budget, hidden risks) that only trajectory-level scoring surfaces. Without it, the evaluation framework cannot detect cost regressions, policy-drift behaviors, or silent degradation of reasoning quality. P1 because this is what the constitution mandates ("Evaluate trajectories, not just outputs" — Reminder 26) and it unlocks every downstream use case (calibration, cooperation, regression testing).

**Independent Test**: Author an expected trajectory with three tool calls in a specific order. Run the agent twice: once producing the exact sequence, once producing the same tools but reordered. Select the `in_order` comparison method for the first run — expect score 1.0. Select the `exact` comparison method for the second run — expect score < 1.0 with a clear indication of the misordering. Independently verify that each of the four multi-dimensional scores (path efficiency, tool appropriateness, reasoning coherence, cost-effectiveness) is computed and returned.

**Acceptance Scenarios**:

1. **Given** an agent execution that produced a recorded trajectory and an expected trajectory defined for the same task, **When** the trajectory scorer runs with the `exact` comparison method, **Then** the scorer returns a score reflecting exact-sequence alignment plus four multi-dimensional scores.
2. **Given** the same execution with a reordering of tool calls, **When** the author compares with the `any_order` method, **Then** the scorer treats order as irrelevant and returns a score based on set membership; if all expected steps appeared, the comparison score is 1.0.
3. **Given** an execution where the agent took two extra unrequested tool steps, **When** the scorer runs with the `precision` method, **Then** precision reflects the fraction of taken steps that were expected; the extra steps reduce precision below 1.0.
4. **Given** an execution missing one of the expected tool calls, **When** the scorer runs with the `recall` method, **Then** recall reflects the fraction of expected steps that appeared; the missing step reduces recall below 1.0.
5. **Given** a trajectory with high reasoning-step count but fewer actual tool calls than expected, **When** the scorer computes path efficiency, **Then** the efficiency score reflects the ratio of meaningful progress to total steps, independent of the comparison method.
6. **Given** an execution whose tool-call cost exceeds typical-task cost by a threshold, **When** cost-effectiveness is scored, **Then** the scorer returns a lower cost-effectiveness value with the observed/expected cost delta included in the result.

---

### User Story 2 — Evaluation Author Defines a Rubric and Scores Outputs with an LLM Judge (Priority: P1)

An evaluation author wants to judge agent outputs against criteria that are too subjective for regex or exact-match scorers (e.g., "is this explanation faithful to the source document?", "is this tone appropriate for a customer email?"). They author a rubric consisting of a name, one or more criteria, each with a numeric scale and per-point reference examples. They point the LLM-as-Judge scorer at a configured judge model and run it against their evaluation set. The scorer returns, per output, a structured verdict: a score per criterion, an overall score, and a short rationale. The verdicts are auditable — every verdict records the rubric version, judge model, and timestamp.

**Why this priority**: Rubric-driven judging fills the gap between purely mechanical scorers and human review. Without it, quality signals for subjective dimensions (helpfulness, style, faithfulness) require manual labelling that does not scale. P1 because (a) three of the six standard templates listed in scope (helpfulness, style, faithfulness) are only realistically evaluable by LLM judges, and (b) the trajectory scorer itself depends on the rubric primitive for its reasoning-coherence dimension.

**Independent Test**: Author a correctness rubric with two criteria (factual_accuracy, completeness), each on a 1–5 scale with three reference examples per score. Run the judge scorer against a small set of known-good and known-bad outputs. Verify that each output receives a structured verdict with per-criterion scores and an overall score, that verdicts record the rubric version and judge model, and that re-running the same judge against the same input produces verdicts within a stable range (small variance).

**Acceptance Scenarios**:

1. **Given** a rubric defined with criteria, scales, and examples, **When** the judge scorer runs against an output, **Then** it returns a structured verdict with a numeric score per criterion and a short rationale.
2. **Given** a verdict produced by the judge scorer, **When** an auditor inspects it, **Then** the rubric version, judge model reference, principal, and timestamp are all present; verdicts are immutable after recording.
3. **Given** a judge scorer invoked against an output that violates a criterion, **When** the verdict returns, **Then** the criterion score sits at or below the midpoint of the declared scale and the rationale cites the violation.
4. **Given** a rubric whose criteria include examples for each scale point, **When** the judge scorer runs, **Then** the examples are supplied to the judge at scoring time so the judge applies consistent scale interpretation.
5. **Given** a judge verdict whose overall score aggregates per-criterion scores, **When** the aggregation method is unspecified by the rubric, **Then** a clear, documented default (arithmetic mean across criteria) is applied and surfaced in the verdict metadata.

---

### User Story 3 — All Existing Scorer Types Continue to Produce Identical Results (Priority: P1)

An SRE responsible for evaluation stability needs confidence that introducing new scorer categories does not perturb pre-existing evaluations. The pre-existing scorer types (exact_match, semantic, regex, json_schema) must produce byte-identical results before and after this feature ships. The scorer registry must support adding new categories without renaming, renumbering, or reordering existing ones; persisted evaluation records referencing pre-existing scorer types must continue to load and re-run.

**Why this priority**: A new scorer release is a trust event. If pre-existing evaluation results silently shift, teams lose confidence in the framework and cannot safely upgrade. P1 because the constitution's Brownfield Rule 3 ("Preserve all existing tests") mandates this and because regression risk is the highest single blocker to release.

**Independent Test**: Snapshot the output of the existing four scorer types on a known evaluation set before the feature lands. Apply the feature. Re-run the same evaluation set using the same scorer configurations. Compare: 100% of scores must be byte-identical. Verify: no existing persistence structures changed incompatibly; the scorer registry can enumerate both old and new scorer types without duplication.

**Acceptance Scenarios**:

1. **Given** a saved evaluation that uses only pre-existing scorer types, **When** the evaluation is re-run after this feature ships, **Then** every score is byte-identical to the pre-feature baseline.
2. **Given** the scorer registry, **When** it is queried for available scorer types, **Then** the pre-existing four types and the two new types (trajectory, llm_judge) appear together without name collisions.
3. **Given** a persisted evaluation-run record whose scorer is pre-existing, **When** the record is loaded for display or re-execution, **Then** loading succeeds with no migration error.
4. **Given** a user configures an evaluation using only pre-existing scorers, **When** the evaluation runs, **Then** no code paths related to trajectory or judge scoring execute, and no extra latency is introduced.

---

### User Story 4 — Quality Engineer Calibrates a Rubric Against Reference Examples (Priority: P2)

A quality engineer receives a new rubric from an evaluation author and needs to know whether the rubric + judge combination produces stable, well-distributed scores before they rely on it in production evaluations. They submit a calibration run: a set of reference examples paired with target score ranges, executed against the rubric and judge. The calibration report returns the score distribution (minimum, maximum, mean, standard deviation, histogram by score bucket), the agreement rate with reference ranges, and flags any criteria whose scores cluster at one extreme (indicating the rubric fails to discriminate).

**Why this priority**: Calibration is an operational-maturity layer — without it, evaluation authors can deploy a rubric that silently produces all-3s or all-5s, masking quality changes. P2 because basic judge scoring (US2) is usable without calibration; calibration is a readiness gate, not a blocker for first use. Teams that need reliable judges need calibration; teams exploring a rubric for the first time do not.

**Independent Test**: Create a calibration set with 20 examples spanning the full score range (5 examples per score band). Submit a calibration run against a rubric and judge. Verify the report contains: score distribution statistics, histogram, per-criterion distribution, agreement rate, low-discrimination flags. Verify that running the same calibration twice yields similar statistics within a documented variance envelope.

**Acceptance Scenarios**:

1. **Given** a rubric and a set of reference examples each labelled with an expected score range, **When** a calibration run completes, **Then** the calibration report contains distribution statistics per criterion and overall.
2. **Given** a calibration run where the judge produces all scores at one end of the scale, **When** the report is generated, **Then** a "low discrimination" flag is raised for the affected criteria.
3. **Given** a calibration run, **When** an auditor inspects it, **Then** the report references the rubric version, the judge model, the reference set identifier, and the timestamp, and is immutable after completion.
4. **Given** two calibration runs of the same rubric and judge against the same reference set, **When** their reports are compared, **Then** summary statistics agree within a documented variance envelope (the judge is reproducible enough to trust).

---

### User Story 5 — Built-in Rubric Templates Available for Common Evaluation Scenarios (Priority: P2)

An evaluation author writing their first judge-scored evaluation does not want to author a rubric from scratch. They browse the built-in rubric library and select from six standard templates: correctness, helpfulness, safety, style, faithfulness, and instruction_following. Each template ships with defined criteria, scales, and reference examples. The author either uses the template directly or copies it as a starting point for a customized variant. Templates are versioned and updates are additive (new templates may be added; existing templates are not silently altered).

**Why this priority**: Templates are an adoption lever, not a correctness requirement. An author with deep familiarity with their domain can author a rubric from scratch. P2 because the absence of templates does not block any evaluation; it only raises the authoring cost. Six templates was chosen to cover the most common evaluation needs across the platform's surfaces without bloating the library.

**Independent Test**: Query the library for available templates. Verify exactly the six templates exist with expected names. Select the "correctness" template and use it directly in an evaluation; verify it scores outputs successfully without modification. Copy the "helpfulness" template, modify one criterion's examples, and save as a new rubric; verify the original template is unchanged.

**Acceptance Scenarios**:

1. **Given** the built-in rubric library, **When** it is queried by an author, **Then** exactly six templates (correctness, helpfulness, safety, style, faithfulness, instruction_following) are listed.
2. **Given** a built-in template, **When** an author uses it in an evaluation without modification, **Then** the template is applied as-is and scores are produced.
3. **Given** a built-in template, **When** an author copies it to create a custom rubric, **Then** the custom rubric becomes an independent entity; subsequent changes to the built-in template do not affect the copy.
4. **Given** a built-in template, **When** the template set is updated with a new additive template, **Then** existing templates keep their names, criteria, and examples; existing evaluations referencing them are unaffected.

---

### User Story 6 — Multi-Agent Fleet Cooperation Trajectory Scoring (Priority: P3)

A fleet operator running a multi-agent workflow wants to evaluate not just individual agent trajectories but how the agents cooperated: did hand-offs happen at the right time, did agents avoid redundant work, was the joint path efficient? The trajectory scorer is extended with a cooperation mode that accepts trajectories from two or more agents that participated in the same workflow execution and scores cooperation dimensions (coordination overhead, hand-off timeliness, redundancy, joint path efficiency) alongside the per-agent scores.

**Why this priority**: Multi-agent cooperation scoring is a natural extension of the single-agent trajectory scorer but is not on the critical path for fleet reliability. Many fleets can be evaluated adequately by aggregating per-agent trajectory scores. P3 reflects this: it is a hardening layer that matures the framework once the single-agent case is stable.

**Independent Test**: Run a two-agent workflow with a known cooperation pattern (e.g., agent A produces a draft, agent B reviews and revises). Run the trajectory scorer in cooperation mode. Verify the output includes per-agent scores and cooperation-dimension scores (coordination overhead, hand-off timeliness, redundancy, joint path efficiency). Compare with the same workflow where one agent redoes work the other already did; verify redundancy score decreases.

**Acceptance Scenarios**:

1. **Given** a multi-agent workflow execution with recorded trajectories for two or more agents, **When** the trajectory scorer runs in cooperation mode, **Then** it returns per-agent scores plus cooperation-dimension scores.
2. **Given** a cooperation scoring run, **When** one agent repeats work another already did, **Then** the redundancy score reflects the overlap and flags the redundant steps.
3. **Given** a cooperation scoring run where hand-offs occur after prolonged idle time, **When** the hand-off timeliness score is computed, **Then** it reflects the delay and surfaces the problematic hand-off windows.

---

### Edge Cases

- **Empty trajectory**: An agent execution that produced zero actions is scored with a well-defined zero-path result (comparison score 0 or N/A per method); an error is NOT raised.
- **Trajectory with missing tool metadata**: When a trajectory step lacks the metadata needed for tool-appropriateness scoring, that dimension is flagged unscored for that step; other dimensions still compute.
- **Rubric criterion with score outside declared scale**: A judge that returns a criterion score outside the declared scale triggers a calibration warning; the verdict is persisted with the clamped score and an out-of-range annotation.
- **Malformed judge verdict**: When the judge returns non-parseable or schema-invalid structured output, the scorer treats it as a judge-failure (classified as transient or permanent); re-tries are bounded and the evaluation result records the failure classification rather than silently falling back.
- **Low-confidence calibration**: Calibration runs with wide variance across repeated identical prompts surface a confidence warning in the report.
- **Rubric mid-run deletion**: A rubric referenced by an in-flight evaluation run cannot be deleted; deletion is rejected with a clear message; the rubric may be archived (new runs blocked) but in-flight runs proceed to completion on the archived version.
- **Circular multi-agent coordination**: Cooperation mode detects cycles (agent A handed to B handed back to A in a short window without progress); these are flagged with a high coordination-overhead score.
- **Judge model unavailable**: When the configured judge model is unreachable, the evaluation run fails fast with a clear "judge unavailable" classification; partial verdicts are not recorded.
- **Oversized trajectory**: Trajectories exceeding a configurable maximum step count are truncated for scoring with an explicit truncation flag on the result; underlying data is preserved.
- **Contradictory rubric examples**: At rubric save time, the platform detects and rejects a rubric in which the same score value has contradictory reference examples within one criterion.
- **Missing cost data**: When cost-effectiveness data is missing from a trajectory, cost-effectiveness is marked unscored and omitted from the aggregated result rather than defaulting to zero.
- **Judge disagrees with all references in calibration**: A calibration run whose judge verdicts disagree with every reference label raises an error-grade finding in the report and prevents the rubric from being marked "calibrated".
- **Backward-compatibility**: Pre-existing evaluations that use only the four original scorer types run with no change in result; registry order, storage schema, and API response shapes for those scorers are untouched.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The platform MUST provide a trajectory scorer that accepts an agent's recorded trajectory and an expected trajectory and returns a comparison score plus four multi-dimensional scores (path efficiency, tool appropriateness, reasoning coherence, cost-effectiveness).
- **FR-002**: The trajectory scorer MUST support five comparison methods — exact, in-order (allowing gaps), any-order, precision, recall — selectable per evaluation; each method MUST compute a valid numeric score for any pair of non-empty trajectories.
- **FR-003**: The trajectory scorer MUST compute scores for empty trajectories without raising errors; empty-trajectory semantics are defined per dimension (e.g., comparison score 0, dimension scores N/A).
- **FR-004**: The trajectory scorer MUST compute path efficiency as a measure of meaningful progress per trajectory step; tool appropriateness based on whether each invoked tool was suitable for the reasoning step; reasoning coherence based on whether reasoning-step outputs are consistent across the path; cost-effectiveness based on observed cost vs. typical-task cost, with clear fall-through when cost data is absent.
- **FR-005**: The trajectory scorer MUST expose a multi-agent cooperation mode that takes trajectories from two or more agents in the same workflow execution and returns cooperation scores (coordination overhead, hand-off timeliness, redundancy, joint path efficiency) alongside per-agent scores.
- **FR-006**: The platform MUST provide an LLM-as-Judge scorer that evaluates outputs against a rubric using a configured judge model and returns a structured verdict with per-criterion scores, an overall score, and a rationale.
- **FR-007**: Rubrics MUST be defined by name, one or more criteria, a numeric scale per criterion with declared min/max, and reference examples at one or more points of each scale; the examples MUST be supplied to the judge at scoring time so scale interpretation is consistent.
- **FR-008**: Rubrics MUST be validated at save time for structural correctness; a rubric whose criteria contain contradictory examples at the same scale point MUST be rejected with a clear error.
- **FR-009**: Rubrics MUST be versioned; every recorded verdict MUST reference the rubric version used; archived rubric versions MUST remain loadable for re-execution of past evaluations.
- **FR-010**: Judge verdicts MUST be immutable once persisted; each verdict MUST include rubric version, judge model reference, principal identity, and timestamp.
- **FR-011**: When the judge returns a criterion score outside the declared scale, the scorer MUST clamp the score to the scale bounds and flag the verdict with an out-of-range annotation; the original judge output MUST be retained for audit.
- **FR-012**: When a judge returns a malformed or schema-invalid structured output, the scorer MUST classify the failure as transient or permanent, attempt bounded retries for transient failures, and surface the final classification on the evaluation result rather than silently recording a synthetic verdict.
- **FR-013**: The platform MUST provide a calibration-run capability that accepts a rubric, a judge configuration, and a reference set (examples paired with expected score ranges) and returns a report with distribution statistics per criterion and overall (min, max, mean, standard deviation, histogram), agreement rate against the reference ranges, and per-criterion low-discrimination flags.
- **FR-014**: Calibration reports MUST be immutable after generation and MUST reference rubric version, judge model, reference-set identifier, and timestamp.
- **FR-015**: A rubric MUST NOT be marked "calibrated" if its calibration run produced judge verdicts that disagreed with every reference label; this condition MUST be surfaced as an error-grade finding in the calibration report.
- **FR-016**: The platform MUST ship six built-in rubric templates at feature launch: correctness, helpfulness, safety, style, faithfulness, instruction_following; each template MUST be complete (criteria, scales, reference examples) and usable without modification.
- **FR-017**: Built-in templates MUST be copy-able to create custom rubrics; copies MUST be independent of the original; updates to a template MUST NOT alter any existing copy.
- **FR-018**: Built-in templates MUST be versioned; additions to the template set MUST be additive — adding a new template MUST NOT rename, remove, or alter existing templates.
- **FR-019**: The scorer registry MUST enumerate all available scorer types, including pre-existing types (exact_match, semantic, regex, json_schema) and the new types (trajectory, llm_judge), without name collisions; the registry MUST NOT reorder or rename pre-existing types.
- **FR-020**: Pre-existing scorer types MUST produce byte-identical results for the same inputs before and after this feature ships; no code path change introduced for new scorers may alter execution of pre-existing scorers.
- **FR-021**: Persisted evaluation records created before this feature MUST continue to load and re-run; storage schema changes MUST be additive only.
- **FR-022**: The platform MUST expose an ad-hoc judging capability that accepts a rubric reference and an output value and returns a verdict without requiring an evaluation run to be configured; rate limits, authentication, and authorization MUST apply identically to this capability as to full evaluation runs.
- **FR-023**: Trajectory and judge scorer invocations MUST be observable — every invocation MUST log principal, scorer type, rubric version (if applicable), judge model (if applicable), duration, and outcome classification (success, transient failure, permanent failure).
- **FR-024**: A rubric referenced by at least one in-flight evaluation run MUST NOT be deletable; rubric archival (new-run-blocking) MUST be permitted and MUST NOT affect in-flight runs.
- **FR-025**: Trajectories exceeding a configurable maximum step count MUST be truncated for scoring purposes with an explicit truncation flag on the result; the underlying trajectory data MUST remain intact.
- **FR-026**: When cost data is missing from a trajectory, the cost-effectiveness dimension MUST be omitted from the result rather than substituted with a default value; downstream aggregations MUST handle the missing value transparently.
- **FR-027**: Judge model unavailability MUST produce a fast-failing evaluation run with a clear classification; partial verdicts MUST NOT be recorded in this case.
- **FR-028**: Multi-agent cooperation scoring MUST detect coordination cycles (hand-offs between the same agents without progress) and surface them in the coordination-overhead dimension with explicit cycle flags.

### Key Entities

- **Recorded Trajectory**: An immutable sequence of agent actions captured during an execution — steps, invoked tools, tool parameters, reasoning outputs, costs. Produced by the existing execution layer; consumed by the trajectory scorer.
- **Expected Trajectory**: A reference sequence authored for comparison — an ordered or unordered set of expected tool calls, possibly with parameter constraints. Referenced by trajectory evaluations; versioned.
- **Trajectory Score Result**: The output of a single trajectory scoring — comparison method applied, comparison score, four dimension scores, and truncation/missing-data annotations.
- **Rubric**: Named, versioned definition of judging criteria — one or more criteria, each with name, numeric scale bounds, and reference examples. Built-in templates are rubrics flagged as non-user-editable.
- **Judge Verdict**: The immutable record of a single judge scoring — per-criterion scores, overall score, rationale, rubric version, judge model reference, principal, timestamp, and any out-of-range/clamp annotations.
- **Calibration Run**: A recorded assessment of a rubric plus judge against a labelled reference set — distribution statistics, histogram, per-criterion discrimination flags, agreement rate, and final calibration outcome (calibrated, failed, pending-revision).
- **Built-in Rubric Template**: A platform-owned rubric shipped with the framework — correctness, helpfulness, safety, style, faithfulness, instruction_following.
- **Scorer Type Registration**: Record of an available scorer in the evaluation registry — identifier, category (deterministic, semantic, trajectory, judge), configuration schema, input requirements.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of recorded agent executions yield a trajectory artifact that the trajectory scorer can consume; zero executions produce a trajectory that cannot be scored for structural reasons.
- **SC-002**: All five trajectory comparison methods (exact, in-order, any-order, precision, recall) return a valid score for every pair of non-empty trajectories in a test corpus of at least 50 paired trajectories.
- **SC-003**: The four trajectory dimensions (path efficiency, tool appropriateness, reasoning coherence, cost-effectiveness) return scores or explicit "unscored" annotations for 100% of scored trajectories; no silent zero-substitution occurs.
- **SC-004**: LLM-as-Judge scorer returns structured verdicts with per-criterion scores for 100% of judgeable outputs; verdicts not returnable due to judge failure are explicitly classified (transient or permanent) with zero silent fallbacks.
- **SC-005**: 100% of judge verdicts record rubric version, judge model, principal, and timestamp; auditors can reproduce or trace any verdict from its recorded metadata.
- **SC-006**: Calibration runs report score distribution statistics (min, max, mean, standard deviation, histogram) for every criterion plus overall; low-discrimination criteria are flagged in 100% of runs where applicable.
- **SC-007**: Repeated calibration runs of the same rubric + judge + reference set produce summary statistics within a documented variance envelope; judges with variance beyond the envelope are flagged not calibrated.
- **SC-008**: Six built-in rubric templates (correctness, helpfulness, safety, style, faithfulness, instruction_following) are available at feature launch; each runs successfully against a sample corpus without author-side modification.
- **SC-009**: Template updates are strictly additive; 100% of existing evaluations referencing a built-in template continue to produce verdicts with the template version they were pinned to.
- **SC-010**: Pre-existing scorer types (exact_match, semantic, regex, json_schema) produce byte-identical results before and after this feature ships on a reference evaluation set of at least 100 cases; regression is zero.
- **SC-011**: Pre-existing persisted evaluation records load and re-run successfully at a rate of 100%; no record requires manual migration.
- **SC-012**: The scorer registry enumerates all six scorer types (four pre-existing + two new) without name collisions and without reordering pre-existing entries.
- **SC-013**: Ad-hoc judge invocations return a verdict within a 30-second p95 latency budget under typical evaluation load; failures are classified and surfaced within the same budget.
- **SC-014**: Trajectories exceeding the configurable maximum step count are truncated with an explicit truncation flag on the result in 100% of cases; no silent data loss.
- **SC-015**: Rubrics referenced by in-flight evaluations cannot be deleted; deletion attempts are rejected in 100% of cases while the rubric is referenced.
- **SC-016**: Multi-agent cooperation scoring detects coordination cycles with zero false negatives on a reference test set of synthetic cyclic workflows.

## Assumptions

- Existing agent executions already produce recorded trajectories (tool calls, reasoning steps, costs) in a consumable form; if some executions do not, adding a trajectory artifact to them is considered prerequisite work covered by the existing execution surface, not by this feature.
- The existing evaluation framework supports registering new scorer types through its registry without requiring changes to other scorer types.
- The existing evaluation API surface supports additive endpoints; the ad-hoc judging endpoint is an additive route that does not conflict with any existing route.
- Judge model configuration (provider, model identifier, authentication, rate limits) is managed by an existing model-routing surface; this feature configures which judge model to use, not how to reach it.
- Rubric storage uses the platform's existing persistence surface for configuration-type data; additive storage schema changes are backward-compatible.
- Reference examples in rubrics are stored by value, not by external reference, so templates remain self-contained and portable.
- Default rubric aggregation (when unspecified) is the arithmetic mean across criteria; other aggregation methods may be introduced later as optional rubric fields.
- Default trajectory maximum step count is 10000; this is operator-configurable.
- Default transient-failure retry count for judge calls is 2; this is operator-configurable.
- Calibration variance envelope default is: mean deviation ≤ 0.2 scale points across repeated runs; operator-configurable.
- Multi-agent cooperation scoring requires trajectories from at least two agents in the same workflow execution; single-agent workflows do not produce cooperation scores.
- Reference sets for calibration are stored as first-class evaluation fixtures using the existing evaluation-fixture surface.
- Rubric archival is a soft-delete state in which new evaluations cannot reference the rubric but in-flight and persisted evaluations remain intact.
- The "faithfulness" rubric template assumes a source document is supplied at scoring time; outputs unlinked to a source fall back to a degraded faithfulness judgment with a clear metadata annotation.
- No new authentication, authorization, or audit primitives are required; this feature reuses existing evaluation, policy, and audit surfaces.

## Dependencies

- Existing evaluation framework scorer registry (for registering two new scorer types).
- Existing evaluation pipeline and run orchestration (for executing trajectory and judge scorers alongside pre-existing scorers).
- Existing model-routing / LLM-provider surface (for invoking the configured judge model).
- Existing execution layer that captures recorded trajectories (tool calls, reasoning steps, costs).
- Existing evaluation-fixture surface (for calibration reference sets).
- Existing persistence surface for rubrics and calibration-run records (additive schema changes only).
- Existing authentication, authorization, and audit surfaces (reused for the ad-hoc judging endpoint and verdict recording).
- Existing monitoring surface (for scorer invocation observability).

## Out of Scope

- Training or fine-tuning judge models — judges are used as configured LLM inferences only.
- Human-in-the-loop review workflows that override judge verdicts — verdicts are recorded as-is; human re-judgment is a separate future feature.
- Non-numeric judge verdicts (e.g., free-form qualitative labels) — every judge verdict yields numeric per-criterion scores on a declared scale.
- Cross-rubric ensembling (combining multiple judges into a single verdict) — only single-judge, single-rubric scoring is supported this release.
- Real-time streaming of trajectory scores during execution — scoring runs post-execution against recorded trajectories.
- Automatic rubric generation from examples — rubrics are authored explicitly or copied from templates.
- Evaluation-driven agent self-improvement (closed-loop retraining) — feedback loops are out of scope.
- UI authoring tools for rubrics and expected trajectories — this release delivers API/backend capabilities; UI is a separate initiative.
- New authentication primitives for ad-hoc judging — reuses existing auth surface.
- Delta scoring against a prior evaluation run (regression diffs) — baseline comparison is deferred.
- Cost-weighted judge routing (picking cheaper judges for low-stakes scoring) — model choice is static per rubric configuration.
