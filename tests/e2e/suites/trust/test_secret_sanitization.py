from __future__ import annotations

import pytest

from suites._helpers import post_json


@pytest.mark.asyncio
async def test_secret_sanitization_preserves_json_structure(http_client) -> None:
    payload = await post_json(http_client, '/api/v1/policies/sanitize-output', {'content_type': 'application/json', 'content': {'token': 'sk-test-secret-1234567890', 'status': 'ok'}})
    assert '[REDACTED:secret]' in str(payload)
    assert payload.get('content', {}).get('status') == 'ok'
    clean = await post_json(http_client, '/api/v1/policies/sanitize-output', {'content_type': 'text/plain', 'content': 'hello world'})
    assert clean.get('content') == 'hello world'
