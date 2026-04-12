from __future__ import annotations

from platform.policies.dependencies import (
    build_memory_write_gate_service,
    build_policy_service,
    build_tool_gateway_service,
    get_memory_write_gate_service,
    get_policy_service,
    get_tool_gateway_service,
)
from platform.policies.gateway import MemoryWriteGateService, ToolGatewayService
from platform.policies.service import PolicyService
from types import SimpleNamespace

import pytest

from tests.policies_support import (
    RegistryPolicyStub,
    WorkspacesPolicyStub,
    build_fake_redis,
    build_policy_settings,
)
from tests.registry_support import SessionStub


def test_build_service_helpers_wire_expected_types() -> None:
    _memory, redis_client = build_fake_redis()
    policy_service = build_policy_service(
        session=SessionStub(),
        settings=build_policy_settings(),
        producer=None,
        redis_client=redis_client,
        registry_service=RegistryPolicyStub(),
        workspaces_service=WorkspacesPolicyStub(),
        reasoning_client=None,
    )
    tool_gateway = build_tool_gateway_service(
        session=SessionStub(),
        settings=build_policy_settings(),
        producer=None,
        redis_client=redis_client,
        registry_service=RegistryPolicyStub(),
        workspaces_service=WorkspacesPolicyStub(),
        reasoning_client=None,
    )
    memory_gateway = build_memory_write_gate_service(
        session=SessionStub(),
        settings=build_policy_settings(),
        producer=None,
        redis_client=redis_client,
        registry_service=RegistryPolicyStub(),
        workspaces_service=WorkspacesPolicyStub(),
        reasoning_client=None,
    )

    assert isinstance(policy_service, PolicyService)
    assert isinstance(tool_gateway, ToolGatewayService)
    assert isinstance(memory_gateway, MemoryWriteGateService)


@pytest.mark.asyncio
async def test_get_service_helpers_read_from_request_state() -> None:
    _memory, redis_client = build_fake_redis()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=build_policy_settings(),
                clients={
                    "redis": redis_client,
                    "kafka": None,
                    "reasoning_engine": None,
                },
            )
        )
    )

    policy_service = await get_policy_service(
        request,
        session=SessionStub(),
        registry_service=RegistryPolicyStub(),
        workspaces_service=WorkspacesPolicyStub(),
    )
    tool_gateway = await get_tool_gateway_service(
        request,
        session=SessionStub(),
        registry_service=RegistryPolicyStub(),
        workspaces_service=WorkspacesPolicyStub(),
    )
    memory_gateway = await get_memory_write_gate_service(
        request,
        session=SessionStub(),
        registry_service=RegistryPolicyStub(),
        workspaces_service=WorkspacesPolicyStub(),
    )

    assert isinstance(policy_service, PolicyService)
    assert isinstance(tool_gateway, ToolGatewayService)
    assert isinstance(memory_gateway, MemoryWriteGateService)
