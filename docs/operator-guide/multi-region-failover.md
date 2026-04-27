# Multi-Region Failover

Multi-region operations are controlled by feature 081. Application logic refuses active-active mode, and failover uses audited plans with two-person approval for production execution.

Operators rehearse failover before production use, confirm replication health, freeze risky changes, execute the plan, verify canonical URLs, then follow the failback procedure when the primary region is healthy.

Use the [multi-region failover runbook](runbooks/multi-region-failover-failback.md) for step-by-step execution.
