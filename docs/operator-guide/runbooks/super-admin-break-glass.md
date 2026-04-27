# Super Admin Break Glass

## Symptom

No super admin can access the platform or global recovery action is required.

## Diagnosis

Confirm the lockout cause, affected accounts, emergency authorization, and whether normal reset flows are unavailable.

## Remediation

Use the FR-579 recovery path through `platform-cli superadmin recover`. Supply the emergency key file from the sealed operator location and record the reason.

## Verification

Confirm one super admin can log in, rotate the emergency credential, notify existing super admins, and review audit events `platform.superadmin.break_glass_recovery` or `platform.superadmin.force_reset`.
