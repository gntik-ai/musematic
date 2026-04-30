# MFA Self-Service Issues

Use this runbook for FR-653 issues on `/settings/security/mfa`: enrollment failures, lost backup codes, backup-code regeneration, or disable requests refused by policy.

## Symptom

- The QR code or setup key does not enroll in the user's authenticator app.
- The confirmation code is refused.
- The user lost backup codes.
- The user cannot disable MFA because administrative policy requires it.

## Diagnosis

1. Confirm the user is authenticated and using the current `/api/v1/auth/mfa/enroll` and `/api/v1/auth/mfa/confirm` flow.
2. Check device clock skew. TOTP verification is time sensitive.
3. Review `auth.mfa.enrolled`, `auth.mfa.disabled`, and `auth.mfa.recovery_codes_regenerated` audit events.
4. Check whether signup or admin policy enforces MFA for the user's role. If enforced, disable must return 403.

## Remediation

1. If enrollment fails, restart the enrollment flow and use the text setup key as a fallback.
2. If codes are lost but the user still has authenticator access, use "Regenerate backup codes" and require TOTP step-up.
3. If the user lost both authenticator and backup codes, use the approved password-recovery and admin-assisted MFA reset path.
4. If policy enforces MFA, do not bypass it. Explain that MFA is administrator-enforced and cannot be disabled self-service.

## Verification

- The user can complete sign-in with an authenticator code.
- Newly generated backup codes are shown once and old unused backup codes no longer work.
- `auth.mfa.recovery_codes_regenerated` or `auth.mfa.disabled` is visible in the audit chain when those actions succeed.
