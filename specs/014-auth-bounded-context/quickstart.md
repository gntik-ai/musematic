# Quickstart: Auth Bounded Context

**Feature**: 014-auth-bounded-context  
**Path**: `apps/control-plane/src/platform/auth/`

---

## Prerequisites

```bash
# Python 3.12+
python3 --version  # 3.12.x

# Install dependencies
cd apps/control-plane
pip install -e ".[dev]"

# Local dependencies (Docker Compose)
cd deploy/local && docker compose up -d postgres redis kafka
```

---

## Run Migrations

```bash
cd apps/control-plane
alembic upgrade head
# Should apply auth tables: user_credentials, mfa_enrollments, auth_attempts,
# password_reset_tokens, service_account_credentials, user_roles, role_permissions
```

---

## Test: Login Flow

```bash
# Start API
PLATFORM_PROFILE=api python -m entrypoints.api_main

# Create a test user (via test helper or admin script)
# Then login:
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "TestPass123"}' | python -m json.tool

# Expected: {"access_token": "eyJ...", "refresh_token": "eyJ...", "token_type": "bearer", "expires_in": 900}
```

---

## Test: Token Refresh

```bash
# Use the refresh token from login response
curl -s -X POST http://localhost:8000/api/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "eyJ..."}' | python -m json.tool

# Expected: new access_token with fresh expiry
```

---

## Test: Account Lockout

```bash
# Attempt login with wrong password 5 times
for i in {1..5}; do
  curl -s -X POST http://localhost:8000/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email": "test@example.com", "password": "WrongPass"}' | python -m json.tool
done
# 5th attempt → {"error": {"code": "ACCOUNT_LOCKED", ...}}

# Attempt with correct password while locked
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "TestPass123"}' | python -m json.tool
# Expected: 403 ACCOUNT_LOCKED
```

---

## Test: MFA Enrollment

```bash
# Login first to get access token
TOKEN="eyJ..."

# Enroll in MFA
curl -s -X POST http://localhost:8000/api/v1/auth/mfa/enroll \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool
# Expected: {"secret": "...", "provisioning_uri": "otpauth://...", "recovery_codes": [...]}

# Confirm enrollment with TOTP code from authenticator app
curl -s -X POST http://localhost:8000/api/v1/auth/mfa/confirm \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"totp_code": "123456"}' | python -m json.tool
# Expected: {"status": "active", "message": "MFA enrollment confirmed"}
```

---

## Test: MFA Login

```bash
# Login with MFA-enabled account
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "TestPass123"}' | python -m json.tool
# Expected: {"mfa_required": true, "mfa_token": "..."}

# Submit TOTP code
curl -s -X POST http://localhost:8000/api/v1/auth/mfa/verify \
  -H "Content-Type: application/json" \
  -d '{"mfa_token": "...", "totp_code": "654321"}' | python -m json.tool
# Expected: {"access_token": "...", "refresh_token": "...", ...}
```

---

## Test: RBAC Permission Check

```python
# In Python REPL or test
from src.platform.auth.service import AuthService

auth_service = AuthService(...)
result = await auth_service.check_permission(
    user_id=user_id,
    resource_type="agent",
    action="write",
    workspace_id=workspace_id,
)
assert result.allowed is True  # if user has creator/operator role
```

---

## Test: Service Account API Key

```bash
# Create service account (admin endpoint)
curl -s -X POST http://localhost:8000/api/v1/auth/service-accounts \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "ci-pipeline", "role": "service_account"}' | python -m json.tool
# Expected: {"service_account_id": "...", "name": "ci-pipeline", "api_key": "msk_...", "role": "service_account"}

# Use API key
curl -s http://localhost:8000/api/v1/some-endpoint \
  -H "X-API-Key: msk_..." | python -m json.tool
# Expected: authenticated response
```

---

## Test: Logout

```bash
# Logout current session
curl -s -X POST http://localhost:8000/api/v1/auth/logout \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool
# Expected: {"message": "Session terminated"}

# Logout all sessions
curl -s -X POST http://localhost:8000/api/v1/auth/logout-all \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool
# Expected: {"message": "All sessions terminated", "sessions_revoked": 3}
```

---

## Run All Tests

```bash
cd apps/control-plane
pytest tests/unit/test_auth*.py tests/integration/test_auth*.py -v --cov=src/platform/auth --cov-report=term-missing
# Must be >= 95% coverage
```
