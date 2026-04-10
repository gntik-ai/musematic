from __future__ import annotations

import base64
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import Select, literal, tuple_

T = TypeVar("T")


class CursorPage(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None
    has_more: bool = False


class OffsetPage(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int


def encode_cursor(item_id: UUID, created_at: datetime) -> str:
    payload = f"{item_id}|{created_at.astimezone(UTC).isoformat()}".encode()
    return base64.urlsafe_b64encode(payload).decode("utf-8")


def decode_cursor(cursor: str) -> tuple[UUID, datetime]:
    raw = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
    raw_id, raw_created_at = raw.split("|", 1)
    return UUID(raw_id), datetime.fromisoformat(raw_created_at)


def apply_cursor_pagination(query: Select[Any], cursor: str | None, page_size: int) -> Select[Any]:
    entity = query.column_descriptions[0]["entity"]
    created_at_column = entity.created_at
    id_column = entity.id
    if cursor:
        cursor_id, cursor_created_at = decode_cursor(cursor)
        query = query.where(
            tuple_(created_at_column, id_column)
            > tuple_(literal(cursor_created_at), literal(cursor_id))
        )
    return query.order_by(created_at_column, id_column).limit(page_size + 1)


def apply_offset_pagination(query: Select[Any], page: int, page_size: int) -> Select[Any]:
    return query.offset((page - 1) * page_size).limit(page_size)
