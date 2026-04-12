from __future__ import annotations

import pytest

from tests.trust_support import build_rule_set_create, build_trust_bundle


@pytest.mark.asyncio
async def test_prescreener_rule_set_lifecycle_and_screening() -> None:
    bundle = build_trust_bundle()
    service = bundle.prescreener_service

    created = await service.create_rule_set(build_rule_set_create())
    activated = await service.activate_rule_set(created.id)
    blocked = await service.screen("This is a jailbreak attempt", "input")
    allowed = await service.screen("normal request", "input")
    listed = await service.list_rule_sets()

    assert created.version == 1
    assert activated.is_active is True
    assert blocked.blocked is True
    assert blocked.matched_rule == "jailbreak"
    assert allowed.blocked is False
    assert listed.total == 1
    assert ("trust-evidence", "prescreener/1/rules.json") in bundle.object_storage.objects
    assert bundle.producer.events[-1]["event_type"] == "prescreener.rule_set.activated"


@pytest.mark.asyncio
async def test_prescreener_loads_active_rules_from_redis_version_cache() -> None:
    bundle = build_trust_bundle()
    created = await bundle.prescreener_service.create_rule_set(build_rule_set_create())
    await bundle.redis.set("trust:prescreener:active_version", b"1")
    stored = await bundle.repository.get_rule_set(created.id)
    assert stored is not None
    stored.is_active = True

    await bundle.prescreener_service.load_active_rules()
    response = await bundle.prescreener_service.screen("drop table users", "input")
    await bundle.prescreener_service.handle_rule_set_activated({"event_type": "reload"})

    assert response.blocked is True
    assert response.matched_rule == "drop-table"
