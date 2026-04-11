from __future__ import annotations

from platform.ws_hub.connection import ConnectionRegistry
from uuid import uuid4

import pytest

from tests.ws_hub_support import build_connection


def test_connection_registry_crud_operations() -> None:
    registry = ConnectionRegistry()
    user_id = uuid4()
    conn = build_connection(user_id=user_id)

    registry.add(conn)

    assert registry.get(conn.connection_id) is conn
    assert registry.get_by_user_id(user_id) == [conn]
    assert registry.all() == [conn]
    assert registry.count() == 1
    assert registry.remove(conn.connection_id) is conn
    assert registry.get(conn.connection_id) is None
    assert registry.count() == 0


def test_connection_registry_duplicate_add_raises() -> None:
    registry = ConnectionRegistry()
    conn = build_connection()

    registry.add(conn)

    with pytest.raises(ValueError, match="Connection already registered"):
        registry.add(conn)


def test_connection_registry_remove_non_existent_returns_none() -> None:
    registry = ConnectionRegistry()

    assert registry.remove("missing") is None
