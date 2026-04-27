# Secret Rotation

## Symptom

A credential is expiring, exposed, or scheduled for regular rotation.

## Diagnosis

Identify consumers, secret provider path, rotation schedule, overlap window, and whether emergency skip-overlap is required.

## Remediation

Create the new secret, update the rotatable secret provider, validate reads, wait through the overlap window, then revoke the old secret. Emergency skip-overlap requires a distinct second approver.

## Verification

Check authentication or provider calls, confirm no stale secret reads in logs, and attach rotation evidence to the audit record.
