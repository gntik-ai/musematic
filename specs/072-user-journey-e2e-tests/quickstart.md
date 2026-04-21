# Quickstart & Acceptance Scenarios: User Journey E2E Tests

**Feature**: 072-user-journey-e2e-tests
**Date**: 2026-04-21

Nine walkthroughs (Q1–Q9), one per journey, with exact commands and expected narrative-report excerpts. These become the basis of the CI green path and the journey reviewer's reading guide.

## Prerequisites

Feature 071's E2E cluster must be running:

```bash
cd tests/e2e
make e2e-up                     # provisions kind, installs platform, seeds baseline (from feature 071)
```

Verify the new mock OAuth servers are healthy:

```bash
kubectl -n platform get pods -l app.kubernetes.io/component=mock-oauth
# NAME                                   READY   STATUS    RESTARTS
# mock-google-oidc-abc123-xyz            1/1     Running   0
# mock-github-oauth-def456-uvw           1/1     Running   0
```

---

## Q1 — Admin bootstrap journey (J01, P1 MVP)

```bash
cd tests/e2e
make e2e-j01
```

**Expected narrative output** (abridged, from `journeys-report.html`):

```
Journey J01 — Platform Administrator: Bootstrap to Production-Ready
  ✓  1. Admin logs in with temporary password               (0.21s)
  ✓  2. Admin changes temporary password to strong password (0.18s)
  ✓  3. Admin enrolls TOTP MFA                              (0.34s)
  ✓  4. Admin verifies MFA second factor on re-login         (0.40s)
  ✓  5. Admin configures Google OAuth provider              (0.27s)
  ✓  6. Admin configures GitHub OAuth provider              (0.29s)
  ✓  7. Admin verifies both providers listed on login page  (0.16s)
  ✓  8. Admin creates first production workspace            (0.31s)
  ✓  9. Admin creates namespaces platform-core + finance-ops (0.44s)
  ✓ 10. Admin invites users with workspace roles            (0.22s)
  ✓ 11. Admin configures workspace-level visibility grants  (0.19s)
  ✓ 12. Admin sets workspace quotas                          (0.20s)
  ✓ 13. Admin configures governance chain obs→judge→enf     (0.52s)
  ✓ 14. Admin configures default alert preferences          (0.17s)
  ✓ 15. Invited user joins workspace and inherits role      (0.38s)

Journey J01 passed in 4.4s (15 steps, 6 bounded contexts)
```

---

## Q2 — Creator to publication journey (J02, P1)

```bash
make e2e-j02
```

**Expected narrative output**:

```
Journey J02 — Agent Creator: From Idea to Published Agent
  ✓  1. Creator signs in via GitHub OAuth (mock)            (0.53s)
  ✓  2. Creator accesses creator workbench with RBAC        (0.12s)
  ✓  3. Creator selects namespace finance-ops               (0.09s)
  ✓  4. Creator registers kyc-verifier with full manifest   (0.44s)
  ✓  5. FQN resolution returns the agent                    (0.08s)
  ✓  6. Agent discoverable via finance-ops:* pattern        (0.10s)
  ✓  7. Zero-trust: agent invisible outside visibility scope (0.09s)
  ✓  8. Creator uploads agent package .tar.gz               (0.62s)
  ✓  9. Immutable revision with content digest created      (0.11s)
  ✓ 10. Policy attached to agent                             (0.13s)
  ✓ 11. Certification requested                              (0.15s)
  ✓ 12. Certification workflow runs (evidence, checks)       (1.20s)
  ✓ 13. Trust reviewer approves certification                (0.19s)
  ✓ 14. Agent appears in marketplace with trust signals      (0.22s)
  ✓ 15. Marketplace search by intent finds the agent         (0.14s)
  ✓ 16. Marketplace search by FQN pattern finds the agent    (0.11s)
  ✓ 17. Purpose + approach fields are searchable             (0.12s)
  ✓ 18. Quick evaluation runs against the agent              (2.30s)
  ✓ 19. Evaluation results stored on agent profile           (0.10s)
  ✓ 20. Final state: certified, published, discoverable      (0.15s)

Journey J02 passed in 7.0s (20 steps, 7 bounded contexts)
```

---

## Q3 — Consumer discovery and execution journey (J03, P1)

```bash
make e2e-j03
```

**Expected narrative output**:

```
Journey J03 — Consumer: Discover, Execute, and Track
  ✓  1. Consumer signs in via Google OAuth (mock, first time) (0.48s)
  ✓  2. User auto-provisioned with default role               (0.09s)
  ✓  3. Consumer browses marketplace home                     (0.13s)
  ✓  4. Consumer searches by intent "verify customer identity"(0.15s)
  ✓  5. Search returns agents ranked by relevance + trust     (0.08s)
  ✓  6. Consumer inspects agent profile (FQN, purpose, trust) (0.12s)
  ✓  7. Consumer starts a new conversation                    (0.18s)
  ✓  8. Conversation ID returned                              (0.01s)
  ✓  9. Consumer sends task message                           (0.20s)
  ✓ 10. Consumer subscribes to WebSocket for conversation    (0.08s)
  ✓ 11. Execution created event received                      (0.30s)
  ✓ 12. Workflow execution events arrive in order            (1.20s)
  ✓ 13. Reasoning trace milestone events arrive              (0.80s)
  ✓ 14. Execution completion event received                   (0.40s)
  ✓ 15. Consumer receives structured result                   (0.10s)
  ✓ 16. Reasoning trace shows task plan, tool selections      (0.15s)
  ✓ 17. Execution timeline shows all steps with durations     (0.12s)
  ✓ 18. Consumer injects follow-up message mid-conversation   (0.20s)
  ✓ 19. Follow-up creates new interaction in same conv        (0.25s)
  ✓ 20. Consumer configures personal alert preferences        (0.10s)
  ✓ 21. Second task completes; alert fires on completion     (1.80s)
  ✓ 22. Conversation history lists both interactions          (0.08s)
  ✓ 23. Final state: 2 interactions, traces persisted         (0.12s)

Journey J03 passed in 7.2s (23 steps, 8 bounded contexts)
```

---

## Q4 — Workspace goal collaboration journey (J04, P2)

```bash
make e2e-j04
```

**Expected narrative output**:

```
Journey J04 — Workspace Collaborator: Multi-Agent Problem Solving
  ✓  1. Collaborator logs in                                  (0.20s)
  ✓  2. Collaborator opens workspace with 4 subscribed agents (0.10s)
  ✓  3. Collaborator creates a goal with objective           (0.15s)
  ✓  4. Goal in READY state, GID assigned                     (0.02s)
  ✓  5. Collaborator posts first goal message                (0.18s)
  ✓  6. Goal transitions to WORKING                           (0.10s)
  ✓  7. Response decision log records per-agent decisions     (0.12s)
  ✓  8. market-data-agent responds (relevant)                (0.30s)
  ✓  9. risk-analysis-agent responds (relevant)              (0.28s)
  ✓ 10. notification-agent does NOT respond (irrelevant)     (0.10s)
  ✓ 11. All messages carry same GID                           (0.05s)
  ✓ 12. participant_id is agent FQN on each message           (0.04s)
  ✓ 13. Collaborator posts follow-up "focus on green energy"  (0.18s)
  ✓ 14. Agents incorporate follow-up in next responses        (0.60s)
  ✓ 15. Agent raises attention request                        (0.25s)
  ✓ 16. Attention arrives via WebSocket with urgency         (0.08s)
  ✓ 17. Collaborator responds to attention request            (0.15s)
  ✓ 18. Collaborator marks goal COMPLETE                      (0.12s)
  ✓ 19. New message POST to completed goal returns 409        (0.08s)
  ✓ 20. GID verified in ClickHouse downstream record          (0.11s)
  ✓ 21. Final state: goal completed, GID everywhere          (0.09s)

Journey J04 passed in 3.5s (21 steps, 5 bounded contexts)
```

---

## Q5 — Trust governance pipeline journey (J05, P2)

```bash
make e2e-j05
```

**Expected narrative output** (abridged to first 12 + last 3 steps):

```
Journey J05 — Trust Officer: Policy to Enforcement
  ✓  1. Trust reviewer logs in                                (0.20s)
  ✓  2. Reviewer creates safety policy "no PII disclosure"   (0.18s)
  ✓  3. Policy attached to workspace                          (0.14s)
  ✓  4. Reviewer configures governance chain                  (0.30s)
  ✓  5. Observer agent registered                             (0.25s)
  ✓  6. Judge agent registered                                (0.22s)
  ✓  7. Enforcer agent registered                             (0.24s)
  ✓  8. Execution triggered with obvious PII violation        (0.15s)
  ✓  9. SafetyPreScreener blocks in < 10 ms                   (0.01s)
  ✓ 10. Subtle violation triggered, bypasses pre-screener     (0.18s)
  ✓ 11. Observer detects signal                               (0.22s)
  ✓ 12. Judge issues VIOLATION verdict with rationale         (0.35s)
  ...
  ✓ 20. Non-compliant agent decommissioned                    (0.28s)
  ✓ 21. Agent absent from marketplace but history preserved   (0.12s)
  ✓ 22. Final state: pipeline active, all verdicts logged    (0.15s)

Journey J05 passed in 5.8s (22 steps, 6 bounded contexts)
```

---

## Q6 — Operator incident response journey (J06, P2)

```bash
make e2e-j06
```

**Key narrative excerpt** (chaos + recovery steps):

```
  ✓  7. Long execution created, checkpoints observed          (1.20s)
  ✓  8. Operator forces runtime pod kill                      (0.30s)
  ✓  9. Platform detects failure via heartbeat                (2.50s)
  ✓ 10. Operator initiates rollback to last checkpoint        (0.28s)
  ✓ 11. Execution resumes from checkpoint state               (1.80s)
  ✓ 12. Final state matches uninterrupted reference run       (0.20s)
  ✓ 13. Rollback recorded in audit trail                      (0.10s)
```

Journey timeout is 600 s (D-008) because checkpoint recovery + re-prioritization + canary take real time.

---

## Q7 — Evaluator improvement loop journey (J07, P3)

```bash
make e2e-j07
```

**Key narrative excerpt**:

```
  ✓  5. Evaluation suite runs against 10 test cases           (3.20s)
  ✓  6. TrajectoryScorer produces 4-dimension scores per case (0.10s)
  ✓  7. LLM-as-Judge produces per-criterion scores w/rationale (1.40s)
  ✓  8. Calibration: 3 cases × 5 re-judgings                  (4.80s)
  ✓  9. Calibration produces score distributions              (0.08s)
  ...
  ✓ 16. New revision created with improved configuration      (0.22s)
  ✓ 17. Re-evaluation shows measurable improvement            (3.10s)
  ✓ 18. Final state: improvement documented                   (0.05s)
```

Journey timeout is 600 s because 10-case evaluation + calibration dominate wall clock.

---

## Q8 — External A2A + MCP integration journey (J08, P3)

```bash
make e2e-j08
```

**Key narrative excerpt**:

```
  ✓  1. External client fetches /.well-known/agent.json       (0.05s)
  ✓  2. Agent Card contains capabilities + auth schemes       (0.02s)
  ✓  3. Client fetches per-agent card by FQN                  (0.04s)
  ✓  4. Per-agent card auto-generated with purpose, skills    (0.02s)
  ✓  5. Client authenticates via OAuth2 bearer                (0.20s)
  ✓  6. Client submits A2A task                               (0.18s)
  ✓  7. Task state: submitted                                 (0.01s)
  ✓  8. Client subscribes to SSE for task progress            (0.05s)
  ✓  9. SSE event: working                                    (0.30s)
  ✓ 10. SSE event: completed                                  (1.20s)
  ...
  ✓ 16. MCP tool invocation routes through tool gateway       (0.18s)
  ✓ 17. Tool output sanitized (no secrets leaked)             (0.04s)
  ✓ 18. Policy enforcement verified on MCP call               (0.10s)
  ✓ 19. Final state: A2A + MCP fully exercised                (0.05s)
```

---

## Q9 — Scientific discovery journey (J09, P3)

```bash
make e2e-j09
```

**Key narrative excerpt**:

```
  ✓  3. Hypothesis generation triggered                       (2.40s)
  ✓  4. Generation agents produce N initial hypotheses         (0.15s)
  ✓  5. Hypotheses viewable in workspace                       (0.08s)
  ✓  6. Chain of Debates on top hypotheses triggered          (3.10s)
  ✓  7. Debate rounds: position → critique → rebuttal → synth (3.80s)
  ✓  8. Debate transcripts persisted                           (0.12s)
  ✓  9. Tournament ranking runs                                (1.50s)
  ✓ 10. Hypotheses have Elo scores                             (0.05s)
  ✓ 11. Proximity graph shows clustering                       (0.10s)
  ✓ 12. Generation biases toward underrepresented clusters     (0.90s)
  ...
  ✓ 17. Final state: experiment designed                       (0.10s)
```

---

## Full journey suite run

```bash
make e2e-journeys
# Runs pytest journeys/ -n 3 --dist=loadfile (3 parallel workers)
```

**Expected aggregate output**:

```
============ pytest-xdist 3 workers ============
gw0 ✓ test_j01_admin_bootstrap.py ................ (4.4s)
gw1 ✓ test_j02_creator_to_publication.py ......... (7.0s)
gw2 ✓ test_j03_consumer_discovery_execution.py ... (7.2s)
gw0 ✓ test_j04_workspace_goal_collaboration.py ... (3.5s)
gw1 ✓ test_j05_trust_governance_pipeline.py ...... (5.8s)
gw2 ✓ test_j06_operator_incident_response.py ..... (9m12s)
gw0 ✓ test_j07_evaluator_improvement_loop.py ..... (8m45s)
gw1 ✓ test_j08_external_a2a_mcp.py ............... (4.2s)
gw2 ✓ test_j09_scientific_discovery.py ........... (6.8s)
gw0 ✓ test_journey_structure.py .................. (0.3s)

========== 10 passed in 12m 38s ==========

Reports:
  tests/e2e/reports/journeys-junit.xml
  tests/e2e/reports/journeys-report.html
```

**Narrative HTML report**: opening `journeys-report.html` in a browser shows all 9 journeys as collapsible accordion rows, each expanding to show the ordered narrative steps with pass/fail icons and timings. A reviewer unfamiliar with the codebase can read the entire platform's end-to-end story in under 10 minutes (SC-010 validation).

---

## Parallel-cluster verification (SC-005)

```bash
# Terminal 1
pytest tests/e2e/journeys/test_j01_admin_bootstrap.py -v

# Terminal 2 (concurrent)
pytest tests/e2e/journeys/test_j02_creator_to_publication.py -v

# Both pass; neither interferes with the other.
# Verify resource isolation:
kubectl -n platform exec -it deploy/amp-control-plane -- psql $DB \
  -c "SELECT name FROM workspaces WHERE name LIKE 'j%-test-%' ORDER BY name;"
# j01-test-a3f1b9c2-ws-primary
# j02-test-d4e2c8a1-ws-primary
```

---

## Cross-cutting verification checklist

After all nine walkthroughs pass:

- [ ] `make e2e-journeys` completes ≤ 30 min on reference runner (SC-004)
- [ ] Every journey file has ≥ 15 assertion points (SC-002, verified by test_journey_structure)
- [ ] Every journey file has ≥ 4 bounded contexts in its inventory comment (SC-003)
- [ ] OAuth flows for admin (Google+GitHub), creator (GitHub), consumer (Google) all succeed (SC-007)
- [ ] GID propagation verified in J04 across goal → messages → execution → ClickHouse (SC-008)
- [ ] Checkpoint recovery verified in J06 (SC-009)
- [ ] `journeys-report.html` narrative is human-readable (SC-010 manual review)
- [ ] Two concurrent journeys pass with isolated resources (SC-005)
- [ ] Journey rerun after prior failure succeeds without manual cleanup (SC-006 — `make e2e-reset && make e2e-j{NN}`)
- [ ] No production `/api/v1/_e2e/*` endpoint regressions (feature 071's SC-007 still passes)
