from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_bulk_suspend_preview_and_apply_return_single_bulk_action(http_client_superadmin) -> None:
    user_ids = [f"11111111-1111-4111-8111-{index:012d}" for index in range(50)]

    preview = await http_client_superadmin.post(
        "/api/v1/admin/users/bulk/suspend?preview=true",
        json=user_ids,
    )
    assert preview.status_code == 200
    preview_payload = preview.json()
    assert preview_payload["preview"] is True
    assert preview_payload["affected_count"] == 50
    assert preview_payload["change_preview"]["irreversibility"] == "reversible"

    applied = await http_client_superadmin.post(
        "/api/v1/admin/users/bulk/suspend?preview=false",
        json=user_ids,
    )
    assert applied.status_code == 200
    payload = applied.json()
    assert payload["bulk_action_id"]
    assert payload["affected_count"] == 50
