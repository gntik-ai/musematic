# Quickstart — UPD-049 Refresh Pass

**Phase 1 output.** Operator and reviewer-lead walkthroughs for the three behaviours added by this refresh: queue assignment, self-review prevention, non-leakage parity verification. The 099 quickstart (creator + first-time reviewer + tenant-flag-toggle walkthroughs) at `specs/099-marketplace-scope/quickstart.md` is unchanged and remains the entry point for end-to-end behaviour.

---

## Prerequisites

Same as 099:

- `make dev-up` running (kind cluster, full Helm stack)
- A superadmin account (the bootstrapped one from feature 086 works)
- At least one default-tenant Pro user with one published-pending agent
- At least one Enterprise tenant ("Acme") with an active `consume_public_marketplace=true` flag

If you don't have these, follow `specs/099-marketplace-scope/quickstart.md` first.

---

## Walkthrough 1 — Reviewer-lead assigns a submission to a specific reviewer

**Goal**: A platform-staff lead distributes the review queue across multiple reviewers without any of them claiming items they shouldn't.

### Steps

1. Sign in as superadmin. Navigate to `/admin/marketplace-review`.
2. Note the new column in the queue table: **Assigned to**. New rows show `—` (unassigned).
3. Click any unassigned row to open the detail page.
4. The detail page now shows an **Assignment** card under the metadata. Click **Assign reviewer**.
5. Select a platform-staff reviewer from the dropdown. The submitter is filtered out (you cannot assign someone to review their own submission). Click **Assign**.
6. The queue now shows the assignee's email in the **Assigned to** column.
7. Optional: click the row again, click **Unassign** to clear.

### Verify

- Database: `SELECT assigned_reviewer_user_id FROM registry_agent_profiles WHERE id = '<agent_id>';` — matches the assignee.
- Audit: `SELECT * FROM security_audit_chain_entries WHERE kind = 'marketplace.review.assigned' ORDER BY id DESC LIMIT 1;` — present, with `assigner_user_id` and `assignee_user_id` set.
- Kafka: `kafka-console-consumer --topic marketplace.events --from-beginning --max-messages 1 | jq 'select(.event_type=="marketplace.review.assigned")'` — present.
- Inbox: the assignee user's notification inbox shows "You have been assigned a marketplace review" with a deep link.

### Filter by assignment

The queue page now has filter chips:

- **Unassigned** — `assigned_reviewer_user_id IS NULL`
- **Assigned to me** — `assigned_reviewer_user_id = current_user`
- **Assigned to others** — `assigned_reviewer_user_id IS NOT NULL AND assigned_reviewer_user_id != current_user`

Click each chip to verify the filter narrows the queue correctly.

---

## Walkthrough 2 — Self-review prevention

**Goal**: Confirm a reviewer cannot act on a submission they authored, at the API and at the UI.

### Setup

You need a user who is BOTH a platform-staff reviewer AND a default-tenant content creator. Create a service account with both roles, or temporarily grant a creator the `platform_admin` role for the test.

### Steps (UI)

1. As that dual-role user, sign in. Submit a public-scope publish from your default-tenant workspace.
2. Navigate to `/admin/marketplace-review`. Find your own submission.
3. Note the **Self-authored** badge on the row.
4. Open the row. Note that **Approve**, **Reject**, and **Claim** buttons are disabled with a "you authored this submission" tooltip.

### Steps (API)

1. From the terminal, with the same dual-role user's JWT:

   ```bash
   curl -X POST -H "Authorization: Bearer $TOKEN" \
     "http://localhost:8000/api/v1/admin/marketplace-review/<your-agent-id>/approve" \
     -H "Content-Type: application/json" \
     -d '{}'
   ```

2. Expected response:

   ```json
   {
     "code": "self_review_not_allowed",
     "message": "Reviewers cannot act on submissions they authored.",
     "details": {
       "submitter_user_id": "...",
       "actor_user_id": "...",
       "action": "approve"
     }
   }
   ```

   Status: 403.

### Verify

- Database: `SELECT review_status FROM registry_agent_profiles WHERE id = '<agent_id>';` — still `pending_review` (refused before any UPDATE).
- Audit: `SELECT * FROM security_audit_chain_entries WHERE kind = 'marketplace.review.self_review_attempted' ORDER BY id DESC LIMIT 1;` — present, with both `submitter_user_id` and `actor_user_id` set in the payload.
- Kafka: no `marketplace.review.approved` event emitted.

Repeat the same flow for **assign**, **claim**, and **reject** — all four MUST return 403 `self_review_not_allowed`.

---

## Walkthrough 3 — Non-leakage parity probe (dev-only)

**Goal**: Verify SC-004 — when a tenant lacks the `consume_public_marketplace` flag, no information about public-hub agents reaches it via search counts, suggestions, or analytics.

### Setup

- Make sure `FEATURE_E2E_MODE=true` in your local Helm values overlay (it's enabled in `make dev-up`'s default values; off in `values.prod.yaml`).
- Create or identify a non-default tenant **without** the consume flag. Any fresh Enterprise tenant works.

### Steps

1. As superadmin, call:

   ```bash
   curl -H "Authorization: Bearer $SUPERADMIN_TOKEN" \
     "http://localhost:8000/api/v1/admin/marketplace-review/parity-probe?query=kyc-verifier&subject_tenant_id=<non-default-tenant-id>"
   ```

2. Inspect the response:

   ```json
   {
     "query": "kyc-verifier",
     "subject_tenant_id": "...",
     "counterfactual": { "total_count": 0, "result_ids": [], ... },
     "live": { "total_count": 0, "result_ids": [], ... },
     "parity_violation": false,
     "parity_violations": []
   }
   ```

3. The `parity_violation` MUST be `false` and the two response payloads MUST match field-for-field. Any `true` is a leak — file an incident.

### Verify production safety

1. In a production-like overlay (`values.prod.yaml`), the same call MUST return 404:

   ```bash
   curl -H "Authorization: Bearer $SUPERADMIN_TOKEN" \
     "https://app.example.com/api/v1/admin/marketplace-review/parity-probe?query=...&subject_tenant_id=..."
   ```

   Expected: HTTP 404 with no body. The endpoint is invisible in production.

### CI integration

The parity probe is exercised by `tests/e2e/suites/marketplace/test_non_leakage_parity.py` on every CI run. A leak (parity_violation true) fails the build.

---

## Walkthrough 4 — Fork update notification end-to-end

**Goal**: Confirm that when a creator publishes a new version of an already-published public agent, fork owners get notified via the UPD-044 template-update channel — but no fork is auto-updated.

### Setup

Same as 099 walkthrough 5 (forked-agent tenants). Make sure `MarketplaceFanoutConsumer` is registered in the worker entrypoint (this refresh adds the registration).

### Steps

1. As an Acme user with consume flag enabled, fork an existing public agent. Note the resulting fork's `id`.
2. As the original public agent's creator, edit the agent and publish a new version. Wait for the new version to enter `pending_review`.
3. As superadmin, navigate to `/admin/marketplace-review`, claim, and approve the new version.
4. The worker's `MarketplaceFanoutConsumer` consumes `marketplace.source_updated` and fans out to fork owners.

### Verify

- The Acme user's notification inbox now shows a "Source agent updated" alert with a deep link to the source detail page.
- The alert body includes the sentence: "This fork has NOT been auto-updated."
- Database: the fork's columns are unchanged (the source's `forked_from_agent_id` references unchanged on the fork's row).
- Kafka: `marketplace.source_updated` produced once; the consumer's lag is zero.

### If the consumer is not registered

If Step 4 produces no notification, check the worker entrypoint:

```bash
grep -n MarketplaceFanout apps/control-plane/entrypoints/worker_main.py
```

There should be a `register(...)` call. If absent, this refresh's wiring is incomplete; file a bug or run the refresh's task `T-CONSUMER-REGISTRATION`.

---

## Troubleshooting

### "I see the assignment column but it's empty for everything"

That's expected — assignment is opt-in. Reviewers can still claim unassigned items today. Use the **Assigned to me** filter chip to verify.

### "The probe returns parity_violation=true on a clean dev environment"

This is a real leak. Inspect `parity_violations[0].field` to see which surface leaked (`total_count`, `result_ids`, `suggestions`, `analytics_event_payload`). Most likely cause: a code path emits the field BEFORE applying the visibility filter. Fix the order; re-run the probe.

### "I tried to approve my own submission and it succeeded"

The self-review guard is missing. Check:

1. `apps/control-plane/src/platform/marketplace/review_service.py` — is `_ensure_not_self_review` called as the first I/O step in `approve`?
2. `apps/control-plane/src/platform/marketplace/dependencies.py` — is the API-layer dependency wired into the route?

### "The probe returns 404 in dev mode"

Check `FEATURE_E2E_MODE`:

```bash
kubectl get configmap platform-config -n platform-control -o yaml | grep FEATURE_E2E_MODE
```

If `false`, set `featureE2eMode: true` in `values.dev.yaml` and re-deploy.
