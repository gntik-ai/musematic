# Quickstart: Privacy Compliance (GDPR / CCPA)

**Feature**: 076-privacy-compliance
**Date**: 2026-04-25

Six walkthroughs (Q1–Q6), one per user story. Run against `make dev-up`.

## Boot

```bash
make dev-up
export PLATFORM_API_URL=http://localhost:8081
export QS_RUN_ID="$(date +%s)"

export SUPERADMIN_ID="$(python3 tests/e2e/scripts/dev_auth.py provision-user \
  --email j-admin@e2e.test)"
export PRIVACY_OFFICER_ID="$(python3 tests/e2e/scripts/dev_auth.py provision-user \
  --email j-privacy@e2e.test)"
export CONSUMER_ID="$(python3 tests/e2e/scripts/dev_auth.py provision-user \
  --email j-consumer@e2e.test)"
export AUDITOR_ID="$(python3 tests/e2e/scripts/dev_auth.py provision-user \
  --email j-auditor@e2e.test)"

export SUPERADMIN_TOKEN="$(python3 tests/e2e/scripts/dev_auth.py mint \
  --email j-admin@e2e.test --role superadmin --user-id "$SUPERADMIN_ID")"
export PRIVACY_OFFICER_TOKEN="$(python3 tests/e2e/scripts/dev_auth.py mint \
  --email j-privacy@e2e.test --role privacy_officer --user-id "$PRIVACY_OFFICER_ID")"
export CONSUMER_TOKEN="$(python3 tests/e2e/scripts/dev_auth.py mint \
  --email j-consumer@e2e.test --role creator --user-id "$CONSUMER_ID")"
export AUDITOR_TOKEN="$(python3 tests/e2e/scripts/dev_auth.py mint \
  --email j-auditor@e2e.test --role auditor --user-id "$AUDITOR_ID")"

export WS_ID="$(curl -sf -X POST "$PLATFORM_API_URL/api/v1/workspaces" \
  -H "Authorization: Bearer $SUPERADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"privacy-quickstart-'"$QS_RUN_ID"'","description":"Privacy compliance quickstart workspace"}' \
  | jq -r '.id')"
export AGENT_ID="$(python3 - <<'PY'
from uuid import uuid4
print(uuid4())
PY
)"
```

---

## Q1 — Run an erasure DSR with full cascade (US1)

```bash
# Provision a subject and generate data across all stores
export SUBJECT_ID="$(python3 tests/e2e/scripts/dev_auth.py \
  provision-subject --email j-subject@e2e.test)"

# (Interact with the platform as the subject to populate stores; omitted)

# Open an erasure DSR
export DSR_ID="$(curl -sf -X POST "$PLATFORM_API_URL/api/v1/privacy/dsr" \
  -H "Authorization: Bearer $PRIVACY_OFFICER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "subject_user_id": "'"$SUBJECT_ID"'",
    "request_type": "erasure",
    "legal_basis": "Consent withdrawn per GDPR Art. 17(1)(b)",
    "hold_hours": 0
  }' | jq -r '.id')"

# Process and watch status
curl -sf -X POST "$PLATFORM_API_URL/api/v1/privacy/dsr/$DSR_ID/process" \
  -H "Authorization: Bearer $PRIVACY_OFFICER_TOKEN" \
  | jq '{status, completed_at, tombstone_id, completion_proof_hash}'

curl -sf -H "Authorization: Bearer $PRIVACY_OFFICER_TOKEN" \
  "$PLATFORM_API_URL/api/v1/privacy/dsr/$DSR_ID" \
  | jq '{status, completed_at, tombstone_id, completion_proof_hash}'

# Fetch tombstone
curl -sf -H "Authorization: Bearer $AUDITOR_TOKEN" \
  "$PLATFORM_API_URL/api/v1/privacy/dsr/$DSR_ID/tombstone" \
  | jq '{entities_deleted, proof_hash, cascade_log: .cascade_log | length}'
# {
#   "entities_deleted": {"postgresql":47,"qdrant":12,"opensearch":8,"s3":3,"clickhouse":156,"neo4j":4},
#   "proof_hash": "ab12cd34...",
#   "cascade_log": 6
# }

# Export signed tombstone
curl -sf -X POST -H "Authorization: Bearer $AUDITOR_TOKEN" \
  "$PLATFORM_API_URL/api/v1/privacy/dsr/$DSR_ID/tombstone/signed" \
  | tee /tmp/tombstone-signed.json \
  | jq '{key_version, signature: .signature[0:32]}'

# Verify externally
PUBKEY="$(curl -sf -H "Authorization: Bearer $AUDITOR_TOKEN" \
  "$PLATFORM_API_URL/api/v1/security/audit-chain/public-key")"
python3 tests/e2e/scripts/verify_signed_tombstone.py \
  /tmp/tombstone-signed.json --public-key "$PUBKEY"
# signed tombstone verified
```

---

## Q2 — First agent interaction shows AI disclosure + consent (US2)

```bash
# New user with no consents yet
export NEW_USER_ID="$(python3 tests/e2e/scripts/dev_auth.py provision-user \
  --email j-new@e2e.test)"
export NEW_USER_TOKEN="$(python3 tests/e2e/scripts/dev_auth.py mint \
  --email j-new@e2e.test --role creator --user-id "$NEW_USER_ID")"

# Try to start a conversation → expect 428 Precondition Required
curl -si -X POST "$PLATFORM_API_URL/api/v1/interactions/conversations" \
  -H "Authorization: Bearer $NEW_USER_TOKEN" \
  -H "X-Workspace-ID: $WS_ID" \
  -H "Content-Type: application/json" \
  -d '{"title":"consent gate smoke"}' | head -12
# HTTP/1.1 428 Precondition Required
# {"error":"consent_required","missing_consents":["ai_interaction","data_collection","training_use"],"disclosure_text_ref":"/api/v1/me/consents/disclosure"}

# Fetch disclosure + record choices
curl -sf -H "Authorization: Bearer $NEW_USER_TOKEN" \
  "$PLATFORM_API_URL/api/v1/me/consents/disclosure" | jq '.text' | head -5

curl -sf -X PUT "$PLATFORM_API_URL/api/v1/me/consents" \
  -H "Authorization: Bearer $NEW_USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_id": "'"$WS_ID"'",
    "choices": {
      "ai_interaction": true,
      "data_collection": true,
      "training_use": false
    }
  }' | jq 'length'
# 3

# Conversation now proceeds
curl -sf -X POST "$PLATFORM_API_URL/api/v1/interactions/conversations" \
  -H "Authorization: Bearer $NEW_USER_TOKEN" \
  -H "X-Workspace-ID: $WS_ID" \
  -H "Content-Type: application/json" \
  -d '{"title":"consented conversation"}' | jq '.id'

# Revoke training_use
curl -sf -X POST \
  "$PLATFORM_API_URL/api/v1/me/consents/training_use/revoke" \
  -H "Authorization: Bearer $NEW_USER_TOKEN"

# History
curl -sf -H "Authorization: Bearer $NEW_USER_TOKEN" \
  "$PLATFORM_API_URL/api/v1/me/consents/history" \
  | jq '.[] | {consent_type, granted, granted_at, revoked_at}'
```

---

## Q3 — Privacy officer approves a PIA (US3)

```bash
# Creator submits a draft PIA for an agent declaring PII processing
export PIA_ID="$(curl -sf -X POST "$PLATFORM_API_URL/api/v1/privacy/pia" \
  -H "Authorization: Bearer $CONSUMER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "subject_type": "agent",
    "subject_id": "'"$AGENT_ID"'",
    "data_categories": ["pii", "behavioral"],
    "legal_basis": "Legitimate interest — HR compliance per GDPR Art. 6(1)(f)",
    "retention_policy": "Erase after 24 months of inactivity",
    "risks": [{"category":"unauthorized_access","severity":"medium"}],
    "mitigations": [{"mitigation":"encrypt_at_rest","status":"implemented"}]
  }' | jq -r '.id')"

# Submit for review
curl -sf -X POST "$PLATFORM_API_URL/api/v1/privacy/pia/$PIA_ID/submit" \
  -H "Authorization: Bearer $CONSUMER_TOKEN"

# Submitter trying to self-approve → 403
curl -si -X POST "$PLATFORM_API_URL/api/v1/privacy/pia/$PIA_ID/approve" \
  -H "Authorization: Bearer $CONSUMER_TOKEN" | head -1
# HTTP/1.1 403 Forbidden

# Privacy officer approves
curl -sf -X POST "$PLATFORM_API_URL/api/v1/privacy/pia/$PIA_ID/approve" \
  -H "Authorization: Bearer $PRIVACY_OFFICER_TOKEN"

# Active PIA lookup now resolves for the agent subject.
curl -sf "$PLATFORM_API_URL/api/v1/privacy/pia/subject/agent/$AGENT_ID/active" \
  -H "Authorization: Bearer $PRIVACY_OFFICER_TOKEN" \
  | jq '{id, status, data_categories}'
```

---

## Q4 — Workspace admin enforces data residency (US4)

```bash
# Configure workspace to EU-only
curl -sf -X PUT "$PLATFORM_API_URL/api/v1/privacy/residency/$WS_ID" \
  -H "Authorization: Bearer $SUPERADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "region_code": "eu-central-1",
    "allowed_transfer_regions": ["eu-west-1"]
  }'

# Check a request from US-East → expect rejection
curl -si -X POST "$PLATFORM_API_URL/api/v1/privacy/residency/$WS_ID/check" \
  -H "Authorization: Bearer $AUDITOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"origin_region":"us-east-1"}' | head -3
# HTTP/1.1 403 Forbidden
# {"error":{"code":"PRIVACY_RESIDENCY_VIOLATION","details":{"origin_region":"us-east-1","required_region":"eu-central-1","allowed_transfer_regions":["eu-west-1"]}}}

# Check from eu-central-1 → succeeds
curl -sf -X POST "$PLATFORM_API_URL/api/v1/privacy/residency/$WS_ID/check" \
  -H "Authorization: Bearer $AUDITOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"origin_region":"eu-central-1"}' | jq '.allowed'

# Fetch the effective residency config.
curl -sf -H "Authorization: Bearer $AUDITOR_TOKEN" \
  "$PLATFORM_API_URL/api/v1/privacy/residency/$WS_ID" \
  | jq '{region_code, allowed_transfer_regions}'
```

---

## Q5 — Privacy officer configures DLP rules and reviews events (US5)

```bash
# Seeded rules already active. Add a workspace-scoped rule.
curl -sf -X POST "$PLATFORM_API_URL/api/v1/privacy/dlp/rules" \
  -H "Authorization: Bearer $PRIVACY_OFFICER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_id": "'"$WS_ID"'",
    "name": "internal_project_alpha",
    "classification": "confidential",
    "pattern": "(?i)Project\\s+Alpha",
    "action": "block"
  }'

# Drive an agent execution that would produce a match
# (The tool output contains "Project Alpha" — blocked before reaching agent)

# Fetch events
curl -sf -H "Authorization: Bearer $PRIVACY_OFFICER_TOKEN" \
  "$PLATFORM_API_URL/api/v1/privacy/dlp/events?workspace_id=$WS_ID" \
  | jq '.[] | {rule_name, classification, action_taken, match_summary}'
# [
#   {"rule_name": "internal_project_alpha", "classification": "confidential", "action_taken": "block", "match_summary": "confidential:internal_project_alpha"}
# ]
# NOTE: match_summary is the classification LABEL — NOT the matched text

# Try to delete a seeded rule → 403
export SSN_SEEDED_RULE_ID="$(curl -sf -H "Authorization: Bearer $PRIVACY_OFFICER_TOKEN" \
  "$PLATFORM_API_URL/api/v1/privacy/dlp/rules" \
  | jq -r '.[] | select(.seeded == true) | .id' | head -1)"
curl -si -X DELETE "$PLATFORM_API_URL/api/v1/privacy/dlp/rules/$SSN_SEEDED_RULE_ID" \
  -H "Authorization: Bearer $PRIVACY_OFFICER_TOKEN" | head -1
# HTTP/1.1 403 Forbidden
```

---

## Q6 — Compliance auditor verifies tombstone chain integrity (US6)

```bash
# Run an erasure (per Q1) then audit.
# Fetch tombstone + signed export
TOMBSTONE_ID=$(curl -sf -H "Authorization: Bearer $AUDITOR_TOKEN" \
  "$PLATFORM_API_URL/api/v1/privacy/dsr/$DSR_ID" | jq -r '.tombstone_id')

curl -sf -X POST -H "Authorization: Bearer $AUDITOR_TOKEN" \
  "$PLATFORM_API_URL/api/v1/privacy/dsr/$DSR_ID/tombstone/signed" \
  -o /tmp/tombstone-signed.json

# Verify externally with ONLY the public key (demonstrates
# independence from the platform)
export PUBKEY="$(curl -sf -H "Authorization: Bearer $AUDITOR_TOKEN" \
  "$PLATFORM_API_URL/api/v1/security/audit-chain/public-key")"

python3 <<'PY'
import os, json, base64, hashlib
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key

with open("/tmp/tombstone-signed.json") as f:
    signed = json.load(f)

canonical = signed["tombstone"]  # already the canonical JSON string
sig = base64.b64decode(signed["signature"])
pub = load_pem_public_key(os.environ["PUBKEY"].encode())
assert isinstance(pub, Ed25519PublicKey), "public key is not Ed25519"
pub.verify(sig, canonical.encode())
print("✓ Ed25519 signature valid")

tombstone = json.loads(canonical)
recomputed = hashlib.sha256(canonical.encode()).hexdigest()
assert recomputed == signed["proof_hash"], "hash mismatch"
print("✓ SHA-256 proof_hash matches canonical payload")
PY

# The same standalone verifier used in Q1 can be shared with external
# assessors and does not import platform code.
python3 tests/e2e/scripts/verify_signed_tombstone.py \
  /tmp/tombstone-signed.json --public-key "$PUBKEY"
# signed tombstone verified
```

**Expected**: Full external-verification in under 5 minutes, using
only the published public key and the platform's documented
canonicalisation rules. No platform API access required beyond the
one fetch of the signed tombstone.
