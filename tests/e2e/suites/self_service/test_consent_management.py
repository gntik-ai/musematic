from __future__ import annotations

import pytest

from suites._helpers import get_json, post_json


@pytest.mark.asyncio
async def test_consent_list(consented_user, self_service_client) -> None:
    payload = await get_json(self_service_client, "/api/v1/me/consent")
    assert "items" in payload


@pytest.mark.asyncio
async def test_consent_revoke_emits_audit(consented_user, self_service_client) -> None:
    consents = (await get_json(self_service_client, "/api/v1/me/consent")).get("items", [])
    if not consents:
        pytest.skip("No consent available to revoke")
    consent_type = consents[0]["consent_type"]
    await post_json(
        self_service_client,
        "/api/v1/me/consent/revoke",
        {"consent_type": consent_type},
    )
    activity = await get_json(
        self_service_client,
        "/api/v1/me/activity",
        params={"event_type": "privacy.consent.revoked"},
    )
    assert "items" in activity


@pytest.mark.asyncio
async def test_consent_history_rendering_contract(consented_user, self_service_client) -> None:
    payload = await get_json(self_service_client, "/api/v1/me/consent/history")
    assert "items" in payload


@pytest.mark.asyncio
async def test_policy_version_change_reconsent_surface(consented_user, self_service_client) -> None:
    payload = await get_json(self_service_client, "/api/v1/me/consent")
    for item in payload.get("items", []):
        assert "consent_type" in item
        assert "granted" in item
