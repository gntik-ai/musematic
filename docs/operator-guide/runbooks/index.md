# Runbooks

Runbooks are written for search during incidents. Each page follows Symptom, Diagnosis, Remediation, and Verification.

| Runbook | Search Keywords | Summary |
| --- | --- | --- |
| [Platform Upgrade](platform-upgrade.md) | upgrade, helm, release | Roll out a new platform version safely. |
| [Database Migration Rollback](database-migration-rollback.md) | alembic, migration, rollback | Roll back a failed database migration. |
| [Disaster Recovery Restore](disaster-recovery-restore.md) | backup, restore, disaster | Restore from object-storage-backed backups. |
| [Multi-Region Failover and Failback](multi-region-failover-failback.md) | region, failover, failback | Execute and reverse a regional failover. |
| [Secret Rotation](secret-rotation.md) | secret, vault, credential | Rotate regular or emergency secrets. |
| [OAuth Bootstrap](oauth-bootstrap.md) | oauth, bootstrap, gitops | Configure Google and GitHub OAuth at install time. |
| [OAuth Secret Rotation](oauth-secret-rotation.md) | oauth, secret, rotation | Rotate OAuth client secrets through Vault KV v2. |
| [OAuth Config Promotion](oauth-config-promotion.md) | oauth, export, import | Promote OAuth provider config without plaintext secrets. |
| [Vault Migration From Kubernetes Secrets](vault-migration-from-k8s.md) | vault, migration, kubernetes secret | Move existing Kubernetes Secrets into Vault. |
| [Vault Secret Rotation](vault-rotation.md) | vault, kv, rotation | Rotate Vault-backed KV v2 secrets. |
| [Vault Cache Flush](vault-cache-flush.md) | vault, cache, stale | Clear per-pod Vault caches after rotation. |
| [Vault Token Rotation](vault-token-rotation.md) | vault, token, lease | Force renewal during incident response. |
| [Capacity Expansion](capacity-expansion.md) | scale, node, capacity | Add worker capacity. |
| [Super Admin Break Glass](super-admin-break-glass.md) | superadmin, break-glass, recovery | Recover super admin access. |
| [Incident Response Procedures](incident-response-procedures.md) | incident, runbook, postmortem | Run the incident lifecycle. |
| [Log Query Cookbook](log-query-cookbook.md) | loki, logql, query | Query common incident patterns. |
| [TLS Emergency Renewal](tls-emergency-renewal.md) | tls, cert-manager, certificate | Renew certificates when automation fails. |
| [Notification Preferences Troubleshooting](notification-preferences-troubleshooting.md) | notifications, preferences, quiet-hours | Diagnose missing or delayed user notifications. |
| [MFA Self-Service Issues](mfa-self-service-issues.md) | mfa, backup-codes, authenticator | Resolve MFA enrollment, backup-code, and policy-disable issues. |
| [Session Revocation Incident](session-revocation-incident.md) | session, stolen-device, revoke | Revoke suspicious user sessions after compromise reports. |
| [DSR Self-Service Flow](dsr-self-service-flow.md) | dsr, gdpr, privacy | Handle self-service data subject requests. |
