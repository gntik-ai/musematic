from __future__ import annotations

from platform.a2a_gateway.card_generator import AgentCardGenerator

import pytest
from tests.a2a_gateway_support import ExecuteResultStub, SessionStub, build_agent_profile


@pytest.mark.asyncio
async def test_generate_platform_card_aggregates_skills_and_capabilities() -> None:
    published = build_agent_profile(fqn="finance:verifier")
    no_revision = build_agent_profile(fqn="finance:draft", revisions=[])
    session = SessionStub(execute_results=[ExecuteResultStub(items=[published, no_revision])])

    card = await AgentCardGenerator().generate_platform_card(
        session, base_url="https://mesh.example"
    )

    assert card["url"] == "https://mesh.example/api/v1/a2a"
    assert card["authentication"] == [{"scheme": "bearer", "in": "header", "name": "Authorization"}]
    assert [skill["id"] for skill in card["skills"]] == ["finance:verifier"]
    assert set(card["capabilities"]) >= {"multi-turn", "streaming", "debate", "tot"}
