# Quickstart: API Governance and Developer Experience

**Feature**: 073-api-governance-dx
**Date**: 2026-04-23

These walkthroughs use the local dev harness exposed by `make dev-up`. That
target reuses the repository's kind-based E2E stack, so the full platform, the
mock Google OIDC server, and the mock GitHub OAuth server are available
locally without ad-hoc bootstrapping.

## Boot the local environment

```bash
# Full local platform on kind
make dev-up

# Control plane API and docs
export PLATFORM_API_URL=http://localhost:8081
export PLATFORM_UI_URL=http://localhost:8080
export PLATFORM_WS_URL=ws://localhost:8082

# Mock identity providers used by the walkthroughs
export MOCK_GOOGLE_OIDC_URL=http://localhost:8083
export MOCK_GITHUB_OAUTH_URL=http://localhost:8084

# One-time OAuth provider bootstrap for the dev harness
python3 tests/e2e/scripts/dev_auth.py bootstrap-providers --api-base "$PLATFORM_API_URL"

# Ensure the bootstrap admin exists as a real user, then mint a platform_admin
# token with that persisted subject so admin audit/debug endpoints satisfy FKs.
export ADMIN_BOOTSTRAP_TOKEN="$(python3 tests/e2e/scripts/dev_auth.py oauth --provider google --login j-admin --api-base "$PLATFORM_API_URL" --mock-base "$MOCK_GOOGLE_OIDC_URL")"
export ADMIN_SUB="$(python3 tests/e2e/scripts/dev_auth.py decode --token "$ADMIN_BOOTSTRAP_TOKEN" --field sub)"
export ADMIN_TOKEN="$(python3 tests/e2e/scripts/dev_auth.py mint --email j-admin@e2e.test --user-id "$ADMIN_SUB" --role platform_admin)"
export CREATOR_TOKEN="$(python3 tests/e2e/scripts/dev_auth.py oauth --provider github --login j-creator-gh --api-base "$PLATFORM_API_URL" --mock-base "$MOCK_GITHUB_OAUTH_URL")"
export CONSUMER_TOKEN="$(python3 tests/e2e/scripts/dev_auth.py oauth --provider google --login j-consumer --api-base "$PLATFORM_API_URL" --mock-base "$MOCK_GOOGLE_OIDC_URL")"
```

Teardown when finished:

```bash
make dev-down
```

---

## Q1 — Fetch the OpenAPI document and browse Swagger UI (US1)

```bash
# Fetch the published OpenAPI document
curl -sf "$PLATFORM_API_URL/api/openapi.json" | jq '.info'
# {
#   "title": "musematic Control Plane API",
#   "version": "1.4.0",
#   "contact": { "name": "musematic platform", "email": "..." }
# }

# Quick smoke-check: the document is valid JSON and contains paths
curl -sf "$PLATFORM_API_URL/api/openapi.json" | jq '.paths | length'
# > 0

# Open Swagger UI
open "$PLATFORM_API_URL/api/docs"

# Open Redoc
open "$PLATFORM_API_URL/api/redoc"
```

**Expected**: The document enumerates every bounded context under its tag
(auth, registry, workflows, execution, …); admin paths carry the
`admin` tag in addition. Every non-exempt operation declares a
`security` requirement. The CI lint gate in `.github/workflows/ci.yml`
remains the canonical Spectral check.

---

## Q2 — Generate a local SDK from the live OpenAPI document (US2)

Local verification focuses on code generation against the published live
document. Registry publication itself is exercised by
`.github/workflows/sdks.yml`.

```bash
python3 -m venv /tmp/musematic-sdk-venv
/tmp/musematic-sdk-venv/bin/pip install --upgrade pip
/tmp/musematic-sdk-venv/bin/pip install "openapi-python-client==0.21.*" "click<8.2"

/tmp/musematic-sdk-venv/bin/openapi-python-client generate \
  --url "$PLATFORM_API_URL/api/openapi.json" \
  --output-path /tmp/musematic-python-sdk \
  --overwrite \
  --meta none

PLATFORM_API_URL="$PLATFORM_API_URL" CREATOR_TOKEN="$CREATOR_TOKEN" /tmp/musematic-sdk-venv/bin/python - <<'PY'
import os
import sys
from pathlib import Path

root = Path("/tmp/musematic-python-sdk")
sys.path.insert(0, str(root))
from client import AuthenticatedClient

client = AuthenticatedClient(
    base_url=os.environ["PLATFORM_API_URL"],
    token=os.environ["CREATOR_TOKEN"],
)
response = client.get_httpx_client().get("/api/v1/workspaces")
print(response.status_code)
print(response.json())
PY
```

**Expected**: Code generation completes against the live OpenAPI document and
writes the client tree to `/tmp/musematic-python-sdk`. The generator currently
emits non-fatal warnings for a handful of duplicate schema names in the live
document, but it still produces a usable client tree. Importing
`AuthenticatedClient` from the generated root and making an authenticated
round-trip call against the live platform succeeds. Release-time publication to
PyPI, npm, GitHub releases, and crates.io is covered by `sdks.yml`.

---

## Q3 — Trigger a 429 and observe headers (US3)

```bash
# Default tier = 300 RPM. Hammer 305 requests.
for i in $(seq 1 305); do
  status=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $CONSUMER_TOKEN" \
    "$PLATFORM_API_URL/api/v1/workspaces")
  if [ "$status" = "429" ]; then
    echo "Got 429 at request $i"
    curl -sI -H "Authorization: Bearer $CONSUMER_TOKEN" \
      "$PLATFORM_API_URL/api/v1/workspaces" | grep -iE 'retry-after|x-ratelimit'
    break
  fi
done
```

**Expected**:

```text
Got 429 at request 301
Retry-After: <seconds>
X-RateLimit-Limit: 300
X-RateLimit-Remaining: 0
X-RateLimit-Reset: <epoch-seconds>
```

Wait 60 seconds and retry:

```bash
sleep 60
curl -sI -H "Authorization: Bearer $CONSUMER_TOKEN" \
  "$PLATFORM_API_URL/api/v1/workspaces" | head -3
# HTTP/1.1 200 OK
```

---

## Q4 — Smoke-test deprecation headers and 410 behaviour (US4)

The default dev harness does not ship a permanently deprecated live route, so
local verification uses the integration smoke test that exercises the
middleware contract end-to-end in-process.

```bash
cd apps/control-plane
.venv/bin/python -m pytest \
  tests/integration/common/test_versioning_e2e.py \
  -q \
  -m integration \
  --run-integration
# 2 passed
```

**Expected**: One test verifies `Deprecation`, `Sunset`, and successor `Link`
headers before the sunset date; the second verifies HTTP 410 after the
sunset date. The same middleware is what the live platform uses.

---

## Q5 — Open a debug logging session and capture an interaction (US5)

```bash
# Use a principal that has not just exhausted the Q3 rate-limit window.
export TARGET_USER_ID="$(python3 tests/e2e/scripts/dev_auth.py decode --token "$CREATOR_TOKEN" --field sub)"

# Open a 30-minute session as platform_admin
SESSION=$(curl -sf -X POST \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"target_type":"user","target_id":"'"$TARGET_USER_ID"'","justification":"investigating reported login issue TKT-1234","duration_minutes":30}' \
  "$PLATFORM_API_URL/api/v1/admin/debug-logging/sessions")
SESSION_ID=$(echo "$SESSION" | jq -r '.session_id')
echo "Opened $SESSION_ID"

# The target user makes a request while the session is active
curl -s -H "Authorization: Bearer $CREATOR_TOKEN" \
  "$PLATFORM_API_URL/api/v1/workspaces" >/dev/null

# Fetch captures
curl -sf -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$PLATFORM_API_URL/api/v1/admin/debug-logging/sessions/${SESSION_ID}/captures" \
  | jq '.items[0] | {method, path, response_status, duration_ms}'

# Authorization is redacted
curl -sf -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$PLATFORM_API_URL/api/v1/admin/debug-logging/sessions/${SESSION_ID}/captures" \
  | jq '.items[0].request_headers.authorization'
# "[REDACTED]"

# Close the session early
curl -si -X DELETE -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$PLATFORM_API_URL/api/v1/admin/debug-logging/sessions/${SESSION_ID}" | head -1
# HTTP/1.1 204 No Content
```

**Expected**: The session is visible with its justification, capture count,
and terminated timestamp. Captured request headers remain redacted and no
new captures are written after the session is closed.

---

## Verifying the build

Local lint gate:

```bash
cd apps/control-plane
python -c "from platform.main import create_app; import json; print(json.dumps(create_app().openapi()))" \
  > /tmp/openapi.json
# Optional local lint when Spectral CLI is installed:
# spectral lint /tmp/openapi.json --fail-on=error
```

SDK release dry-run (GitHub Actions):

```bash
gh workflow run sdks.yml -f release_tag=v1.4.0-rc.1
gh run watch
```
