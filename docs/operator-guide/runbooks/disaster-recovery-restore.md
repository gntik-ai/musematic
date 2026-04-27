# Disaster Recovery Restore

## Symptom

Primary data is unavailable, corrupted, or lost beyond normal failover recovery.

## Diagnosis

Confirm the blast radius, latest usable backup, object storage integrity, encryption material, and target recovery point.

## Remediation

Restore PostgreSQL and object-store artifacts according to the feature 048 backup manifest. Restore dependent stores only after confirming they are consistent with the selected recovery point.

## Verification

Run smoke tests, verify user login, run a sample workflow, inspect audit-chain continuity, and record achieved RPO/RTO in the incident timeline.
