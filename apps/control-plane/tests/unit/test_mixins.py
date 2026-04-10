from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import String, create_engine, inspect
from sqlalchemy import select
from sqlalchemy.orm import Session, Mapped, mapped_column

from platform.common.models.base import Base
from platform.common.models.mixins import (
    AuditMixin,
    EventSourcedMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
    WorkspaceScopedMixin,
)


class TestModel(
    Base,
    UUIDMixin,
    TimestampMixin,
    SoftDeleteMixin,
    AuditMixin,
    WorkspaceScopedMixin,
    EventSourcedMixin,
):
    __tablename__ = "test_models"
    __test__ = False

    name: Mapped[str] = mapped_column(String, nullable=False)


def test_mixins_apply_expected_defaults() -> None:
    engine = create_engine("sqlite:///:memory:")
    TestModel.__table__.create(engine)

    with Session(engine) as session:
        record = TestModel(name="example", workspace_id=uuid4())
        session.add(record)
        session.commit()
        session.refresh(record)

        assert record.id is not None
        assert record.created_at is not None
        assert record.updated_at is not None
        assert record.created_by is None
        assert record.updated_by is None
        assert record.version == 1
        assert record.is_deleted is False
        assert record.pending_events == []


def test_soft_delete_and_timestamp_update() -> None:
    engine = create_engine("sqlite:///:memory:")
    TestModel.__table__.create(engine)

    with Session(engine) as session:
        record = TestModel(name="before", workspace_id=uuid4())
        session.add(record)
        session.commit()
        session.refresh(record)

        original_updated_at = record.updated_at
        record.name = "after"
        record.deleted_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(record)

        assert record.is_deleted is True
        assert record.updated_at >= original_updated_at


def test_workspace_id_index_exists() -> None:
    engine = create_engine("sqlite:///:memory:")
    TestModel.__table__.create(engine)

    indexes = inspect(engine).get_indexes("test_models")

    assert any("workspace_id" in index["column_names"] for index in indexes)


def test_soft_delete_query_helpers_compile() -> None:
    engine = create_engine("sqlite:///:memory:")
    TestModel.__table__.create(engine)

    query = select(TestModel).where(TestModel.is_deleted.is_(False))
    filtered = select(TestModel).where(TestModel.filter_deleted())

    assert "deleted_at" in str(query)
    assert "deleted_at" in str(filtered)
