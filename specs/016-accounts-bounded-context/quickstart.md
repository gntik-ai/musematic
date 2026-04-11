# Quickstart: Accounts Bounded Context

**Feature**: 016-accounts-bounded-context  
**Date**: 2026-04-11

---

## Prerequisites

- Control plane running (feature 013 FastAPI scaffold)
- Auth bounded context running (feature 014)
- PostgreSQL 16+ available with `accounts_` tables migrated
- Kafka `accounts.events` topic created
- Redis available (for rate limiting)

---

## Run Migration

```bash
cd apps/control-plane
alembic upgrade head
# Verify: accounts_users, accounts_email_verifications, accounts_invitations, accounts_approval_requests tables exist
```

---

## Environment Variables

```bash
# Minimum required
ACCOUNTS_SIGNUP_MODE=open                  # open | invite_only | admin_approval
ACCOUNTS_EMAIL_VERIFY_TTL_HOURS=24
ACCOUNTS_INVITE_TTL_DAYS=7
ACCOUNTS_RESEND_RATE_LIMIT=3
```

---

## Test: Registration and Email Verification (Open Mode)

```bash
# 1. Register a new user
curl -X POST http://localhost:8000/api/v1/accounts/register \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "display_name": "Test User", "password": "SecureP@ssw0rd!"}'
# Expected: 202 with anti-enumeration message

# 2. Retrieve the verification token from DB (test only):
psql -c "SELECT token_hash FROM accounts_email_verifications WHERE user_id = (SELECT id FROM accounts_users WHERE email = 'test@example.com');"
# Note: in tests, use the repository to get the plaintext token from a test helper

# 3. Verify email (use plaintext token from notification service mock)
curl -X POST http://localhost:8000/api/v1/accounts/verify-email \
  -H "Content-Type: application/json" \
  -d '{"token": "<plaintext_token>"}'
# Expected: 200 with status "active"

# 4. Verify accounts.user.activated event was emitted on Kafka accounts.events topic
# Use kafkacat or test consumer
```

---

## Test: Admin Approval Mode

```bash
# 1. Set signup mode
export ACCOUNTS_SIGNUP_MODE=admin_approval

# 2. Register and verify email (same as above)
# After verification: status should be "pending_approval"

# 3. Get admin JWT token (from auth bounded context)
# See feature 014 quickstart.md for login instructions

# 4. View pending approvals
curl -X GET http://localhost:8000/api/v1/accounts/pending-approvals \
  -H "Authorization: Bearer <admin_token>"
# Expected: user appears in items list

# 5. Approve user
curl -X POST http://localhost:8000/api/v1/accounts/<user_id>/approve \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Approved"}'
# Expected: 200 with status "active"

# 6. Verify accounts.user.approved and accounts.user.activated events on Kafka
```

---

## Test: Invitation Flow

```bash
# 1. Create an invitation (as admin)
curl -X POST http://localhost:8000/api/v1/accounts/invitations \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"email": "invited@example.com", "roles": ["workspace_editor"]}'
# Expected: 201 with invitation details

# 2. Get invitation token from DB (test only)
psql -c "SELECT token_hash FROM accounts_invitations WHERE invitee_email = 'invited@example.com';"

# 3. View invitation details (as invitee — no auth)
curl http://localhost:8000/api/v1/accounts/invitations/<token>
# Expected: invitee_email, roles, expires_at

# 4. Accept invitation
curl -X POST http://localhost:8000/api/v1/accounts/invitations/<token>/accept \
  -H "Content-Type: application/json" \
  -d '{"token": "<token>", "display_name": "Invited User", "password": "SecureP@ssw0rd!"}'
# Expected: 201 with status "active"
```

---

## Test: Admin Lifecycle Actions

```bash
# Suspend a user
curl -X POST http://localhost:8000/api/v1/accounts/<user_id>/suspend \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Security review"}'
# Expected: 200 with status "suspended"

# Verify suspended user cannot log in (via auth bounded context)
# See feature 014 quickstart.md for login test

# Reactivate
curl -X POST http://localhost:8000/api/v1/accounts/<user_id>/reactivate \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{}'
# Expected: 200 with status "active"

# Reset MFA
curl -X POST http://localhost:8000/api/v1/accounts/<user_id>/reset-mfa \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{}'
# Expected: 200 with mfa_cleared: true
```

---

## Test: Anti-Enumeration

```bash
# Register with existing email — should get same 202 response as a new registration
curl -X POST http://localhost:8000/api/v1/accounts/register \
  -H "Content-Type: application/json" \
  -d '{"email": "existing@example.com", "display_name": "Test", "password": "SecureP@ssw0rd!"}'
# Expected: 202 (identical to new registration) — NOT 409

# Resend verification for non-existent email — same 202 response
curl -X POST http://localhost:8000/api/v1/accounts/resend-verification \
  -H "Content-Type: application/json" \
  -d '{"email": "doesnotexist@example.com"}'
# Expected: 202
```

---

## Run Tests

```bash
cd apps/control-plane

# Unit tests
pytest tests/unit/test_accounts_*.py -v

# Integration tests
pytest tests/integration/test_*accounts*.py -v

# Coverage (must be ≥95%)
pytest tests/ --cov=src/platform/accounts --cov-report=term-missing

# Lint + type check
ruff check src/platform/accounts/
mypy src/platform/accounts/ --strict
```
