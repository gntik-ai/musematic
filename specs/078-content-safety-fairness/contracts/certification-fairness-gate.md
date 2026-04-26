# Certification Fairness Gate Contract

**Feature**: 078-content-safety-fairness
**Module**: `apps/control-plane/src/platform/trust/certification_service.py` (modified)

## Hook point

In the existing `request_certification(agent_id)` flow:

```python
async def request_certification(self, agent_id: UUID) -> Certification:
    agent = await self.agents_repo.get(agent_id)
    revision = await self.agents_repo.get_active_revision(agent_id)

    # Existing gates (model card, pre-screener, PIA when required) — unchanged.
    await self._existing_gates(agent, revision)

    # NEW gate (this feature)
    if revision.declared.high_impact_use:
        latest = await self._fairness.get_latest_passing_evaluation(
            agent_id=agent_id,
            agent_revision_id=revision.id,
            staleness_days=self.settings.content_moderation.default_fairness_staleness_days,
        )
        if latest is None:
            raise CertificationBlocked(
                reason="fairness_evaluation_required",
                detail=(
                    f"Agent {agent.fqn} declares high_impact_use=true; an "
                    "approved fairness evaluation against the current revision "
                    "is required before certification. Run "
                    "`POST /api/v1/evaluations/fairness/run` against this revision."
                ),
            )
        if latest.computed_at < utcnow() - timedelta(days=self.staleness_days):
            raise CertificationBlocked(
                reason="fairness_evaluation_stale",
                detail=(
                    f"The most recent passing fairness evaluation is older than "
                    f"{self.staleness_days} days. Re-run the fairness suite."
                ),
            )

    # Proceed with existing certification logic
    ...
```

## Service interface

```python
class FairnessGateInterface(Protocol):
    async def get_latest_passing_evaluation(
        self,
        *,
        agent_id: UUID,
        agent_revision_id: UUID,
        staleness_days: int,
    ) -> FairnessEvaluationSummary | None:
        """Returns the latest evaluation_run with overall_passed=True
        for the given (agent_id, agent_revision_id), or None if none exists
        or all are stale."""

@dataclass(slots=True, frozen=True)
class FairnessEvaluationSummary:
    evaluation_run_id: UUID
    agent_revision_id: UUID
    suite_id: UUID
    overall_passed: bool
    computed_at: datetime
```

Implemented in `evaluation/service.py`; called via in-process service interface from `trust/certification_service.py` (Principle IV — no SQL into evaluation/ tables from trust/).

## Material revision invalidation (FR-035)

- "Material revision" is defined by the existing registry definition: a revision change that updates the agent manifest in a way that affects behaviour (re-trained, re-prompted, capability changes). Non-material changes (typo fix in description) do NOT trigger invalidation.
- Because the gate looks up `agent_revision_id` exactly, a new revision automatically requires a fresh fairness evaluation — the prior evaluation is bound to the prior revision_id and won't satisfy the gate.
- No explicit "invalidate" action; the data model handles it naturally.

## Audit-chain emissions (rule 32, 37)

| Outcome | Audit event |
|---|---|
| Gate passed | `trust.certification.fairness_gate.passed` with revision_id, evaluation_run_id, computed_at. |
| Gate blocked: required | `trust.certification.blocked.fairness_required` with revision_id, declared categories. |
| Gate blocked: stale | `trust.certification.blocked.fairness_stale` with revision_id, evaluation_run_id, computed_at, staleness_days. |
| Gate skipped (low-impact) | No audit entry — non-action. |

## Backwards compatibility

- Agents not declared `high_impact_use=true` see no gate — existing certification flow unchanged.
- Existing model-card and PIA gates run unchanged before the fairness gate.
- The existing `CertificationBlocked` exception machinery is reused; just a new `reason` value.
- No schema change to `certifications` table; gate is enforced in service code only.

## Unit-test contract

- **CFG1** — high-impact agent with no fairness evaluation → `CertificationBlocked(reason="fairness_evaluation_required")`.
- **CFG2** — high-impact agent with passing fairness evaluation within staleness window → certification proceeds; existing gates run.
- **CFG3** — high-impact agent with passing fairness evaluation older than staleness window → `CertificationBlocked(reason="fairness_evaluation_stale")`.
- **CFG4** — non-high-impact agent with no fairness evaluation → certification proceeds (gate not triggered).
- **CFG5** — high-impact agent has passing eval against revision A; new revision B created; certification of B → `fairness_evaluation_required` (revision_id mismatch).
- **CFG6** — `latest_passing_evaluation` returns None when there's a `failed` evaluation but no passing one — block with `fairness_evaluation_required`.
- **CFG7** — Audit-chain entries emitted on each path (passed, required, stale).
- **CFG8** — Existing PIA + model-card gates still fire when both their preconditions and the fairness gate apply (no short-circuit between gates).
