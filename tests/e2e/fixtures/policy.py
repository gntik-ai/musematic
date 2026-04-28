from __future__ import annotations

import pytest


class PolicyFactory:
    def __init__(self, http_client, workspace_id: str) -> None:
        self.http_client = http_client
        self.workspace_id = workspace_id
        self.bindings: list[str] = []

    async def attach(self, policy_name: str, target_agent_fqn: str):
        response = await self.http_client.post(
            "/api/v1/policies/bindings",
            json={
                "policy_name": policy_name,
                "target_agent_fqn": target_agent_fqn,
                "workspace_id": self.workspace_id,
            },
        )
        assert response.status_code in {200, 201}, response.text
        payload = response.json()
        if payload.get("id"):
            self.bindings.append(payload["id"])
        return payload

    async def detach(self, binding_id: str) -> None:
        response = await self.http_client.delete(f"/api/v1/policies/bindings/{binding_id}")
        assert response.status_code in {200, 202, 204, 404}, response.text

    async def cleanup(self) -> None:
        for binding_id in reversed(self.bindings):
            await self.detach(binding_id)


@pytest.fixture(scope="function")
async def policy(http_client, workspace) -> PolicyFactory:
    factory = PolicyFactory(http_client, workspace_id=workspace["id"])
    try:
        yield factory
    finally:
        await factory.cleanup()
