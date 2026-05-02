# Quickstart — UPD-049 Marketplace Scope

**Audience**: developers, operators, and reviewers picking up the feature for the
first time. Each section is a self-contained walkthrough that exercises one of the
five user stories from `spec.md`.

---

## Prerequisites

```bash
# from repo root
make dev-up                 # brings up postgres, redis, kafka, control plane, and web
make migrate                # apply all migrations, including 108_marketplace_scope_and_review.py
```

Confirm migration 108 is at head:

```bash
cd apps/control-plane && alembic current
# expected: 108_marketplace_scope_review (head)
```

Verify the new RLS policy:

```bash
psql "$DATABASE_URL" -c "\d+ registry_agent_profiles" | grep -A 10 'Policies'
# expected: agents_visibility — three USING branches
```

Verify the configuration block:

```bash
psql "$DATABASE_URL" -c \
  "SELECT marketplace_scope, review_status, COUNT(*)
     FROM registry_agent_profiles
    GROUP BY 1, 2 ORDER BY 1, 2;"
# expected after migration: all rows have marketplace_scope='workspace', review_status='draft' (defaults)
```

---

## Scenario 1 — Default-tenant creator publishes to public marketplace (US1)

**Persona**: Alice, a Pro user on the default tenant, owns a `pdf-extractor` agent.

```bash
# 1. Alice publishes with public scope.
curl -X POST "$API/api/v1/registry/agents/$AGENT_ID/publish" \
  -H "Authorization: Bearer $ALICE_JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "scope": "public_default_tenant",
    "marketing_metadata": {
      "category": "data-extraction",
      "marketing_description": "Extract structured data from PDFs (tables, forms, headers).",
      "tags": ["pdf", "extraction", "structured-output"]
    }
  }'
# expected: 200 OK with review_status: "pending_review"
```

```bash
# 2. Verify it appears in the review queue (super-admin perspective).
curl "$API/api/v1/admin/marketplace-review/queue" \
  -H "Authorization: Bearer $SUPER_ADMIN_JWT"
# expected: items[0].agent_id == AGENT_ID; submitted_at is recent
```

```bash
# 3. Super admin claims and approves.
curl -X POST "$API/api/v1/admin/marketplace-review/$AGENT_ID/claim" \
  -H "Authorization: Bearer $SUPER_ADMIN_JWT"

curl -X POST "$API/api/v1/admin/marketplace-review/$AGENT_ID/approve" \
  -H "Authorization: Bearer $SUPER_ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{ "notes": "Looks good" }'
# expected: review_status: "published"
```

```bash
# 4. A second default-tenant user (Bob) sees the agent in the marketplace.
curl "$API/api/v1/marketplace/search?q=pdf" \
  -H "Authorization: Bearer $BOB_JWT" \
  | jq '.items[] | select(.fqn | contains("pdf-extractor"))'
# expected: one match with marketplace_scope: "public_default_tenant"
```

---

## Scenario 2 — Enterprise tenant cannot publish public (US2)

**Persona**: Carol, an Acme-tenant user, attempts to publish her agent publicly.

```bash
# 1. UI test (Playwright): Carol opens /agent-management/<fqn>/publish.
#    The "public_default_tenant" scope option is visible but disabled with a tooltip.
pnpm --filter web test:e2e tests/marketplace/publish-scope-picker.spec.ts

# 2. Direct API call from Carol bypassing the UI is refused.
curl -X POST "$API/api/v1/registry/agents/$ACME_AGENT_ID/publish" \
  -H "Authorization: Bearer $CAROL_JWT" \
  -H "Content-Type: application/json" \
  -d '{ "scope": "public_default_tenant" }'
# expected: 403 with code public_scope_not_allowed_for_enterprise
```

```bash
# 3. Direct database INSERT bypassing the service is refused by the CHECK.
psql "$DATABASE_URL" -c "
  INSERT INTO registry_agent_profiles
    (id, tenant_id, workspace_id, namespace_id, local_name, fqn, purpose, role_types,
     visibility_agents, visibility_tools, tags, status, created_by, marketplace_scope)
  VALUES (gen_random_uuid(), '$ACME_TENANT_ID', ..., 'public_default_tenant')
"
# expected: ERROR — registry_agent_profiles_public_only_default_tenant violated
```

---

## Scenario 3 — Enterprise tenant with consume flag sees public agents (US3)

**Persona**: Super admin enables `consume_public_marketplace` on Acme. Carol now sees
public agents.

```bash
# 1. Super admin sets the flag on Acme.
curl -X PATCH "$API/api/v1/admin/tenants/$ACME_TENANT_ID" \
  -H "Authorization: Bearer $SUPER_ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{ "feature_flags": { "consume_public_marketplace": true } }'
# expected: 200 OK with feature_flags.consume_public_marketplace: true
```

```bash
# 2. Verify the resolver picks up the flag.
psql "$DATABASE_URL" -c "
  SELECT slug, feature_flags->>'consume_public_marketplace' AS consume
    FROM tenants WHERE id = '$ACME_TENANT_ID';
"
# expected: consume='true'

# 3. Verify the audit chain entry was written.
psql "$DATABASE_URL" -c "
  SELECT event_type, payload->>'flag_name', payload->>'to_value'
    FROM audit_chain_entries
   WHERE tenant_id = '$ACME_TENANT_ID'
   ORDER BY entry_seq DESC LIMIT 1;
"
# expected: tenants.feature_flag_changed | consume_public_marketplace | true

# 4. Verify the Kafka event was published.
kafkactl consume tenants.lifecycle --max-messages=1 --from-beginning=false
# expected: tenants.feature_flag_changed envelope with the flag change
```

```bash
# 5. Carol's marketplace listing now includes public agents.
curl "$API/api/v1/marketplace/search?q=pdf" \
  -H "Authorization: Bearer $CAROL_JWT" \
  | jq '.items[].marketplace_scope' | sort | uniq -c
# expected: includes 'public_default_tenant' rows alongside 'tenant' rows
```

---

## Scenario 4 — Enterprise tenant without consume flag is fully isolated (US4)

**Persona**: Dan, a Globex user, has no consume flag.

```bash
curl "$API/api/v1/marketplace/search" -H "Authorization: Bearer $DAN_JWT" \
  | jq '.items[].marketplace_scope' | sort | uniq
# expected: ONLY 'workspace' and 'tenant' — no 'public_default_tenant'

# Direct fetch of a known public agent's detail page returns 404 for Dan.
curl -i "$API/api/v1/registry/agents/$PUBLIC_AGENT_ID" \
  -H "Authorization: Bearer $DAN_JWT"
# expected: HTTP/1.1 404 Not Found
```

The 404 (not 403) is intentional: existence is hidden.

---

## Scenario 5 — Forking a public agent into a private tenant (US5)

**Persona**: Carol (Acme, with consume flag) forks Alice's published `pdf-extractor`.

```bash
curl -X POST "$API/api/v1/registry/agents/$ALICE_AGENT_ID/fork" \
  -H "Authorization: Bearer $CAROL_JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "target_scope": "tenant",
    "new_name": "acme-pdf-extractor"
  }'
# expected: 201 with forked_from_agent_id: ALICE_AGENT_ID
```

```bash
# Verify the fork lives in Acme.
psql "$DATABASE_URL" -c "
  SET LOCAL app.tenant_id = '$ACME_TENANT_ID';
  SELECT fqn, marketplace_scope, review_status, forked_from_agent_id
    FROM registry_agent_profiles
   WHERE local_name = 'acme-pdf-extractor';
"
# expected:
#   fqn = '<acme-namespace>:acme-pdf-extractor'
#   marketplace_scope = 'tenant'
#   review_status = 'draft'
#   forked_from_agent_id = ALICE_AGENT_ID
```

```bash
# Verify the source agent is unchanged.
psql "$DATABASE_URL" -c "
  SET LOCAL app.tenant_id = '$DEFAULT_TENANT_ID';
  SELECT fqn, marketplace_scope, review_status FROM registry_agent_profiles
   WHERE id = '$ALICE_AGENT_ID';
"
# expected: still public_default_tenant / published
```

```bash
# Verify the marketplace.forked Kafka event.
kafkactl consume marketplace.events --max-messages=1 \
  --filter='event_type=marketplace.forked'
# expected: payload has source_agent_id=ALICE_AGENT_ID, fork_agent_id=<new>
```

---

## Source-update notification (US5 follow-on)

```bash
# Alice publishes a new revision of pdf-extractor and submits for re-review.
curl -X POST "$API/api/v1/registry/agents/$ALICE_AGENT_ID/publish" \
  -H "Authorization: Bearer $ALICE_JWT" \
  -d '{ "scope": "public_default_tenant", "marketing_metadata": { ... } }'
# expected: review_status: pending_review (the previously published version stays
# visible until the new version is approved)

# Super admin approves.
curl -X POST "$API/api/v1/admin/marketplace-review/$ALICE_AGENT_ID/approve" \
  -H "Authorization: Bearer $SUPER_ADMIN_JWT" -d '{}'

# Carol's notification inbox now shows a marketplace.source_updated alert.
curl "$API/api/v1/users/$CAROL_USER_ID/alerts" \
  -H "Authorization: Bearer $CAROL_JWT" \
  | jq '.items[] | select(.type == "marketplace.source_updated")'
# expected: one alert citing pdf-extractor's FQN and stating the fork has NOT been auto-updated
```

---

## Operator runbook — flipping `consume_public_marketplace`

When a contract addendum requires giving an Enterprise tenant access to the public
marketplace:

1. Confirm the contract is signed and the request is in writing (the audit chain entry
   will be the durable record).
2. Run the PATCH from Scenario 3 with the super-admin JWT.
3. Verify the audit chain entry and Kafka event landed.
4. Notify the tenant's primary contact via email that the flag is on (template
   in `deploy/runbooks/marketplace-consume-flag.md`).
5. To revoke, run the same PATCH with `false`. Existing forks remain — they're now
   orphaned reference points; the consumer will no longer see source-update
   notifications because the source becomes invisible to them again.
