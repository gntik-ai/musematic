from __future__ import annotations

from datetime import datetime
from platform.common.models.base import Base
from platform.common.models.mixins import TenantScopedMixin, UUIDMixin
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column


class IncidentIntegration(Base, TenantScopedMixin, UUIDMixin):
    __tablename__ = "incident_integrations"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "integration_key_ref",
            name="uq_incident_integrations_provider_key_ref",
        ),
        CheckConstraint(
            "provider IN ('pagerduty','opsgenie','victorops')",
            name="ck_incident_integrations_provider",
        ),
    )

    provider: Mapped[str] = mapped_column(String(length=32), nullable=False)
    integration_key_ref: Mapped[str] = mapped_column(String(length=512), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    alert_severity_mapping: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Incident(Base, TenantScopedMixin, UUIDMixin):
    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('critical','high','warning','info')",
            name="ck_incidents_severity",
        ),
        CheckConstraint(
            "status IN ('open','acknowledged','resolved','auto_resolved')",
            name="ck_incidents_status",
        ),
        Index("ix_incidents_condition_fingerprint", "condition_fingerprint"),
        Index(
            "ix_incidents_open_fingerprint",
            "condition_fingerprint",
            postgresql_where=text("status IN ('open','acknowledged')"),
        ),
        Index("ix_incidents_triggered_at_desc", text("triggered_at DESC")),
        Index("ix_incidents_related_executions_gin", "related_executions", postgresql_using="gin"),
    )

    condition_fingerprint: Mapped[str] = mapped_column(String(length=512), nullable=False)
    severity: Mapped[str] = mapped_column(String(length=16), nullable=False)
    status: Mapped[str] = mapped_column(String(length=32), nullable=False, default="open")
    title: Mapped[str] = mapped_column(String(length=512), nullable=False)
    description: Mapped[str] = mapped_column(Text(), nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    related_executions: Mapped[list[UUID]] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True)),
        nullable=False,
        default=list,
    )
    related_event_ids: Mapped[list[UUID]] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True)),
        nullable=False,
        default=list,
    )
    runbook_scenario: Mapped[str | None] = mapped_column(String(length=256), nullable=True)
    alert_rule_class: Mapped[str] = mapped_column(String(length=128), nullable=False)
    post_mortem_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("post_mortems.id", ondelete="SET NULL"),
        nullable=True,
    )


class IncidentExternalAlert(Base, TenantScopedMixin, UUIDMixin):
    __tablename__ = "incident_external_alerts"
    __table_args__ = (
        UniqueConstraint(
            "incident_id",
            "integration_id",
            name="uq_incident_external_alert_incident_integration",
        ),
        CheckConstraint(
            "delivery_status IN ('pending','delivered','failed','resolved')",
            name="ck_incident_external_alerts_status",
        ),
        Index(
            "ix_incident_external_alerts_next_retry_pending",
            "next_retry_at",
            postgresql_where=text("delivery_status = 'pending'"),
        ),
    )

    incident_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
    )
    integration_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("incident_integrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider_reference: Mapped[str | None] = mapped_column(String(length=512), nullable=True)
    delivery_status: Mapped[str] = mapped_column(
        String(length=32),
        nullable=False,
        default="pending",
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text(), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Runbook(Base, TenantScopedMixin, UUIDMixin):
    __tablename__ = "runbooks"
    __table_args__ = (
        UniqueConstraint("scenario", name="uq_runbooks_scenario"),
        CheckConstraint("status IN ('active','retired')", name="ck_runbooks_status"),
        CheckConstraint("length(symptoms) > 0", name="ck_runbooks_symptoms_nonempty"),
        CheckConstraint(
            "length(remediation_steps) > 0",
            name="ck_runbooks_remediation_nonempty",
        ),
        CheckConstraint(
            "length(escalation_path) > 0",
            name="ck_runbooks_escalation_nonempty",
        ),
    )

    scenario: Mapped[str] = mapped_column(String(length=256), nullable=False)
    title: Mapped[str] = mapped_column(String(length=256), nullable=False)
    symptoms: Mapped[str] = mapped_column(Text(), nullable=False)
    diagnostic_commands: Mapped[list[dict[str, str]]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=list,
    )
    remediation_steps: Mapped[str] = mapped_column(Text(), nullable=False)
    escalation_path: Mapped[str] = mapped_column(Text(), nullable=False)
    status: Mapped[str] = mapped_column(String(length=16), nullable=False, default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    updated_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


class PostMortem(Base, TenantScopedMixin, UUIDMixin):
    __tablename__ = "post_mortems"
    __table_args__ = (
        UniqueConstraint("incident_id", name="uq_post_mortems_incident_id"),
        CheckConstraint(
            "status IN ('draft','published','distributed')",
            name="ck_post_mortems_status",
        ),
        Index(
            "ix_post_mortems_linked_certifications_gin",
            "linked_certification_ids",
            postgresql_using="gin",
        ),
    )

    incident_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(length=32), nullable=False, default="draft")
    timeline: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB(none_as_null=False),
        nullable=True,
    )
    timeline_blob_ref: Mapped[str | None] = mapped_column(String(length=1024), nullable=True)
    timeline_source_coverage: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )
    impact_assessment: Mapped[str | None] = mapped_column(Text(), nullable=True)
    root_cause: Mapped[str | None] = mapped_column(Text(), nullable=True)
    action_items: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB(none_as_null=False),
        nullable=True,
    )
    distribution_list: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB(none_as_null=False),
        nullable=True,
    )
    linked_certification_ids: Mapped[list[UUID]] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True)),
        nullable=False,
        default=list,
    )
    blameless: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    created_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    distributed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
