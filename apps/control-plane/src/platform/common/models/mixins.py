from __future__ import annotations

import uuid
from datetime import UTC, datetime
from platform.common.models.base import Base
from typing import Any
from uuid import UUID

from sqlalchemy import UUID as SQLUUID
from sqlalchemy import DateTime, Integer, event, func, text
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


def _utcnow() -> datetime:
    return datetime.now(UTC)


class UUIDMixin:
    id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=_utcnow,
    )


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @hybrid_property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @is_deleted.inplace.expression
    @classmethod
    def _is_deleted_expression(cls) -> Any:
        return cls.deleted_at.is_not(None)

    @classmethod
    def filter_deleted(cls) -> Any:
        return cls.deleted_at.is_(None)


class AuditMixin:
    created_by: Mapped[UUID | None] = mapped_column(SQLUUID(as_uuid=True), nullable=True)
    updated_by: Mapped[UUID | None] = mapped_column(SQLUUID(as_uuid=True), nullable=True)


class WorkspaceScopedMixin:
    workspace_id: Mapped[UUID] = mapped_column(SQLUUID(as_uuid=True), nullable=False, index=True)


def _current_tenant_id() -> UUID:
    from platform.common.tenant_context import current_tenant
    from platform.tenants.seeder import DEFAULT_TENANT_ID

    tenant = current_tenant.get(None)
    return tenant.id if tenant is not None else DEFAULT_TENANT_ID


class TenantScopedMixin:
    tenant_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        nullable=False,
        default=_current_tenant_id,
        server_default=text("'00000000-0000-0000-0000-000000000001'::uuid"),
    )


class EventSourcedMixin:
    pending_events: list[Any]
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    @declared_attr.directive
    def __mapper_args__(cls) -> dict[str, Any]:  # noqa: N805
        return {"version_id_col": cls.version}


@event.listens_for(Base, "init", propagate=True)
def _init_pending_events(target: Any, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
    del args, kwargs
    if isinstance(target, EventSourcedMixin):
        target.pending_events = []
