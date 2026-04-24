# Quickstart: Security Compliance and Supply Chain

**Feature**: 074-security-compliance
**Date**: 2026-04-23

Six walkthroughs (Q1–Q6), one per user story. Each runs against
`make dev-up`.

## Boot

```bash
make dev-up
export PLATFORM_API_URL=http://localhost:8081
export MOCK_GOOGLE_OIDC_URL=http://localhost:8083
export MOCK_GITHUB_OAUTH_URL=http://localhost:8084
export BOOTSTRAP_ADMIN_TOKEN="$(python3 tests/e2e/scripts/dev_auth.py mint \
  --email j-admin@e2e.test --role platform_admin)"
python3 tests/e2e/scripts/dev_auth.py bootstrap-providers \
  --api-base "$PLATFORM_API_URL" \
  --admin-token "$BOOTSTRAP_ADMIN_TOKEN" >/dev/null
export QUICKSTART_ADMIN_USER_ID="$(python3 tests/e2e/scripts/dev_auth.py oauth \
  --provider google \
  --login j-consumer \
  --api-base "$PLATFORM_API_URL" \
  --mock-base "$MOCK_GOOGLE_OIDC_URL" \
  --json | jq -r '.claims.sub')"
export SUPERADMIN_TOKEN="$(python3 tests/e2e/scripts/dev_auth.py mint \
  --email j-consumer@e2e.test \
  --user-id "$QUICKSTART_ADMIN_USER_ID" \
  --role superadmin)"
export AUDITOR_TOKEN="$(python3 tests/e2e/scripts/dev_auth.py mint \
  --email j-consumer@e2e.test \
  --user-id "$QUICKSTART_ADMIN_USER_ID" \
  --role auditor)"
```

---

## Q1 — Ship a release with SBOM + vuln gating (US1)

```bash
# CI side: run scanners + normalize outputs
python3 ci/normalize_scan_results.py scan-results \
  --release-version 1.4.0 \
  --metadata scan-metadata.json \
  --no-post > /tmp/normalised.json

# Upload SBOM
curl -sf -X POST "$PLATFORM_API_URL/api/v1/security/sbom" \
  -H "Authorization: Bearer $SUPERADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "release_version": "1.4.0",
    "format": "cyclonedx",
    "content": "'"$(cat sbom-cyclonedx.json | jq -c .)"'"
  }' | jq '{id, content_sha256}'

# Upload scan result per scanner
for scanner in trivy pip_audit govulncheck bandit gosec; do
  curl -sf -X POST "$PLATFORM_API_URL/api/v1/security/scans/1.4.0/results" \
    -H "Authorization: Bearer $SUPERADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$(jq --arg s "$scanner" '.[] | select(.scanner==$s)' /tmp/normalised.json)"
done

# Aggregate status
curl -sf -H "Authorization: Bearer $AUDITOR_TOKEN" \
  "$PLATFORM_API_URL/api/v1/security/scans/1.4.0/status"
# { "gating_result": "passed", "scanners": [...], "blocked_findings": [] }
```

**Expected**: SBOM row created; five scan results created; aggregate
status `passed`. Kafka events `security.sbom.published` and
`security.scan.completed` emitted; compliance_evidence auto-populated.

---

## Q2 — Verify audit chain integrity (US2)

```bash
# Trigger a few audit-emitting operations first (any admin action)
curl -sf -X POST "$PLATFORM_API_URL/api/v1/security/pentests" \
  -H "Authorization: Bearer $SUPERADMIN_TOKEN" \
  -d '{"scheduled_for": "2026-07-01", "firm": "AcmeSec"}' >/dev/null

# Run verify
curl -sf -H "Authorization: Bearer $AUDITOR_TOKEN" \
  "$PLATFORM_API_URL/api/v1/security/audit-chain/verify"
# {"valid": true, "entries_checked": 1247, "broken_at": null}

# Export attestation for the last 1,000 entries
curl -sf -X POST -H "Authorization: Bearer $AUDITOR_TOKEN" \
  "$PLATFORM_API_URL/api/v1/security/audit-chain/attestations" \
  -d '{"start_seq": 247, "end_seq": 1247}' | jq '{start_seq, end_seq, signature: .signature[0:32]}'
# { "start_seq": 247, "end_seq": 1247, "signature": "ab12cd34..." }

# Fetch public key + verify signature externally (pseudocode)
PUBKEY=$(curl -sf "$PLATFORM_API_URL/api/v1/security/audit-chain/public-key")

# Tamper: update one row directly in the DB (simulated)
psql -c "UPDATE audit_chain_entries SET entry_hash = 'deadbeef...' WHERE sequence_number = 500"

# Verify detects tamper
curl -sf -H "Authorization: Bearer $AUDITOR_TOKEN" \
  "$PLATFORM_API_URL/api/v1/security/audit-chain/verify"
# {"valid": false, "broken_at": 500}
```

---

## Q3 — Rotate a production credential with zero downtime (US3)

```bash
# Create schedule
curl -sf -X POST "$PLATFORM_API_URL/api/v1/security/rotations" \
  -H "Authorization: Bearer $SUPERADMIN_TOKEN" \
  -d '{
    "secret_name": "test_db_password",
    "secret_type": "db_password",
    "rotation_interval_days": 90,
    "overlap_window_hours": 24,
    "vault_path": "secret/data/musematic/dev/rotating/test-db"
  }' | jq -r '.id' | tee /tmp/rotation_id

# Trigger rotation
curl -sf -X POST \
  "$PLATFORM_API_URL/api/v1/security/rotations/$(cat /tmp/rotation_id)/trigger" \
  -H "Authorization: Bearer $SUPERADMIN_TOKEN"

# Drive load during rotation
for i in $(seq 1 1000); do
  curl -sf "$PLATFORM_API_URL/health" -H "X-Use-Rotating-Secret: test_db_password" >/dev/null
done &

# Watch state transitions (new audit chain entries per stage)
watch -n 2 "curl -sf \"$PLATFORM_API_URL/api/v1/security/rotations/$(cat /tmp/rotation_id)/history\" -H 'Authorization: Bearer $AUDITOR_TOKEN' | jq '.[-3:]'"
```

**Expected**: Zero request failures during overlap. State progresses
`rotating → overlap → finalising → idle`.

---

## Q4 — Issue + use + revoke a JIT credential (US4)

```bash
export ENG_TOKEN="$(python3 tests/e2e/scripts/dev_auth.py mint \
  --email j-creator@e2e.test \
  --user-id "$(python3 tests/e2e/scripts/dev_auth.py oauth \
    --provider github \
    --login j-creator \
    --api-base "$PLATFORM_API_URL" \
    --mock-base "$MOCK_GITHUB_OAUTH_URL" \
    --json | jq -r '.claims.sub')" \
  --role creator)"
export PEER_TOKEN="$(python3 tests/e2e/scripts/dev_auth.py mint \
  --email j-consumer@e2e.test \
  --user-id "$QUICKSTART_ADMIN_USER_ID" \
  --role platform_admin)"

# Request JIT grant
GRANT=$(curl -sf -X POST "$PLATFORM_API_URL/api/v1/security/jit-grants" \
  -H "Authorization: Bearer $ENG_TOKEN" \
  -d '{
    "operation": "db:prod:read",
    "purpose": "Investigating production incident TKT-789",
    "requested_expiry_minutes": 30
  }')
GRANT_ID=$(echo "$GRANT" | jq -r '.id')

# Self-approval should fail
curl -si -X POST "$PLATFORM_API_URL/api/v1/security/jit-grants/$GRANT_ID/approve" \
  -H "Authorization: Bearer $ENG_TOKEN" | head -1
# HTTP/1.1 403 Forbidden

# Peer approves
JIT_JWT=$(curl -sf -X POST \
  "$PLATFORM_API_URL/api/v1/security/jit-grants/$GRANT_ID/approve" \
  -H "Authorization: Bearer $PEER_TOKEN" | jq -r '.jwt')

# Use it against the grant usage endpoint
curl -sf -X POST "$PLATFORM_API_URL/api/v1/security/jit-grants/$GRANT_ID/usage" \
  -H "Authorization: Bearer $JIT_JWT" \
  -d '{"operation":"db:prod:read","target":"readonly-smoke","outcome":"success"}' >/dev/null

# Inspect usage audit
curl -sf -H "Authorization: Bearer $ENG_TOKEN" \
  "$PLATFORM_API_URL/api/v1/security/jit-grants/$GRANT_ID" \
  | jq '.usage_audit'

# Revoke
curl -sf -X POST \
  "$PLATFORM_API_URL/api/v1/security/jit-grants/$GRANT_ID/revoke" \
  -H "Authorization: Bearer $SUPERADMIN_TOKEN"

# JWT now rejected
curl -si -X POST "$PLATFORM_API_URL/api/v1/security/jit-grants/$GRANT_ID/usage" \
  -H "Authorization: Bearer $JIT_JWT" \
  -d '{"operation":"db:prod:read","target":"readonly-smoke","outcome":"after-revoke"}' | head -1
# HTTP/1.1 401 Unauthorized
```

---

## Q5 — Track a pentest through scheduling → import → remediation (US5)

```bash
# Schedule
PT_ID=$(curl -sf -X POST "$PLATFORM_API_URL/api/v1/security/pentests" \
  -H "Authorization: Bearer $SUPERADMIN_TOKEN" \
  -d '{"scheduled_for":"2026-05-01","firm":"AcmeSec"}' | jq -r .id)

# Execute + attach report
curl -sf -X POST "$PLATFORM_API_URL/api/v1/security/pentests/$PT_ID/execute" \
  -H "Authorization: Bearer $SUPERADMIN_TOKEN" \
  -d '{"report_url":"s3://pentests/2026-05.pdf"}'

# Import 3 findings
curl -sf -X POST "$PLATFORM_API_URL/api/v1/security/pentests/$PT_ID/findings" \
  -H "Authorization: Bearer $SUPERADMIN_TOKEN" \
  -d '{
    "findings":[
      {"severity":"critical","title":"SQL injection in /api/v1/x","description":"..."},
      {"severity":"medium","title":"Missing header","description":"..."},
      {"severity":"low","title":"Cookie flag","description":"..."}
    ]
  }' | jq '.[] | {severity, remediation_due_date}'
# [
#   {"severity": "critical", "remediation_due_date": "2026-05-08"},  # +7 days
#   {"severity": "medium",   "remediation_due_date": "2026-07-30"},  # +90 days
#   {"severity": "low",      "remediation_due_date": "2026-10-28"}   # +180 days
# ]

# Advance clock (testing only); worker surfaces overdue
curl -sf -H "Authorization: Bearer $AUDITOR_TOKEN" \
  "$PLATFORM_API_URL/api/v1/security/pentests/findings/overdue"
```

---

## Q6 — Export a SOC2 compliance evidence bundle (US6)

```bash
# After US1-US5 have produced evidence, query framework view
curl -sf -H "Authorization: Bearer $AUDITOR_TOKEN" \
  "$PLATFORM_API_URL/api/v1/security/compliance/frameworks/soc2" \
  | jq '.controls[] | {control_id, evidence_count, gap}'
# [
#   {"control_id": "CC6.1", "evidence_count": 3, "gap": false},
#   {"control_id": "CC7.1", "evidence_count": 8, "gap": false},
#   {"control_id": "CC9.1", "evidence_count": 0, "gap": true},
#   ...
# ]

# Upload manual evidence for the gap
CC91_UUID=$(curl -sf -H "Authorization: Bearer $AUDITOR_TOKEN" \
  "$PLATFORM_API_URL/api/v1/security/compliance/frameworks/soc2" \
  | jq -r '.controls[] | select(.gap == true) | .id' | head -1)

curl -sf -X POST "$PLATFORM_API_URL/api/v1/security/compliance/evidence/manual" \
  -H "Authorization: Bearer $SUPERADMIN_TOKEN" \
  -F "control_id=$CC91_UUID" \
  -F "description=Risk management policy v3.pdf" \
  -F "file=@risk-mgmt-v3.pdf"

# Export bundle for the past 90 days
BUNDLE=$(curl -sf -X POST "$PLATFORM_API_URL/api/v1/security/compliance/bundles" \
  -H "Authorization: Bearer $SUPERADMIN_TOKEN" \
  -d '{"framework":"soc2","window_start":"2026-01-23","window_end":"2026-04-23"}')
BUNDLE_URL=$(echo "$BUNDLE" | jq -r '.url')

# Download + verify signature
curl -sf "$BUNDLE_URL" -o /tmp/soc2-bundle.tar.gz
python3 tests/e2e/scripts/verify_bundle.py /tmp/soc2-bundle.tar.gz --public-key "$PUBKEY"
# ✓ Bundle signature valid
# ✓ 247 evidence artefacts hashes match
```

**Expected**: Bundle download + local hash verification passes;
signed by the same Ed25519 key as audit-chain attestations.
