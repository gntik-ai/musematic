from __future__ import annotations

from platform.audit.repository import AuditChainRepository
from platform.audit.repository import _encode_cursor as _encode_audit_cursor
from uuid import uuid4

import pytest

from tests.unit.test_me_service_router import NOW, ExecuteResult, QuerySession


@pytest.mark.asyncio
async def test_activity_query_uses_actor_or_subject_and_cursor_pagination() -> None:
    entries = [type("Entry", (), {"id": uuid4(), "created_at": NOW})() for _ in range(2)]
    repository = AuditChainRepository(QuerySession([ExecuteResult(entries)]))

    page, next_cursor = await repository.list_entries_by_actor_or_subject(
        actor_id=uuid4(),
        subject_id=uuid4(),
        start_ts=NOW,
        end_ts=NOW,
        event_type="auth.session.revoked",
        limit=1,
        cursor=_encode_audit_cursor(entries[0]),
    )

    assert page == entries[:1]
    assert next_cursor is not None
