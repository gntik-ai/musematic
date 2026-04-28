from __future__ import annotations

import pytest

from suites._helpers import get_json, post_json


@pytest.mark.asyncio
async def test_conversation_branch_merge_and_close(http_client, workspace) -> None:
    conversation = await post_json(http_client, '/api/v1/interactions/conversations', {'workspace_id': workspace['id'], 'title': 'E2E conversation'})
    message = await post_json(http_client, f"/api/v1/interactions/conversations/{conversation['id']}/messages", {'content': 'hello'})
    branch = await post_json(http_client, f"/api/v1/interactions/conversations/{conversation['id']}/branches", {'from_message_id': message.get('id')})
    await post_json(http_client, f"/api/v1/interactions/conversations/{conversation['id']}/branches/{branch['id']}/merge", {})
    closed = await post_json(http_client, f"/api/v1/interactions/conversations/{conversation['id']}/close", {})
    fetched = await get_json(http_client, f"/api/v1/interactions/conversations/{conversation['id']}")
    assert closed.get('state') == fetched.get('state') == 'closed'
