from __future__ import annotations

import hashlib

import pytest

from suites._helpers import post_json


@pytest.mark.asyncio
async def test_generic_s3_upload_download_and_presign(http_client) -> None:
    content = b'e2e artifact content'
    checksum = hashlib.sha256(content).hexdigest()
    artifact = await post_json(http_client, '/api/v1/storage/artifacts', {'name': 'test-artifact.txt', 'content': content.decode(), 'sha256': checksum})
    download = await http_client.get(f"/api/v1/storage/artifacts/{artifact['id']}/download")
    assert download.status_code == 200
    assert hashlib.sha256(download.content).hexdigest() == checksum
    presign = await post_json(http_client, f"/api/v1/storage/artifacts/{artifact['id']}/presign", {'expires_seconds': 60})
    assert presign.get('url')
