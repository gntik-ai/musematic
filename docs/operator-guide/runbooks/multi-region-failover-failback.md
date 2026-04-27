# Multi-Region Failover and Failback

## Symptom

The primary region is unavailable or needs a controlled evacuation.

## Diagnosis

Check replication status, DNS health, region capacity, active maintenance windows, and the approved failover plan.

## Remediation

Execute the feature 081 failover plan through the admin route requiring super admin and 2PA. Freeze risky changes, switch traffic, verify data-plane dependencies, and keep the old primary isolated until recovery is understood.

## Verification

Confirm canonical URLs resolve to the active region, smoke-test login and workflow execution, verify alerts quiet, then rehearse failback before returning traffic.
