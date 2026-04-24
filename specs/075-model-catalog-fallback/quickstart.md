# Quickstart: Model Catalog and Fallback

**Feature**: 075-model-catalog-fallback
**Date**: 2026-04-23

Six walkthroughs (Q1-Q6), one per user story. Run against `make dev-up`.

## Boot

```bash
make dev-up
export PLATFORM_API_URL=http://localhost:8081
export SYSTEM_BOOTSTRAP_USER_ID=00000000-0000-0000-0000-000000000075

export STEWARD_TOKEN="$(python3 tests/e2e/scripts/dev_auth.py mint \
  --email j-steward@e2e.test --role platform_admin \
  --user-id "$SYSTEM_BOOTSTRAP_USER_ID")"

export CREATOR_TOKEN_NO_WS="$(python3 tests/e2e/scripts/dev_auth.py mint \
  --email j-creator@e2e.test --role creator)"

export TRUST_TOKEN="$(python3 tests/e2e/scripts/dev_auth.py mint \
  --email j-reviewer@e2e.test --role trust_certifier \
  --user-id "$SYSTEM_BOOTSTRAP_USER_ID")"

export WS_ID="$(
  curl -sf -X POST "$PLATFORM_API_URL/api/v1/workspaces" \
    -H "Authorization: Bearer $CREATOR_TOKEN_NO_WS" \
    -H "Content-Type: application/json" \
    -d '{"name":"model-catalog-quickstart","description":"Temporary quickstart workspace"}' \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])'
)"

export CREATOR_TOKEN="$(python3 tests/e2e/scripts/dev_auth.py mint \
  --email j-creator@e2e.test --role creator --workspace-id "$WS_ID")"

export TRUST_TOKEN="$(python3 tests/e2e/scripts/dev_auth.py mint \
  --email j-reviewer@e2e.test --role trust_certifier \
  --workspace-id "$WS_ID" --user-id "$SYSTEM_BOOTSTRAP_USER_ID")"

export MODEL_SUFFIX="$(python3 -c 'import uuid; print(uuid.uuid4().hex[:8])')"
```

The steward and trust tokens use the migration-seeded bootstrap user because
catalogue approvals are audit-linked to the `users` table.

---

## Q1 - Curate the approved catalogue (US1)

```bash
# Migration 059 seeds the approved entries.
curl -sf -H "Authorization: Bearer $STEWARD_TOKEN" \
  "$PLATFORM_API_URL/api/v1/model-catalog/entries"

# Add and block a temporary model entry.
export ENTRY_ID="$(
  curl -sf -X POST "$PLATFORM_API_URL/api/v1/model-catalog/entries" \
    -H "Authorization: Bearer $STEWARD_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
      "provider": "mistral",
      "model_id": "mistral-large-'"$MODEL_SUFFIX"'",
      "display_name": "Mistral Large Quickstart",
      "context_window": 128000,
      "input_cost_per_1k_tokens": "0.004",
      "output_cost_per_1k_tokens": "0.012",
      "quality_tier": "tier1",
      "approval_expires_at": "2026-10-23T00:00:00Z"
    }' | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])'
)"

curl -sf -X POST \
  "$PLATFORM_API_URL/api/v1/model-catalog/entries/$ENTRY_ID/block" \
  -H "Authorization: Bearer $STEWARD_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"justification":"quickstart safety block"}'
```

---

## Q2 - Bind an agent and observe catalogue validation (US2)

```bash
export NS_NAME="test-$MODEL_SUFFIX"
curl -sf -X POST "$PLATFORM_API_URL/api/v1/namespaces" \
  -H "Authorization: Bearer $CREATOR_TOKEN" \
  -H "X-Workspace-ID: $WS_ID" \
  -H "Content-Type: application/json" \
  -d '{"name":"'"$NS_NAME"'","description":"Model catalog quickstart namespace"}'

export AGENT_ID="$(
  curl -sf -X POST "$PLATFORM_API_URL/api/v1/agents/upload" \
    -H "Authorization: Bearer $CREATOR_TOKEN" \
    -H "X-Workspace-ID: $WS_ID" \
    -F "namespace_name=$NS_NAME" \
    -F "package=@tests/e2e/journeys/fixtures/agent_package.tar.gz" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["agent_profile"]["id"])'
)"

curl -sf -X PATCH "$PLATFORM_API_URL/api/v1/agents/$AGENT_ID" \
  -H "Authorization: Bearer $CREATOR_TOKEN" \
  -H "X-Workspace-ID: $WS_ID" \
  -H "Content-Type: application/json" \
  -d '{"default_model_binding":"openai:gpt-4o"}'

# The blocked entry from Q1 is rejected by binding validation.
curl -si -X PATCH "$PLATFORM_API_URL/api/v1/agents/$AGENT_ID" \
  -H "Authorization: Bearer $CREATOR_TOKEN" \
  -H "X-Workspace-ID: $WS_ID" \
  -H "Content-Type: application/json" \
  -d '{"default_model_binding":"mistral:mistral-large-'"$MODEL_SUFFIX"'"}'
```

Expected: the final request returns a 4xx response instead of storing the
blocked model binding.

---

## Q3 - Configure a fallback policy (US3)

```bash
export CATALOG_JSON="$(curl -sf -H "Authorization: Bearer $STEWARD_TOKEN" \
  "$PLATFORM_API_URL/api/v1/model-catalog/entries")"
export GPT4O_ENTRY_ID="$(python3 -c 'import json,os; items=json.loads(os.environ["CATALOG_JSON"])["items"]; print(next(i["id"] for i in items if i["provider"]=="openai" and i["model_id"]=="gpt-4o"))')"
export OPUS_ENTRY_ID="$(python3 -c 'import json,os; items=json.loads(os.environ["CATALOG_JSON"])["items"]; print(next(i["id"] for i in items if i["provider"]=="anthropic" and i["model_id"]=="claude-opus-4-6"))')"
export SONNET_ENTRY_ID="$(python3 -c 'import json,os; items=json.loads(os.environ["CATALOG_JSON"])["items"]; print(next(i["id"] for i in items if i["provider"]=="anthropic" and i["model_id"]=="claude-sonnet-4-6"))')"

curl -sf -X POST "$PLATFORM_API_URL/api/v1/model-catalog/fallback-policies" \
  -H "Authorization: Bearer $STEWARD_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name":"default-openai-to-anthropic-'"$MODEL_SUFFIX"'",
    "scope_type":"global",
    "primary_model_id":"'"$GPT4O_ENTRY_ID"'",
    "fallback_chain":["'"$OPUS_ENTRY_ID"'","'"$SONNET_ENTRY_ID"'"],
    "retry_count":3,
    "backoff_strategy":"exponential",
    "acceptable_quality_degradation":"tier_plus_one",
    "recovery_window_seconds":300
  }'
```

Expected: the policy is persisted with a two-entry fallback chain. Runtime
fallback dispatch is covered by `tests/integration/model_catalog/test_fallback_e2e.py`.

---

## Q4 - Review model cards during certification (US4)

```bash
curl -sf -X PUT "$PLATFORM_API_URL/api/v1/model-catalog/entries/$GPT4O_ENTRY_ID/card" \
  -H "Authorization: Bearer $STEWARD_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "capabilities":"General-purpose multimodal reasoning and tool orchestration.",
    "training_cutoff":"2024-10-01",
    "known_limitations":"May require external tools for fresh facts.",
    "safety_evaluations":{"quickstart":"passed"},
    "bias_assessments":{"quickstart":"reviewed"},
    "card_url":"https://example.com/cards/gpt-4o.html"
  }'

export AGENT_REVISION_ID="$(
  curl -sf -H "Authorization: Bearer $CREATOR_TOKEN" \
    -H "X-Workspace-ID: $WS_ID" \
    "$PLATFORM_API_URL/api/v1/agents/$AGENT_ID" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["current_revision"]["id"])'
)"

curl -sf -X POST "$PLATFORM_API_URL/api/v1/trust/certifications" \
  -H "Authorization: Bearer $TRUST_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id":"'"$AGENT_ID"'",
    "agent_fqn":"'"$NS_NAME"':fixture-agent",
    "agent_revision_id":"'"$AGENT_REVISION_ID"'"
  }'
```

Expected: certification creation succeeds when the bound model has a card.

---

## Q5 - Rotate a workspace provider credential without downtime (US5)

```bash
export CRED_ID="$(
  curl -sf -X POST "$PLATFORM_API_URL/api/v1/model-catalog/credentials" \
    -H "Authorization: Bearer $STEWARD_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
      "workspace_id":"'"$WS_ID"'",
      "provider":"openai",
      "vault_ref":"test-db-password"
    }' | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])'
)"

curl -sf -X POST "$PLATFORM_API_URL/api/v1/model-catalog/credentials/$CRED_ID/rotate" \
  -H "Authorization: Bearer $STEWARD_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"overlap_window_hours":24}'
```

Expected: the rotation response enters `overlap`. The e2e chart seeds
`ROTATING_SECRET_TEST_DB_PASSWORD_CURRENT`, which backs the `test-db-password`
reference.

---

## Q6 - Manage prompt-injection defence patterns (US6)

```bash
curl -sf -H "Authorization: Bearer $STEWARD_TOKEN" \
  -H "X-Workspace-ID: $WS_ID" \
  "$PLATFORM_API_URL/api/v1/model-catalog/injection-patterns?layer=input_sanitizer"

export PATTERN_ID="$(
  curl -sf -X POST "$PLATFORM_API_URL/api/v1/model-catalog/injection-patterns" \
    -H "Authorization: Bearer $STEWARD_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
      "pattern_name":"quickstart-ignore-'"$MODEL_SUFFIX"'",
      "pattern_regex":"ignore all previous instructions",
      "severity":"high",
      "layer":"input_sanitizer",
      "action":"quote_as_data",
      "workspace_id":"'"$WS_ID"'"
    }' | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])'
)"

curl -sf -H "Authorization: Bearer $STEWARD_TOKEN" \
  -H "X-Workspace-ID: $WS_ID" \
  "$PLATFORM_API_URL/api/v1/model-catalog/injection-findings?workspace_id=$WS_ID"

curl -sf -X DELETE "$PLATFORM_API_URL/api/v1/model-catalog/injection-patterns/$PATTERN_ID" \
  -H "Authorization: Bearer $STEWARD_TOKEN"
```

Expected: seeded patterns are listed, a workspace-scoped pattern can be
created and deleted, and findings are queryable. Router-level block/redaction
behaviour is covered by `tests/integration/model_catalog/test_injection_corpus.py`.
