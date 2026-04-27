# Runbooks

Runbooks are written for search during incidents. Each page follows Symptom, Diagnosis, Remediation, and Verification.

| Runbook | Search Keywords | Summary |
| --- | --- | --- |
| [Platform Upgrade](platform-upgrade.md) | upgrade, helm, release | Roll out a new platform version safely. |
| [Database Migration Rollback](database-migration-rollback.md) | alembic, migration, rollback | Roll back a failed database migration. |
| [Disaster Recovery Restore](disaster-recovery-restore.md) | backup, restore, disaster | Restore from object-storage-backed backups. |
| [Multi-Region Failover and Failback](multi-region-failover-failback.md) | region, failover, failback | Execute and reverse a regional failover. |
| [Secret Rotation](secret-rotation.md) | secret, vault, credential | Rotate regular or emergency secrets. |
| [Capacity Expansion](capacity-expansion.md) | scale, node, capacity | Add worker capacity. |
| [Super Admin Break Glass](super-admin-break-glass.md) | superadmin, break-glass, recovery | Recover super admin access. |
| [Incident Response Procedures](incident-response-procedures.md) | incident, runbook, postmortem | Run the incident lifecycle. |
| [Log Query Cookbook](log-query-cookbook.md) | loki, logql, query | Query common incident patterns. |
| [TLS Emergency Renewal](tls-emergency-renewal.md) | tls, cert-manager, certificate | Renew certificates when automation fails. |
