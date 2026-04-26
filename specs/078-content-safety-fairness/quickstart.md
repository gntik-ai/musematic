# Quickstart: Content Safety and Fairness

**Feature**: 078-content-safety-fairness

This document is a hands-on walkthrough of every primary path. Each Q-block is a complete scenario producing a single observable outcome.

## Prerequisites

- Control plane running with `FEATURE_CONTENT_MODERATION=true`.
- Privacy compliance subsystem (feature 076) enabled with consent service available.
- Audit chain (UPD-024) enabled.
- Vault accessible; provider credentials seeded under `secret/data/trust/moderation-providers/...`.
- Migration `061_content_safety_fairness.py` applied.

---

## Q1 — Workspace admin enables content moderation with `block` on toxicity (US1)

```bash
# 1. Create a moderation policy.
curl -X POST $API/api/v1/trust/moderation/policies \
  -H "Authorization: Bearer $WS_ADMIN_TOKEN" \
  -H "X-Workspace-ID: $WS_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "categories": ["toxicity","hate_speech","violence_self_harm","sexually_explicit","pii_leakage"],
    "thresholds": {"toxicity":0.8,"hate_speech":0.7,"violence_self_harm":0.7,"sexually_explicit":0.8,"pii_leakage":0.5},
    "default_action": "block",
    "primary_provider": "openai",
    "fallback_provider": "self_hosted",
    "provider_failure_action": "fail_closed",
    "monthly_cost_cap_eur": 10.00
  }'
# 201 {id, version: 1, active: true, ...}

# 2. Trigger an agent execution that produces toxic output.
# Force via test fixture or evaluation harness.

# 3. Inspect the moderation event log.
curl $API/api/v1/trust/moderation/events?workspace_id=$WS_ID \
  -H "Authorization: Bearer $WS_ADMIN_TOKEN" \
  -H "X-Workspace-ID: $WS_ID"
# 200 {items:[{
#   id, execution_id, agent_id, policy_id, provider:"openai",
#   triggered_categories:["toxicity"], scores:{toxicity:0.92,...},
#   action_taken:"block", latency_ms: 245, audit_chain_ref:"...",
#   created_at:"..."
# }], total:1}

# 4. Verify the user received a safe replacement, not the toxic content.
# (Inspect the conversation interaction / WebSocket trace.)
```

**Verify**: One `content_moderation_events` row; `action_taken='block'`; original content NOT delivered to any consumer; safe replacement message delivered instead; audit-chain entry references the original content.

---

## Q2 — `redact` action on PII leakage (US1)

```bash
# 1. Create a policy with redact for pii_leakage.
curl -X PATCH $API/api/v1/trust/moderation/policies/$POLICY_ID \
  -H "Authorization: Bearer $WS_ADMIN_TOKEN" \
  -H "X-Workspace-ID: $WS_ID" \
  -H "Content-Type: application/json" \
  -d '{"action_map":{"pii_leakage":"redact"}, "default_action":"block"}'

# 2. Trigger an agent output containing email/phone/credit-card.
# 3. Inspect the delivered output — sensitive fragments replaced.
# 4. Confirm event row records the pre-redaction scores.
```

**Verify**: User receives output with `[REDACTED:pii_leakage]` placeholders in place of sensitive fragments; event row carries scores and `action_taken='redact'`.

---

## Q3 — `flag` action with operator alert (US1)

```bash
# 1. Set violence_self_harm to flag.
curl -X PATCH $API/api/v1/trust/moderation/policies/$POLICY_ID \
  -H "Authorization: Bearer $WS_ADMIN_TOKEN" \
  -H "X-Workspace-ID: $WS_ID" \
  -H "Content-Type: application/json" \
  -d '{"action_map":{"violence_self_harm":"flag"}}'

# 2. Trigger output that scores 0.7 for violence.
# 3. User receives the output unchanged.
# 4. Operator notification (email / Slack / etc, via feature 077) fires.
# 5. Inspect event row.
```

**Verify**: Output delivered; event row `action_taken='flag'`; `monitor.alerts` event `trust.content_moderation.triggered` published; notifications subsystem fans out to configured operator channels.

---

## Q4 — Provider failure mode `fail_closed` (US1, Edge case)

```bash
# 1. Configure policy with primary=openai, no fallback,
#    self_hosted off, provider_failure_action=fail_closed.
# 2. Disconnect the openai_moderation API (firewall rule or env override).
# 3. Trigger any agent output.
# 4. Verify: output NOT delivered; replacement message delivered instead;
#    event row: action_taken='fail_closed_blocked';
#    operator alerted within 60s.
```

**Verify**: Failure path blocks output as expected; operator receives alert; event captured.

---

## Q5 — Provider fallback chain (US1, Edge case)

```bash
# 1. Configure primary=openai, fallback=google_perspective,
#    plus self_hosted as the floor.
# 2. Disconnect openai; verify google_perspective takes over.
# 3. Disconnect google_perspective too; verify self_hosted takes over.
# 4. Restore providers; verify primary takes over again.
```

**Verify**: At each step, event rows show the actual provider used; provider_failed events emitted only for the failed providers.

---

## Q6 — First-time AI disclosure on user interaction (US2)

```bash
# 1. Sign in as a user who has NEVER interacted with an agent
#    (no privacy_consent_records row for ai_interaction).
# 2. Attempt to start a conversation with any agent.
curl -X POST $API/api/v1/interactions/conversations \
  -H "Authorization: Bearer $NEW_USER_TOKEN" \
  -H "X-Workspace-ID: $WS_ID" \
  -H "Content-Type: application/json" \
  -d '{"title":"First agent conversation","metadata":{"agent_id":"'$AGENT_ID'"}}'
# 428 {error:"consent_required", missing_consents:["ai_interaction"], disclosure_text_ref:"/api/v1/me/consents/disclosure"}

# 3. Fetch the disclosure text.
curl $API/api/v1/me/consents/disclosure \
  -H "Authorization: Bearer $NEW_USER_TOKEN"

# 4. Acknowledge.
curl -X PUT $API/api/v1/me/consents \
  -H "Authorization: Bearer $NEW_USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"choices":{"ai_interaction":true,"data_collection":true,"training_use":false},"workspace_id":"'$WS_ID'"}'

# 5. Re-attempt the conversation; now succeeds.
# 6. Inspect privacy_consent_records — row exists with disclosure version recorded.
```

**Verify**: HTTP 428 returned by `interactions.create_conversation` (per feature 076 contract); disclosure-text returned; after acknowledgement, conversation creation succeeds; consent record persists across sessions; subsequent interactions do not re-prompt.

---

## Q7 — Disclosure text material change re-prompts users (US2)

```bash
# 1. As workspace admin, update the disclosure text and mark material.
curl -X POST $API/api/v1/trust/disclosure/version \
  -H "Authorization: Bearer $WS_ADMIN_TOKEN" \
  -H "X-Workspace-ID: $WS_ID" \
  -H "Content-Type: application/json" \
  -d '{"text":"NEW: We now process your conversation for ML training.","material":true}'

# 2. As a user with prior acknowledgement, attempt to interact.
# 3. Verify HTTP 428 with `missing_consents:["ai_interaction"]`.
# 4. Acknowledge again; the new version is referenced on the new
#    consent record.
```

---

## Q8 — Run a fairness evaluation (US3)

```bash
# 1. Build a test suite with group attributes.
# Suite contains 100 cases; each case carries
# {"group_attributes":{"language":"en|es","gender":"f|m|nb"}}.

# 2. Generate the deterministic smoke payload.
python - <<'PY' > fairness-payload.json
import json
import os

workspace_id = os.environ["WS_ID"]
agent_id = os.environ["AGENT_ID"]
revision_id = os.environ["REVISION_ID"]
suite_id = os.environ["SUITE_ID"]
languages = ["en", "es"]
genders = ["f", "m", "nb"]
cases = []

for index in range(100):
    positive = index % 3 != 0
    cases.append(
        {
            "id": f"case-{index:03d}",
            "label": "positive" if positive else "negative",
            "prediction": "positive" if index % 4 != 0 else "negative",
            "score": 0.90 if positive else 0.35,
            "group_attributes": {
                "language": languages[index % len(languages)],
                "gender": genders[index % len(genders)],
            },
        }
    )

print(
    json.dumps(
        {
            "workspace_id": workspace_id,
            "agent_id": agent_id,
            "agent_revision_id": revision_id,
            "suite_id": suite_id,
            "cases": cases,
            "config": {
                "metrics": ["demographic_parity", "equal_opportunity", "calibration"],
                "group_attributes": ["language", "gender"],
                "fairness_band": 0.10,
                "min_group_size": 5,
            },
        }
    )
)
PY

# 3. Run fairness scorer.
curl -X POST $API/api/v1/evaluations/fairness/run \
  -H "Authorization: Bearer $EVALUATOR_TOKEN" \
  -H "X-Workspace-ID: $WS_ID" \
  -H "Content-Type: application/json" \
  --data @fairness-payload.json
# 202 {evaluation_run_id, status:"completed", rows:[...], overall_passed:false}

# Preview mode is for dry-runs before a real evaluation. Set
# "preview": true to route any receiver-side LLM preview dependency to
# the platform mock-LLM outputs instead of live model calls. This keeps
# cost at zero but means the run validates metric plumbing and group
# coverage, not live-model quality.

# 4. Poll for completion.
curl $API/api/v1/evaluations/fairness/runs/$RUN_ID \
  -H "Authorization: Bearer $EVALUATOR_TOKEN"
# 200 {
#   status:"completed",
#   rows: [
#     {metric_name:"demographic_parity", group_attribute:"language",
#      per_group_scores:{"en":0.82,"es":0.79}, spread:0.03, passed:true,
#      fairness_band:0.10, coverage:{included:{en:60,es:40}, ...}},
#     {metric_name:"demographic_parity", group_attribute:"gender",
#      per_group_scores:{"f":0.75,"m":0.84,"nb":0.62}, spread:0.22, passed:false,
#      fairness_band:0.10, coverage:{included:{f:42,m:40,nb:18}, ...}},
#     ...
#   ],
#   overall_passed: false,
#   notes: ["calibration unsupported on classification-only output"]
# }
```

**Verify**: Per-attribute, per-metric rows persisted to `fairness_evaluations`; `overall_passed` reflects worst-case per-metric pass; coverage statistics reported; group-attribute values NOT present in any structured-log field (assert via log capture).

---

## Q9 — Determinism check (US3, SC-009)

```bash
# 1. Re-run the same suite + revision with the same config.
# 2. Compare the per_group_scores from runs 1 and 2.
# 3. Assert each value is within 0.001 of the prior run.
```

---

## Q10 — Certification blocked on missing fairness evaluation (US4)

```bash
# 1. Take an agent with high_impact_use=true and no fairness evaluation.
# 2. Trust reviewer requests certification.
curl -X POST $API/api/v1/trust/certifications \
  -H "Authorization: Bearer $TRUST_CERTIFIER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id":"'$AGENT_ID'",
    "agent_fqn":"'$AGENT_FQN'",
    "agent_revision_id":"'$REVISION_ID'",
    "high_impact_use":true
  }'
# 409 {error:"certification_blocked", reason:"fairness_evaluation_required",
#       detail:"Agent ... declares high_impact_use=true; an approved fairness
#               evaluation against the current revision is required before
#               certification. Run POST /api/v1/evaluations/fairness/run."}

# 3. Run a fairness evaluation that passes.
# 4. Resubmit certification.
# 5. Certification proceeds.
```

---

## Q11 — Stale fairness evaluation blocks certification (US4)

```bash
# 1. Start with a passing fairness evaluation more than 90 days old.
# 2. Submit certification.
# 3. Verify reason='fairness_evaluation_stale'.
# 4. Re-run fairness evaluation; resubmit; certification succeeds.
```

---

## Q12 — Material revision invalidates prior evaluation (US4)

```bash
# 1. Agent revision A has a passing fairness evaluation.
# 2. Create revision B (re-trained agent).
# 3. Submit certification of revision B.
# 4. Verify reason='fairness_evaluation_required' even though A had a pass.
# 5. Run fairness evaluation against B; resubmit; certification succeeds.
```

---

## Q13 — Operator views moderation event aggregates (US5)

```bash
# 1. Generate ~100 moderation events across categories and actions over 24h.
# 2. Open the aggregate dashboard.
SINCE="$(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%SZ)"
curl "$API/api/v1/trust/moderation/events/aggregate?workspace_id=$WS_ID&since=$SINCE&group_by=category,day" \
  -H "Authorization: Bearer $WS_ADMIN_TOKEN" \
  -H "X-Workspace-ID: $WS_ID"
# 200 [
#   {"category":"toxicity","day":"2026-04-26","count":42},
#   {"category":"pii_leakage","day":"2026-04-26","count":18}
# ]

# 3. Drill down by filter.
curl "$API/api/v1/trust/moderation/events?workspace_id=$WS_ID&category=toxicity&action=block" \
  -H "Authorization: Bearer $WS_ADMIN_TOKEN" \
  -H "X-Workspace-ID: $WS_ID"
```

---

## Q14 — Cross-workspace authorization (US5, FR-040, SC-011)

```bash
# 1. As workspace_admin of WS1, attempt to read events from WS2.
curl $API/api/v1/trust/moderation/events?workspace_id=$WS2_ID \
  -H "Authorization: Bearer $WS1_ADMIN_TOKEN" \
  -H "X-Workspace-ID: $WS1_ID"
# 403 {error:"forbidden"} — no leakage that WS2 exists.
```

---

## Q15 — DLP runs after moderation (Edge case, Rule 34)

```bash
# 1. Configure moderation with redact on pii_leakage.
# 2. Configure DLP to also redact email patterns (feature 076).
# 3. Trigger output containing a PII pattern that BOTH catch.
# 4. Inspect: moderation runs first → first redaction; DLP runs second
#    → unchanged (already redacted) or further redacted.
```

**Verify**: Layer order preserved (`output_moderation` → `dlp_scan`); both stages run; final delivered content is fully redacted.

---

## Smoke checklist

After deployment, run all 15 Q-scripts in a fresh workspace and verify:

- [ ] All `content_moderation_events` rows referenced by `audit_chain_ref` resolve to a chain entry containing the original content.
- [ ] `block` outputs never reach the user (verify via WebSocket capture + DB).
- [ ] First-time disclosure 428 fires for users with no prior consent record.
- [ ] Subsequent interactions do not re-prompt (no 428 after acknowledgement).
- [ ] Material disclosure update re-prompts existing users.
- [ ] Fairness scorer determinism within 0.001 across 5 re-runs.
- [ ] Certification blocked with the correct reason for high-impact agents without passing eval.
- [ ] Cross-workspace operator access denied with 403 (no info leakage).
- [ ] Audit chain entries exist for every policy CRUD, every moderation trigger, every fairness run, every certification gate firing.
- [ ] Group-attribute values absent from structured-log capture.
- [ ] Provider API keys never present in any logged output.
- [ ] DLQ depth (feature 077) does not grow due to flag-action notifications (i.e. operator alerts deliver successfully).
