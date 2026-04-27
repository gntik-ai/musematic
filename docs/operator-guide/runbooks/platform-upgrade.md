# Platform Upgrade

## Symptom

Operators need to deploy a new Musematic release or patch version.

## Diagnosis

Read the release notes, breaking-change inventory, migration notes, and chart diff. Confirm no active incident or maintenance freeze blocks rollout.

## Remediation

Run a rolling Helm upgrade with `--wait`, apply database migrations first when the release notes require it, and keep the previous chart values available for rollback.

```bash
helm upgrade musematic deploy/helm/platform --namespace platform --wait
```

## Verification

Run `platform-cli observability status`, smoke-test login and workflow execution, confirm pods are ready, and watch error-rate dashboards for one release window.
