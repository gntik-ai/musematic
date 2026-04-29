# Threat Model: Administrator Workbench

## 2PA Replay, Race, And Expiry

| Vector | Attacker model | Impact | Mitigation |
|---|---|---|---|
| Replay an approved token | Admin with access to old request token | Re-execute critical action | `TwoPersonAuthService.validate_token()` re-reads the request and consumes it transactionally at apply time. |
| Approve own request | Compromised single super admin | Bypass two-person control | Service rejects approver equal to initiator. E2E asserts the rejection. |
| Race two applies against one token | Two clients sharing token | Duplicate failover/config action | Partial unique index on unconsumed request plus transactional consume. |
| Use expired request | Slow operator or captured token | Execute stale critical action | Expiry checked during validate; scanner is cleanup only, not the authority. |

## Impersonation Abuse

| Vector | Attacker model | Impact | Mitigation |
|---|---|---|---|
| Start without justification | Curious super admin | Ambiguous audit trail | API enforces justification length >= 20 chars; UI validates before submit. |
| Nested impersonation | Super admin already acting as user | Confusing principal chain | Service rejects an active second impersonation. |
| Impersonate another super admin | Malicious super admin | Privilege laundering | Requires 2PA token for super-admin target. |
| Hide banner client-side | User with DOM control | Reduced user awareness | Audit context is server-side source of truth; banner is UX only. |

## Bootstrap Secret Leakage

| Vector | Attacker model | Impact | Mitigation |
|---|---|---|---|
| Log password env var | Log reader | Super admin credential exposure | Static check `lint_bootstrap_secrets.py`; no logger call may reference secret variable names. |
| Conflict password and password file | Misconfigured GitOps values | Ambiguous credential source | Bootstrap fails fast before any user write. |
| Generated password repeated | Operator reruns install | Credential disclosure | Generated password is printed exactly once and bootstrap is idempotent. |
| Force reset in production | Insider with chart access | Takeover of super admin | Production reset requires `ALLOW_SUPERADMIN_RESET=true` plus critical audit and notifications. |

## Read-Only Bypass

| Vector | Attacker model | Impact | Mitigation |
|---|---|---|---|
| Re-enable button via browser devtools | Admin in read-only session | Unauthorized write | `AdminReadOnlyMiddleware` blocks non-GET `/api/v1/admin/*` server-side. |
| Direct curl with session cookie | Scripted admin request | Unauthorized write | Same middleware evaluates request method and session flag. |
| Initiate 2PA while read-only | Admin tries delayed write | Critical write path opened | Read-only middleware blocks request creation. |
| Stale local UI state | Browser state out of sync | Confusing disabled controls | Server-side block remains authoritative; UI reads session mode as defense in depth. |

## Review Notes

Security review must re-check 2PA token consume semantics, audit-chain payloads for dual principals, and all bootstrap logging paths before merge.
