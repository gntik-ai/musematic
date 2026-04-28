from __future__ import annotations

import pytest

from suites._helpers import delete_ok, get_json, patch_json, post_json, unique_name


@pytest.mark.asyncio
async def test_namespace_crud_and_duplicate_detection(http_client) -> None:
    name = unique_name('namespace')
    created = await post_json(http_client, '/api/v1/namespaces', {'name': name, 'display_name': 'Namespace CRUD'}, {200, 201})
    namespace_id = created.get('id', name)
    fetched = await get_json(http_client, f'/api/v1/namespaces/{namespace_id}')
    assert fetched.get('name') == name
    updated = await patch_json(http_client, f'/api/v1/namespaces/{namespace_id}', {'display_name': 'Namespace CRUD updated'})
    assert updated.get('display_name') == 'Namespace CRUD updated'
    listed = await get_json(http_client, '/api/v1/namespaces', params={'limit': 10, 'offset': 0})
    assert isinstance(listed.get('items', listed), list)
    duplicate = await http_client.post('/api/v1/namespaces', json={'name': name, 'display_name': 'Duplicate'})
    assert duplicate.status_code == 409
    await delete_ok(http_client, f'/api/v1/namespaces/{namespace_id}')
