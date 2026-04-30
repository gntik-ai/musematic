# UPD-042 Secret Leak Verification

Status: blocked pending live 24-hour synthetic-load run.

## Required Procedure

Run the canonical secret-leak regex set against `kubectl logs` for control-plane pods after synthetic API-key creation, MFA enrollment, DSR submission, and consent revocation flows have run for 24 hours.

Required sample command shape:

```sh
kubectl logs -n platform -l app.kubernetes.io/name=control-plane --since=24h \
  | python scripts/check-log-secret-leaks.py
```

## Scope

The scan must cover:

- Personal API key creation and one-time display.
- MFA enrollment setup keys.
- MFA backup-code regeneration.
- DSR submission payloads.
- Consent revocation.
- Session revocation.

## Current Workspace Result

Not executed in this workspace because there is no running 24-hour synthetic workload or Kubernetes log source attached to this session.

Local static coverage was completed on 2026-04-30:

- `python scripts/check-secret-access.py` passed with zero direct secret-access violations.

This does not replace the required SC-014 24-hour `kubectl logs` scan.
