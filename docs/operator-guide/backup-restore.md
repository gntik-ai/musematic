# Backup and Restore

Backups cover PostgreSQL, object storage, and data stores according to the feature 048 contracts. Operators should verify backup presence, age, checksum, encryption, and restore drill history.

Before restore, decide whether the incident requires point-in-time database recovery, object-store restore, or full environment rebuild. Preserve the failed state for forensics where possible.

After restore, run smoke tests, verify audit-chain continuity where applicable, and document the recovery point and recovery time achieved.
