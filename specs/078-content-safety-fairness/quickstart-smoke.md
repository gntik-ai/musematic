# Quickstart Smoke Record: Content Safety and Fairness

**Feature**: 078-content-safety-fairness  
**Date**: 2026-04-26  
**Scope**: local control-plane service/API smoke through deterministic unit and integration tests. External Vault/provider calls were not used; provider behaviour is covered with fake adapters so the smoke remains reproducible.

## Commands

```bash
cd apps/control-plane
../../.venv/bin/python -m pytest --import-mode=importlib tests/unit -q
../../.venv/bin/python -m pytest --import-mode=importlib \
  tests/integration/trust/test_guardrail_with_moderation_e2e.py \
  tests/integration/trust/test_certification_blocked_on_fairness.py \
  tests/integration/evaluation/test_fairness_evaluation_e2e.py \
  tests/integration/test_disclosure_first_interaction.py \
  -m integration --run-integration -q
../../.venv/bin/python -m mypy --strict src/platform/trust src/platform/evaluation
../../.venv/bin/python ../../ci/check_sensitive_logs.py tests src
```

```bash
cd ../..
.venv/bin/python -m ruff check \
  apps/control-plane/src/platform/trust \
  apps/control-plane/src/platform/evaluation \
  apps/control-plane/src/platform/interactions/service.py \
  apps/control-plane/tests/unit/trust \
  apps/control-plane/tests/unit/evaluation \
  apps/control-plane/tests/unit/interactions/test_conversation_consent.py \
  apps/control-plane/tests/integration/trust/test_guardrail_with_moderation_e2e.py \
  apps/control-plane/tests/integration/trust/test_certification_blocked_on_fairness.py \
  apps/control-plane/tests/integration/evaluation/test_fairness_evaluation_e2e.py \
  apps/control-plane/tests/integration/test_disclosure_first_interaction.py \
  ci/check_sensitive_logs.py
```

## Scenario Coverage

| Scenario | Local smoke coverage |
|---|---|
| Q1 block moderation | `test_guardrail_with_moderation_e2e.py`, `test_content_moderator.py`, policy API unit tests |
| Q2 redact PII leakage | `test_content_moderator.py`, `test_moderation_action_resolver.py` |
| Q3 flag with alert | `test_content_moderator.py` verifies triggered alert emission |
| Q4 fail_closed provider failure | `test_content_moderator.py` fail-closed path |
| Q5 provider fallback chain | `test_content_moderator.py` fallback and provider-failed paths |
| Q6 first-time disclosure | `test_disclosure_first_interaction.py`, `test_conversation_consent.py` |
| Q7 material disclosure update | `test_disclosure_first_interaction.py` |
| Q8 fairness evaluation | `test_fairness_evaluation_e2e.py`, `test_fairness_scorer.py` |
| Q9 determinism | `test_fairness_evaluation_e2e.py`, `test_fairness_metrics.py` |
| Q10 missing fairness blocks certification | `test_certification_blocked_on_fairness.py`, `test_certification_service.py` |
| Q11 stale fairness blocks certification | `test_certification_service.py` |
| Q12 material revision invalidates prior eval | `test_certification_blocked_on_fairness.py` |
| Q13 event aggregates | `test_moderation_events_router.py` |
| Q14 cross-workspace authorization | `test_moderation_events_router.py` |
| Q15 moderation before DLP | `test_guardrail_with_moderation_e2e.py` |

## Deviations Captured And Resolved

- Policy create/update uses `X-Workspace-ID`; `workspace_id` is not accepted in the policy JSON body because the request schema forbids extra fields.
- Moderation event list returns `{items, total}`, not a bare JSON array.
- Flag-action alert uses the implemented event type `trust.content_moderation.triggered`.
- Fairness endpoints are mounted at `/api/v1/evaluations/fairness/*` through `platform.api.evaluations`.
- Fairness run payload must include `agent_id` and the deterministic `cases` array; the current local service completes inline and returns `status:"completed"` with HTTP 202.
- Certification create requires `agent_fqn` and `agent_revision_id`; the high-impact gate is activated with `high_impact_use:true`.
- Moderation aggregate `since` is an ISO timestamp and the response is a grouped row list.
