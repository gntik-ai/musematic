# Quickstart — UPD-051 Data Lifecycle

**Phase 1 output.** Operator and end-user walkthroughs for all five user stories. Maps each spec scenario to a runnable demo on `make dev-up` (kind cluster).

---

## Prerequisites

- `make dev-up` running with the new sub-charts enabled (`clamav`, `public-pages`).
- A super-admin account (the bootstrapped one from feature 086 works).
- A test tenant `acme` with at least one workspace and a Pro plan.
- Mailhog at `localhost:8025` for email capture.
- `mc` (MinIO client) configured against the dev cluster's `data-lifecycle-exports` bucket.

---

## Walkthrough 1 — Workspace owner export (US1)

**Goal**: confirm a workspace owner can request, monitor, and download a workspace export ZIP.

### Steps

1. Sign in as the workspace owner. Navigate to `/workspaces/{id}/data-export`. Click **Request export**.
2. Confirm the page shows a `pending` job card with an estimated completion time.
3. Wait for the worker to pick up (≤ 30 seconds in dev). The card should flip to `processing`, then `completed`.
4. Click **Download** on the completed job. A signed URL fetches the ZIP from MinIO.

### Verify

- PostgreSQL: `SELECT id, status, output_size_bytes FROM data_export_jobs WHERE scope_id = '<workspace_id>' ORDER BY created_at DESC LIMIT 1;` — status `completed`, size > 0.
- MinIO: `mc ls dev/data-lifecycle-exports/workspace/<workspace_id>/<job_id>.zip` lists the object.
- Audit chain: `SELECT * FROM audit_chain_entries WHERE event_type LIKE 'data_lifecycle.export%' ORDER BY id DESC LIMIT 5;` shows `export_requested`, `export_completed`, `export_url_issued`.
- Mailhog: notification email "Your workspace export is ready" sent to the owner.
- ZIP contents: `unzip -l workspace.zip` shows `metadata.json`, `agents/`, `executions/`, `audit/`, `costs/`, `members/`, `README.md`.

### Cross-workspace privacy check

Confirm `members/members.json` contains only the workspace's members and DOES NOT include external users' email addresses. This validates US1 acceptance #4 (workspace member data follows GDPR; no email leak).

---

## Walkthrough 2 — Workspace deletion two-phase (US2)

**Goal**: confirm two-phase deletion with grace, cancel-link semantics, anti-enumeration, and cascade.

### Steps (phase 1)

1. As workspace owner, navigate to `/workspaces/{id}/settings/delete`.
2. Read the confirmation copy. Type the workspace slug exactly into the typed-confirmation field. Click **Delete workspace**.
3. The page shows a banner "Workspace pending deletion. Cancel link sent to owner@example.com. Grace ends 2026-05-10."
4. Workspace status flips to `pending_deletion`. Attempting to write any resource in the workspace returns 423.

### Verify the cancel-link flow

1. Open Mailhog. Find the cancel email. Copy the cancel link.
2. Click the link in a fresh browser session. Observe the message "If the link was valid, deletion has been cancelled — check your email for confirmation."
3. The workspace returns to `active`.
4. Audit chain shows `data_lifecycle.workspace_deletion_aborted`.

### Verify anti-enumeration (R10)

1. Submit `POST /api/v1/workspaces/cancel-deletion/<garbage-token>` from the terminal.
2. Same response body as the success case. NO 404, NO error.
3. Internal audit chain records `data_lifecycle.cancel_token_invalid` with subtype `unknown` — operators see the truth even though callers don't.

### Steps (phase 2 — fast-forward grace)

1. Re-request deletion as in steps 1–3 above (skip the cancel).
2. In dev, fast-forward the grace clock: `make trigger-cron CRON=grace_monitor`. The monitor advances jobs whose `grace_ends_at <= now()`.
3. The job transitions to `phase_2`; the cascade worker dispatches store-by-store.
4. Audit chain shows `data_lifecycle.workspace_deletion_phase_2` then `data_lifecycle.workspace_deletion_completed` with the tombstone id.
5. PostgreSQL: workspace row's `status='deleted'`; agents/executions/audit rows for that workspace are gone.
6. Qdrant: collection prefix `workspace_<id>_*` empty (`curl http://qdrant:6333/collections | jq` confirms).
7. MinIO: workspace S3 prefix gone.
8. Tombstone: `SELECT * FROM privacy_compliance_tombstones WHERE id = '<tombstone_id>';` — exists, immutable.

---

## Walkthrough 3 — Tenant cancellation with full export (US3)

**Goal**: confirm super-admin tenant deletion produces a final export, honours the 30-day grace, and cascades fully (data, DNS, TLS, secrets) on advance.

### Steps (preflight)

1. As super admin, navigate to `/admin/tenants/acme`. Confirm `subscription_status` is NOT `active` (cancel via `/admin/tenants/acme/billing` first per UPD-052).
2. Issue a fresh 2PA token via the admin workbench's 2PA tray.

### Steps (phase 1)

1. Navigate to `/admin/tenants/acme/delete`.
2. Type `delete tenant acme`. Reason: "Acme contract end."
3. Approve the 2PA prompt.
4. Submit. The page shows the deletion job + the linked final-export job.

### Verify

- PostgreSQL: `SELECT id, phase, grace_ends_at, two_pa_token_id, final_export_job_id FROM deletion_jobs WHERE tenant_id='<acme_id>' ORDER BY created_at DESC LIMIT 1;` — phase `phase_1`, grace 30 d ahead, tokens populated.
- Tenants row: `status='pending_deletion'`.
- Audit chain: `data_lifecycle.tenant_deletion_phase_1` with the actor + 2PA token id.
- Mailhog (delivered to tenant admin): "Your final tenant export is being prepared."
- Mailhog (after export completes, ≤ 60 min in prod / few minutes in dev): "Your tenant export is ready" with signed URL + OTP.

### Phase 2 (after grace)

1. Fast-forward the cron in dev (`make trigger-cron CRON=grace_monitor`).
2. Cascade dispatches:
   - PostgreSQL adapter: tenant_id-scoped DELETE across every tenant-scoped table.
   - Qdrant adapter: collections under tenant prefix dropped.
   - Neo4j adapter: nodes with `tenant_id` property and their edges deleted.
   - ClickHouse adapter: tenant rows dropped from analytics tables.
   - OpenSearch adapter: tenant-scoped indices deleted.
   - S3 adapter: tenant prefixes deleted across all buckets.
   - DNS teardown (UPD-053, when `FEATURE_UPD053_DNS_TEARDOWN=true`): tenant subdomain removed; TLS cert revoked.
3. `cascade_completed_at` set; tombstone written; audit chain emits `data_lifecycle.tenant_deletion_completed`.

### Cold-storage retention (US3 acceptance #6)

- The audit chain entry tombstones are mirrored to the `platform-audit-cold-storage` bucket with S3 Object Lock COMPLIANCE mode and 7-year retention.
- `mc stat dev/platform-audit-cold-storage/tenant/<acme_id>/tombstone-<timestamp>.json` shows `lock-mode: COMPLIANCE`, `retain-until: 2033-...`.

---

## Walkthrough 4 — Sub-processors public page (US4)

**Goal**: confirm anyone can read the sub-processors page without auth, RSS works, subscriptions work.

### Steps

1. From an unauthenticated browser, fetch `https://dev.musematic.local/legal/sub-processors`.
2. Confirm the page lists Anthropic, OpenAI, Hetzner, Stripe with category, location, links.
3. Confirm the `Last updated` timestamp matches `MAX(updated_at) FROM sub_processors`.
4. Fetch `https://dev.musematic.local/legal/sub-processors.rss` — XML feed.

### Add a new sub-processor

1. Sign in as super admin; navigate to `/admin/legal/sub-processors`.
2. Click **Add**. Fill in MaxMind, Inc.; category Fraud; USA; data_categories `["ip_addresses"]`; URL.
3. Save. Within 30 seconds, the public page reflects the new entry.

### Verify

- Kafka: `kafka-console-consumer --topic data_lifecycle.events --max-messages 1 | jq 'select(.event_type=="data_lifecycle.sub_processor.added")'` shows the event.
- Audit chain: `data_lifecycle.sub_processor_change` entry with subtype `added`.
- RSS feed: new `<item>` for "Added: MaxMind".
- Subscribers: any subscribed email receives a UPD-077 webhook fanout (HMAC-signed).

### Outage independence (rule 49)

1. Stop the main control-plane Deployment: `kubectl scale deploy/control-plane --replicas=0 -n platform`.
2. Reload the public page — STILL works because the `public-pages` Deployment is independent and uses the regenerator's snapshot ConfigMap as a fallback.
3. Restore: `kubectl scale deploy/control-plane --replicas=2`.

---

## Walkthrough 5 — DPA upload at tenant creation (US5)

**Goal**: confirm a super admin can upload a DPA PDF that is virus-scanned, hashed, and stored in Vault.

### Steps (clean upload)

1. As super admin, navigate to `/admin/dpa` for tenant Acme.
2. Click **Upload DPA**. Select a small clean PDF (the `eicar.txt` test file is for the next test).
3. Choose version `v3.0`, effective date today.
4. Click **Upload**. The progress bar shows `Scanning…` then `Storing…` then `Done`.

### Verify

- PostgreSQL: `SELECT dpa_signed_at, dpa_version, dpa_artifact_uri, dpa_artifact_sha256 FROM tenants WHERE slug='acme';` — values populated.
- Vault: `vault kv get secret/data/musematic/dev/tenants/acme/dpa/dpa-v3.0.pdf` returns the metadata (PDF base64-encoded in `data`).
- Audit chain: `data_lifecycle.dpa_uploaded` with actor, version, sha256.

### Steps (virus-positive upload)

1. Click **Upload DPA** again. Select an EICAR test file renamed `eicar.pdf`.
2. Click Upload. ClamAV detects the signature.
3. UI shows `Virus detected: Eicar-Test-Signature. Upload rejected.`
4. PostgreSQL `tenants` row UNCHANGED. Vault path NOT written.
5. Audit chain: `data_lifecycle.dpa_rejected_virus` with the signature name.

### Steps (scanner unreachable)

1. `kubectl scale deploy/clamav --replicas=0 -n platform-data`.
2. Click **Upload DPA**. After 25 seconds, UI shows `DPA scanner unavailable. Try again later.`
3. PostgreSQL UNCHANGED. Vault NOT written.
4. Audit chain: `data_lifecycle.dpa_scan_unavailable`.
5. Restore: `kubectl scale deploy/clamav --replicas=1`.

---

## Journey J27 — Tenant Lifecycle Cancellation (rule 25)

End-to-end real-cluster journey crossing workspaces, registry, audit, S3, and (when flag on) DNS. Asserted via real Loki/Prometheus queries (rule 26):

1. Bootstrap: tenant `j27-acme` with two workspaces.
2. Workspace owner of `j27-acme/main` requests workspace export. Wait for completion. Download URL valid.
3. Super admin requests tenant export. Wait for completion. Receive URL + OTP.
4. Super admin schedules tenant deletion. Verify final export completes.
5. Fast-forward grace. Verify cascade across all six store types. Tombstone present.
6. Verify audit chain integrity: `python tools/verify_audit_chain.py --tenant j27-acme` — chain hash verifies even after cascade.
7. Verify Loki query: `{service="control-plane",bounded_context="data_lifecycle"} |= "tenant_deletion_completed"` returns the expected log line.
8. Verify Prometheus: `data_lifecycle_export_duration_seconds` p95 ≤ 60 min.
9. Backup-purge T+30 (in CI: stub the wall-clock advance): `data_lifecycle.backup.purge_completed` event observed; KMS key destroyed.

J27 lives at `tests/e2e/journeys/j27_tenant_lifecycle_cancellation.py`.

---

## Troubleshooting

### Export job stuck in `processing`

The Redis lease prevents concurrent dispatch but does not auto-release on worker crash. After lease TTL (~65 min), the job becomes pickable again. Check `redis-cli TTL data_lifecycle:export_lease:<job_id>`. Manual override: `redis-cli DEL data_lifecycle:export_lease:<job_id>` then mark the job `failed` via the operator runbook.

### Cascade reports a missing adapter

The R1 extension to `CascadeAdapter` requires every existing adapter to implement `execute_for_workspace` / `execute_for_tenant`. If a new adapter has been added to `privacy_compliance/cascade_adapters/` after this feature shipped, that adapter must add the scope-level methods. Migration check: `grep -l "execute_for_tenant" apps/control-plane/src/platform/privacy_compliance/cascade_adapters/*.py | wc -l` should equal the number of `*_adapter.py` files.

### DNS teardown leaves a dangling record

When `FEATURE_UPD053_DNS_TEARDOWN=false`, the cascade reports `dns_teardown_skipped` warning. Run `deploy/runbooks/data-lifecycle/dns-teardown-manual.md` for the manual cleanup procedure.

### Public sub-processors page returns 503 during a control-plane outage

This should not happen — the `public-pages` release uses a snapshot ConfigMap. If it does, confirm: `kubectl get configmap -n platform-public public-pages-sub-processors-snapshot -o yaml | grep -c "items"`. If empty, manually trigger the regenerator: `kubectl create job --from=cronjob/sub-processors-regenerator manual-1 -n platform`.

### Final tenant export password not arriving

Check Mailhog AND, when `FEATURE_UPD077_DPA_SMS_PASSWORD=true`, the Twilio sandbox console. If neither received, the OTP fallback applies — direct the tenant admin to the `/legal/access-recovery` page (UPD-077).
