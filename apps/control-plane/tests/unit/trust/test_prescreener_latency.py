from __future__ import annotations

import pytest

from tests.trust_support import build_rule_set_create, build_trust_bundle


@pytest.mark.asyncio
async def test_prescreener_screen_reports_latency_on_blocked_match() -> None:
    bundle = build_trust_bundle()
    service = bundle.prescreener_service
    created = await service.create_rule_set(build_rule_set_create())
    await service.activate_rule_set(created.id)

    response = await service.screen("This is a jailbreak attempt", "input")

    assert response.blocked is True
    assert response.matched_rule == "jailbreak"
    assert response.latency_ms is not None
    assert response.latency_ms >= 0.0
    assert response.rule_set_version == str(created.version)


@pytest.mark.asyncio
async def test_prescreener_screen_reports_latency_when_no_patterns_match() -> None:
    bundle = build_trust_bundle()
    service = bundle.prescreener_service
    created = await service.create_rule_set(build_rule_set_create())
    await service.activate_rule_set(created.id)

    response = await service.screen("normal request", "input")

    assert response.blocked is False
    assert response.passed_to_full_pipeline is True
    assert response.latency_ms is not None
    assert response.latency_ms >= 0.0
    assert response.rule_set_version == str(created.version)


@pytest.mark.asyncio
async def test_prescreener_screen_has_no_version_without_active_rule_set() -> None:
    bundle = build_trust_bundle()
    service = bundle.prescreener_service
    service._compiled_patterns = {}
    service._active_version = None

    response = await service.screen("content", "input")

    assert response.blocked is False
    assert response.rule_set_version is None
    assert response.latency_ms is not None
    assert response.latency_ms >= 0.0
