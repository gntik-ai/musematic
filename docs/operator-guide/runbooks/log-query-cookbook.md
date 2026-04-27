# Log Query Cookbook

## Symptom

An incident needs fast log inspection by service, GID, or correlation ID.

## Diagnosis

Start with a narrow time range and a known identifier. Avoid broad cluster-wide searches until the likely namespace is known.

## Remediation

Use the [LogQL Cookbook](../logql-cookbook.md) and preserve useful queries in the incident timeline.

## Verification

Confirm the query returns expected recent logs, then cross-check the same event in traces or audit records.
