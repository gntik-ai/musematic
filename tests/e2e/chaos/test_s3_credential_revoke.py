from __future__ import annotations

import pytest

from suites._helpers import post_json


@pytest.mark.asyncio
async def test_s3_credential_revoke_surfaces_error(http_client) -> None:
    token = await post_json(http_client, '/api/v1/_e2e/chaos/s3/rotate-credentials', {'mode': 'revoke'})
    try:
        upload = await http_client.post('/api/v1/storage/artifacts', json={'name': 'test-revoke.txt', 'content': 'large-upload'})
        assert upload.status_code in {400, 500, 503}
        assert 'S3CredentialError' in upload.text
    finally:
        await post_json(http_client, '/api/v1/_e2e/chaos/s3/restore-credentials', {'token': token.get('restore_token')})
