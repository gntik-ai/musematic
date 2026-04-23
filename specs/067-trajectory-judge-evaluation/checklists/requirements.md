# Specification Quality Checklist: Trajectory Evaluation and LLM-as-Judge Formalization

**Purpose**: Validate specification completeness and quality before proceeding to planning  
**Created**: 2026-04-19  
**Feature**: [spec.md](../spec.md)

## Content Quality

- [X] No implementation details (languages, frameworks, APIs) — spec uses logical domain terms: "scorer registry", "trajectory artifact", "rubric template", "judge verdict", "calibration report". The user-input brownfield file list mentions `evaluation/scorers/` and similar paths; those paths stay in the input context, not the spec body.
- [X] Focused on user value and business needs — six user stories frame concrete personas (evaluation author, SRE, quality engineer, fleet operator) with delivered outcomes (trajectory regression detection, subjective scoring, no regression, rubric calibration, template reuse, cooperation scoring).
- [X] Written for non-technical stakeholders — plain language: "right answer, wrong path", "rubrics composed of criteria, scales, and reference examples", "judge returns all scores at one end of the scale".
- [X] All mandatory sections completed — User Scenarios (6 stories), Requirements (28 FRs + 8 entities), Success Criteria (16 SCs) all populated.

## Requirement Completeness

- [X] No [NEEDS CLARIFICATION] markers remain — defaults chosen explicitly: five comparison methods named (FR-002), four trajectory dimensions named (FR-004), six templates named (FR-016), arithmetic mean as default aggregation (Assumption), trajectory max step count default 10000 (Assumption), judge retry default 2 (Assumption), variance envelope default 0.2 (Assumption), rubric archival as soft-delete (Assumption), single judge per rubric (Out of Scope), numeric verdicts only (Out of Scope).
- [X] Requirements are testable and unambiguous — each FR uses MUST/MUST NOT with verifiable conditions (FR-002 "valid numeric score for any pair of non-empty trajectories"; FR-008 "rejected with a clear error"; FR-011 "clamp the score to the scale bounds and flag the verdict"; FR-020 "byte-identical results before and after"; FR-024 "MUST NOT be deletable while in-flight").
- [X] Success criteria are measurable — SC-001/002/003/004/005/006/008/009/010/011/012/014/015/016 (100% / zero); SC-007 (repeatable within documented envelope); SC-013 (30s p95 latency).
- [X] Success criteria are technology-agnostic — phrased as user-observable outcomes (verdicts produced, distribution statistics reported, byte-identical legacy scores, cycle detection rates) without naming Python libraries, HTTP frameworks, databases, or specific LLM providers.
- [X] All acceptance scenarios are defined — 6 user stories × 3–6 Given/When/Then scenarios each (US1: 6; US2: 5; US3: 4; US4: 4; US5: 4; US6: 3).
- [X] Edge cases are identified — 13 edge cases: empty trajectory, missing tool metadata, out-of-scale score, malformed verdict, low-confidence calibration, rubric mid-run deletion, circular coordination, judge unavailable, oversized trajectory, contradictory examples, missing cost data, judge disagreement with all references, backward-compatibility.
- [X] Scope is clearly bounded — explicit Out of Scope: judge fine-tuning, human-in-the-loop overrides, non-numeric verdicts, cross-rubric ensembling, real-time streaming scores, automatic rubric generation, closed-loop retraining, UI tooling, new auth primitives, regression diffs, cost-weighted routing.
- [X] Dependencies and assumptions identified — Dependencies lists evaluation-framework registry, evaluation pipeline, model-routing surface, execution trajectory capture, fixture surface, persistence, auth/authorization/audit, monitoring. Assumptions cover existing trajectory capture, registry extensibility, additive endpoints, judge configuration surface, persistence schema, rubric self-containment, default aggregation, default limits, calibration variance, single-judge model, and template-variance on faithfulness rubric.

## Feature Readiness

- [X] All functional requirements have clear acceptance criteria — each FR maps to user-story scenarios or edge cases (FR-001–FR-005 → US1, US6; FR-006–FR-012, FR-022 → US2; FR-013–FR-015 → US4; FR-016–FR-018 → US5; FR-019–FR-021 → US3; FR-023–FR-028 → cross-cutting + edge cases).
- [X] User scenarios cover primary flows — trajectory scoring against reference (US1), rubric-driven judging (US2), no-regression for existing scorers (US3), calibration (US4), template use (US5), multi-agent cooperation (US6).
- [X] Feature meets measurable outcomes defined in Success Criteria — 16 SCs cover trajectory coverage, comparison-method correctness, dimension completeness, judge verdict coverage, verdict metadata, calibration reporting, judge reproducibility, template availability, template stability, legacy byte-identity, legacy persistence loadability, registry enumeration, ad-hoc judge latency, trajectory truncation, rubric lifecycle, cycle detection.
- [X] No implementation details leak into specification — entities described as logical records (Recorded Trajectory, Expected Trajectory, Rubric, Judge Verdict, Calibration Run, Built-in Rubric Template, Scorer Type Registration) without SQLAlchemy/Pydantic/FastAPI/YAML-library names in the body.

## Notes

- All items pass on the first validation pass — no iteration required.
- Backward compatibility (FR-020 + SC-010) is load-bearing — any non-byte-identical change to pre-existing scorers blocks release.
- Judge verdicts are immutable (FR-010) and audited (FR-023, SC-005) — every verdict is reproducible from its metadata.
- Calibration is an explicit gating step: a rubric can be "calibrated" only if its calibration run agrees with the reference set (FR-015 + SC-007).
- Templates are additive-only (FR-017 + FR-018 + SC-009) — updates cannot silently alter existing evaluations.
- Multi-agent cooperation (US6, FR-005 + FR-028, SC-016) is P3 and does not block single-agent trajectory release.
- The ad-hoc judging endpoint (FR-022) reuses existing auth/rate-limit surfaces — no new security primitives.
- Spec is ready for `/speckit.plan` — no clarifications needed.
