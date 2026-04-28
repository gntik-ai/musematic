from __future__ import annotations

from uuid import uuid4

import pytest


class AgentFactory:
    def __init__(self, http_client, workspace_id: str) -> None:
        self.http_client = http_client
        self.workspace_id = workspace_id
        self.created: list[str] = []

    async def register(self, namespace: str, local_name: str, role_type: str, **kwargs):
        scoped_local_name = f"test-{local_name}-{uuid4().hex[:6]}"
        payload = {
            "namespace": namespace,
            "local_name": scoped_local_name,
            "fqn": f"{namespace}:{scoped_local_name}",
            "role_type": role_type,
            "workspace_id": self.workspace_id,
            "purpose": kwargs.pop("purpose", "E2E factory-created agent purpose.".ljust(60, ".")),
            "approach": kwargs.pop(
                "approach",
                "E2E factory-created agent approach for deterministic tests.".ljust(80, "."),
            ),
            **kwargs,
        }
        response = await self.http_client.post("/api/v1/agents", json=payload)
        assert response.status_code in {200, 201}, response.text
        agent = response.json()
        self.created.append(agent.get("id") or payload["fqn"])
        return agent

    async def with_certification(self, agent_id: str, valid_days: int = 30):
        response = await self.http_client.post(
            f"/api/v1/trust/agents/{agent_id}/certifications",
            json={"valid_days": valid_days, "status": "active"},
        )
        assert response.status_code in {200, 201}, response.text
        return response.json()

    async def with_visibility(self, agent_id: str, patterns: list[str]):
        response = await self.http_client.post(
            f"/api/v1/agents/{agent_id}/visibility",
            json={"patterns": patterns},
        )
        assert response.status_code in {200, 201, 204}, response.text
        return response.json() if response.content else {}

    async def cleanup(self) -> None:
        for agent_id in reversed(self.created):
            await self.http_client.delete(f"/api/v1/agents/{agent_id}")


@pytest.fixture(scope="function")
async def agent(http_client, workspace) -> AgentFactory:
    factory = AgentFactory(http_client, workspace_id=workspace["id"])
    try:
        yield factory
    finally:
        await factory.cleanup()
