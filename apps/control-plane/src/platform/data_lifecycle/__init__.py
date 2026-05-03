"""UPD-051 — Data Lifecycle bounded context.

Owns workspace-scoped and tenant-scoped data export, two-phase deletion with
grace, DPA management, sub-processors public list, GDPR Article 28 evidence,
and 30-day backup-purge separation.

Cross-store cascade is delegated to
``privacy_compliance.services.cascade_orchestrator``. Audit emission is
delegated to ``audit.service.AuditChainService``.
"""
