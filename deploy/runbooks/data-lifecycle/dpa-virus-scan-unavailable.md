# DPA virus-scan unavailable

## Symptom

Super-admin attempts a DPA upload. The UI shows `503 dpa_scan_unavailable`. Audit chain has `data_lifecycle.dpa_scan_unavailable` entries. The Grafana dashboard `Data Lifecycle - UPD-051` shows non-zero `data_lifecycle_dpa_scan_unavailable_total` rate.

## Diagnosis

1. Verify the ClamAV pod is running:

   ```bash
   kubectl get pods -n platform-data -l app=clamav
   ```

2. Test the daemon socket from the control-plane pod:

   ```bash
   kubectl exec -n platform deploy/control-plane -- nc -zv clamav.platform-data 3310
   ```

3. Check the daemon logs:

   ```bash
   kubectl logs -n platform-data deploy/clamav --tail 100
   ```

   Common failure modes:
   - `freshclam` failed to download the latest signature database (expired definitions). The daemon refuses scans once the signature DB ages beyond the threshold.
   - PVC for the signature DB is full.
   - Memory limit exceeded — large PDFs spike RSS.

## Recovery

### Signature database stale

```bash
kubectl exec -n platform-data deploy/clamav -- freshclam
kubectl rollout restart -n platform-data deploy/clamav
```

If `freshclam` reports a network error, verify outbound DNS+HTTPS to `database.clamav.net` is allowed by the cluster network policy. The ClamAV chart includes a `NetworkPolicy` that allows `database.clamav.net:443` egress by default; if it has been overridden, restore.

### PVC full

```bash
kubectl get pvc -n platform-data | grep clamav
# If usage > 90%:
kubectl exec -n platform-data deploy/clamav -- du -sh /var/lib/clamav/*
# Old signature snapshots can be safely cleaned:
kubectl exec -n platform-data deploy/clamav -- find /var/lib/clamav -name "*.cld.old" -delete
```

If signatures themselves fill the PVC, scale the volume by editing the chart's `dataVolumeClaim.size` and rolling.

### Memory pressure

```bash
kubectl top pod -n platform-data -l app=clamav
```

Bump the deployment's `resources.limits.memory` if RSS spikes during scanning. The default 1Gi is sufficient for the 50 MB DPA cap.

## Bypass for time-critical uploads

**Do NOT bypass the scan lightly.** In an extreme outage, set `DATA_LIFECYCLE_CLAMAV_HOST=""` and roll the control-plane Deployment. The DPA service will log a structured `data_lifecycle.dpa_scan_skipped_no_clamav` warning and accept uploads without scanning. Enable a temporary out-of-band manual review of uploaded files. Restore the env var as soon as ClamAV is healthy again.

## Prevention

- Add a Prometheus alert: `data_lifecycle_dpa_scan_unavailable_total > 0 over 10 min` -> page the data-lifecycle on-call.
- Pin the ClamAV chart's `freshclam` cron to a sensible schedule (default daily). If your environment caches signatures aggressively, set it more frequently to avoid the stale-DB failure mode.
