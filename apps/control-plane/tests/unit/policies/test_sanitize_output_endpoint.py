from __future__ import annotations

from platform.common.dependencies import get_db
from platform.policies.dependencies import get_tool_gateway_service
from platform.policies.gateway import ToolGatewayService
from platform.policies.router import router as policies_router
from platform.policies.sanitizer import OutputSanitizer
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from tests.policies_support import InMemoryPolicyRepository


class SessionStub:
    pass


def build_sanitize_output_app(repository: InMemoryPolicyRepository) -> FastAPI:
    app = FastAPI()
    gateway = ToolGatewayService(
        policy_service=SimpleNamespace(),
        sanitizer=OutputSanitizer(repository),
        reasoning_client=None,
        registry_service=None,
        settings=None,
    )

    async def _gateway() -> ToolGatewayService:
        return gateway

    async def _db() -> SessionStub:
        return SessionStub()

    app.dependency_overrides[get_tool_gateway_service] = _gateway
    app.dependency_overrides[get_db] = _db
    app.include_router(policies_router)
    return app


def make_transport(app: FastAPI) -> httpx.ASGITransport:
    return httpx.ASGITransport(app=app)


@pytest.mark.asyncio
async def test_sanitize_output_endpoint_redacts_bearer_tokens() -> None:
    repository = InMemoryPolicyRepository()
    app = build_sanitize_output_app(repository)

    async with httpx.AsyncClient(
        transport=make_transport(app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/policies/gate/sanitize-output",
            json={
                "output": "Authorization: Bearer abcdefghijklmnop123456",
                "agent_id": str(uuid4()),
                "agent_fqn": "finance:agent",
                "tool_fqn": "finance:search",
                "execution_id": None,
                "workspace_id": str(uuid4()),
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert "[REDACTED:bearer_token]" in body["output"]
    assert body["redaction_count"] >= 1


@pytest.mark.asyncio
async def test_sanitize_output_endpoint_redacts_connection_strings() -> None:
    repository = InMemoryPolicyRepository()
    app = build_sanitize_output_app(repository)

    async with httpx.AsyncClient(
        transport=make_transport(app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/policies/gate/sanitize-output",
            json={
                "output": "DB failure: postgres://user:pass@db:5432/prod",
                "agent_id": str(uuid4()),
                "agent_fqn": "finance:agent",
                "tool_fqn": "finance:search",
                "execution_id": str(uuid4()),
                "workspace_id": str(uuid4()),
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert "[REDACTED:connection_string]" in body["output"]
    assert body["redaction_count"] >= 1


@pytest.mark.asyncio
async def test_sanitize_output_endpoint_redacts_jwt_tokens_in_json_strings() -> None:
    repository = InMemoryPolicyRepository()
    app = build_sanitize_output_app(repository)
    output = '{"result": "ok", "token": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyMSJ9.signature123"}'

    async with httpx.AsyncClient(
        transport=make_transport(app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/policies/gate/sanitize-output",
            json={
                "output": output,
                "agent_id": str(uuid4()),
                "agent_fqn": "finance:agent",
                "tool_fqn": "finance:search",
                "execution_id": str(uuid4()),
                "workspace_id": str(uuid4()),
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert "[REDACTED:jwt_token]" in body["output"]
    assert body["redaction_count"] >= 1


@pytest.mark.asyncio
async def test_sanitize_output_endpoint_leaves_clean_output_unchanged() -> None:
    repository = InMemoryPolicyRepository()
    app = build_sanitize_output_app(repository)

    async with httpx.AsyncClient(
        transport=make_transport(app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/policies/gate/sanitize-output",
            json={
                "output": "no secrets here, just a search result",
                "agent_id": str(uuid4()),
                "agent_fqn": "finance:agent",
                "tool_fqn": "finance:search",
                "execution_id": None,
                "workspace_id": str(uuid4()),
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["output"] == "no secrets here, just a search result"
    assert body["redaction_count"] == 0
    assert repository.blocked_records == {}
