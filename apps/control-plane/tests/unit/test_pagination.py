from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import String, create_engine, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from platform.common.models.base import Base
from platform.common.pagination import (
    CursorPage,
    OffsetPage,
    apply_cursor_pagination,
    apply_offset_pagination,
    decode_cursor,
    encode_cursor,
)


class CursorModel(Base):
    __tablename__ = "cursor_models"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column()


def test_cursor_page_and_offset_page_models() -> None:
    cursor_page = CursorPage[int](items=[1, 2, 3], next_cursor="abc", has_more=True)
    offset_page = OffsetPage[str](items=["a"], total=20, page=2, page_size=5, total_pages=4)

    assert cursor_page.has_more is True
    assert offset_page.total_pages == 4


def test_encode_and_decode_cursor_roundtrip() -> None:
    value_id = uuid4()
    created_at = datetime.now(timezone.utc)

    encoded = encode_cursor(value_id, created_at)
    decoded_id, decoded_created_at = decode_cursor(encoded)

    assert decoded_id == value_id
    assert decoded_created_at == created_at


def test_apply_cursor_and_offset_pagination_modify_query() -> None:
    engine = create_engine("sqlite:///:memory:")
    CursorModel.__table__.create(engine)
    with Session(engine):
        query = select(CursorModel)
        cursor = encode_cursor(uuid4(), datetime.now(timezone.utc))
        cursor_query = apply_cursor_pagination(query, cursor, 10)
        offset_query = apply_offset_pagination(query, 2, 5)

    assert "LIMIT" in str(cursor_query)
    assert "OFFSET" in str(offset_query)
