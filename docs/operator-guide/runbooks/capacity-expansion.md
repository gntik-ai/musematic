# Capacity Expansion

## Symptom

Executions queue, pods remain pending, data stores saturate, or forecasted load exceeds available headroom.

## Diagnosis

Check node allocatable resources, pending pods, storage pressure, runtime queue latency, and cost forecasts.

## Remediation

Add worker nodes through Terraform or the managed Kubernetes node pool, then wait for cluster autoscaler and workload scheduling. For Hetzner environments, update the worker count and apply the module plan.

## Verification

Confirm new nodes are Ready, pods reschedule, queue latency drops, and dashboards show restored headroom.
