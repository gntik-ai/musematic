from __future__ import annotations

from platform.a2a_gateway.events import A2AEventPayload, A2AEventPublisher, A2AEventType
from platform.a2a_gateway.exceptions import (
    A2AEndpointConflictError,
    A2AHttpsRequiredError,
    A2APolicyDeniedError,
    A2ATaskNotFoundError,
    A2AUnsupportedCapabilityError,
)
from platform.a2a_gateway.external_registry import ExternalAgentCardRegistry
from platform.a2a_gateway.models import (
    A2AAuditRecord,
    A2ADirection,
    A2AExternalEndpoint,
    A2ATask,
    A2ATaskState,
)
from platform.a2a_gateway.repository import A2AGatewayRepository
from platform.a2a_gateway.schemas import (
    A2AExternalEndpointCreate,
    A2AExternalEndpointListResponse,
)
from platform.a2a_gateway.server_service import extract_text, replace_text
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.policies.gateway import ToolGatewayService
from platform.policies.models import EnforcementComponent, PolicyBlockedActionRecord
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

import httpx
from sqlalchemy.exc import IntegrityError


class A2AGatewayClientService:
    def __init__(
        self,
        *,
        repository: A2AGatewayRepository,
        external_registry: ExternalAgentCardRegistry,
        tool_gateway: ToolGatewayService,
        event_publisher: A2AEventPublisher,
        settings: PlatformSettings,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.repository = repository
        self.external_registry = external_registry
        self.tool_gateway = tool_gateway
        self.event_publisher = event_publisher
        self.settings = settings
        self.http_client = http_client

    async def list_external_endpoints(
        self,
        workspace_id: UUID,
    ) -> A2AExternalEndpointListResponse:
        items = await self.repository.list_external_endpoints(workspace_id)
        return A2AExternalEndpointListResponse(items=items, total=len(items))

    async def register_external_endpoint(
        self,
        *,
        workspace_id: UUID,
        payload: A2AExternalEndpointCreate,
        created_by: UUID,
    ) -> A2AExternalEndpoint:
        self._require_https(payload.endpoint_url)
        self._require_https(payload.agent_card_url)
        try:
            return await self.repository.create_external_endpoint(
                A2AExternalEndpoint(
                    workspace_id=workspace_id,
                    name=payload.name,
                    endpoint_url=payload.endpoint_url,
                    agent_card_url=payload.agent_card_url,
                    auth_config=payload.auth_config,
                    card_ttl_seconds=payload.card_ttl_seconds,
                    created_by=created_by,
                )
            )
        except IntegrityError as exc:
            raise A2AEndpointConflictError() from exc

    async def delete_external_endpoint(
        self,
        *,
        workspace_id: UUID,
        endpoint_id: UUID,
    ) -> A2AExternalEndpoint:
        endpoint = await self.repository.get_external_endpoint(
            endpoint_id,
            workspace_id=workspace_id,
        )
        if endpoint is None:
            raise A2ATaskNotFoundError(str(endpoint_id))
        return await self.repository.delete_external_endpoint(endpoint)

    async def invoke_external_agent(
        self,
        *,
        calling_agent_id: UUID,
        calling_agent_fqn: str,
        external_endpoint_id: UUID,
        message: dict[str, Any],
        workspace_id: UUID,
        execution_id: UUID | None,
        session: Any,
    ) -> A2ATask:
        del session
        endpoint = await self.repository.get_external_endpoint(
            external_endpoint_id,
            workspace_id=workspace_id,
        )
        if endpoint is None:
            raise A2ATaskNotFoundError(str(external_endpoint_id))
        self._require_https(endpoint.endpoint_url)
        self._require_https(endpoint.agent_card_url)

        gate = await self.tool_gateway.validate_tool_invocation(
            agent_id=calling_agent_id,
            agent_fqn=calling_agent_fqn,
            tool_fqn=f"a2a:{external_endpoint_id}",
            declared_purpose="a2a_outbound",
            execution_id=execution_id,
            workspace_id=workspace_id,
            session=self.repository.session,
        )
        if not gate.allowed:
            await self.repository.create_audit_record(
                A2AAuditRecord(
                    task_id=None,
                    direction=A2ADirection.outbound,
                    principal_id=calling_agent_id,
                    agent_fqn=calling_agent_fqn,
                    action="outbound_denied",
                    result="denied",
                    policy_decision=gate.model_dump(mode="json"),
                    workspace_id=workspace_id,
                    error_code=gate.block_reason,
                )
            )
            await self.repository.create_policy_blocked_record(
                PolicyBlockedActionRecord(
                    agent_id=calling_agent_id,
                    agent_fqn=calling_agent_fqn,
                    enforcement_component=EnforcementComponent.tool_gateway,
                    action_type="a2a_outbound_call",
                    target=f"a2a:{external_endpoint_id}",
                    block_reason=gate.block_reason or "policy_denied",
                    policy_rule_ref=gate.policy_rule_ref,
                    execution_id=execution_id,
                    workspace_id=workspace_id,
                )
            )
            await self.event_publisher.publish(
                event_type=A2AEventType.outbound_denied,
                key=str(external_endpoint_id),
                payload=A2AEventPayload(
                    task_id=None,
                    workspace_id=workspace_id,
                    principal_id=calling_agent_id,
                    agent_fqn=calling_agent_fqn,
                    state=A2ATaskState.failed.value,
                    direction=A2ADirection.outbound.value,
                    details={"reason": gate.block_reason or "policy_denied"},
                ),
                correlation_ctx=CorrelationContext(
                    workspace_id=workspace_id,
                    execution_id=execution_id,
                    agent_fqn=calling_agent_fqn,
                    correlation_id=uuid4(),
                ),
            )
            raise A2APolicyDeniedError(gate.block_reason or "policy_denied")

        card_entry = await self.external_registry.get_card(external_endpoint_id)
        card = card_entry["card"]
        authentications = card.get("authentication", []) if isinstance(card, dict) else []
        if authentications and not any(
            isinstance(item, dict) and item.get("scheme") == "bearer" for item in authentications
        ):
            raise A2AUnsupportedCapabilityError("authentication")

        task = await self.repository.create_task(
            A2ATask(
                task_id=f"a2a-task-{uuid4().hex[:8]}",
                direction=A2ADirection.outbound,
                a2a_state=A2ATaskState.submitted,
                agent_fqn=calling_agent_fqn,
                principal_id=calling_agent_id,
                workspace_id=workspace_id,
                interaction_id=None,
                conversation_id=None,
                external_endpoint_id=endpoint.id,
                protocol_version=self.settings.A2A_PROTOCOL_VERSION,
                submitted_message=message,
            )
        )
        await self.repository.create_audit_record(
            A2AAuditRecord(
                task_id=task.id,
                direction=A2ADirection.outbound,
                principal_id=calling_agent_id,
                agent_fqn=calling_agent_fqn,
                action="outbound_call",
                result="success",
                workspace_id=workspace_id,
            )
        )
        await self.event_publisher.publish(
            event_type=A2AEventType.outbound_attempted,
            key=task.task_id,
            payload=A2AEventPayload(
                task_id=task.task_id,
                workspace_id=workspace_id,
                principal_id=calling_agent_id,
                agent_fqn=calling_agent_fqn,
                state=A2ATaskState.submitted.value,
                direction=A2ADirection.outbound.value,
                details={"endpoint_id": str(endpoint.id)},
            ),
            correlation_ctx=CorrelationContext(
                workspace_id=workspace_id,
                execution_id=execution_id,
                agent_fqn=calling_agent_fqn,
                correlation_id=uuid4(),
            ),
        )

        result_payload = await self._submit_and_collect(endpoint, message)
        sanitized = await self._sanitize_result(
            calling_agent_id=calling_agent_id,
            calling_agent_fqn=calling_agent_fqn,
            endpoint_id=external_endpoint_id,
            workspace_id=workspace_id,
            execution_id=execution_id,
            payload=result_payload,
        )
        await self.repository.update_task_state(
            task,
            a2a_state=A2ATaskState.completed,
            result_payload=sanitized,
        )
        await self.repository.create_audit_record(
            A2AAuditRecord(
                task_id=task.id,
                direction=A2ADirection.outbound,
                principal_id=calling_agent_id,
                agent_fqn=calling_agent_fqn,
                action="task_completed",
                result="success",
                workspace_id=workspace_id,
            )
        )
        return task

    def _expect_mapping(self, value: Any, capability: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise A2AUnsupportedCapabilityError(capability)
        return {str(key): item for key, item in value.items()}

    async def _submit_and_collect(
        self,
        endpoint: A2AExternalEndpoint,
        message: dict[str, Any],
    ) -> dict[str, Any]:
        client = self.http_client
        should_close = False
        if client is None:
            client = httpx.AsyncClient(timeout=10.0)
            should_close = True
        headers: dict[str, str] = {}
        auth_scheme = None
        token = None
        if isinstance(endpoint.auth_config, dict):
            auth_scheme = endpoint.auth_config.get("scheme")
            raw_token = endpoint.auth_config.get("token") or endpoint.auth_config.get("value")
            token = raw_token if isinstance(raw_token, str) else None
        if auth_scheme == "bearer" and token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            response = await client.post(
                endpoint.endpoint_url,
                json={
                    "agent_fqn": endpoint.name,
                    "message": message,
                    "protocol_version": self.settings.A2A_PROTOCOL_VERSION,
                },
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise A2AUnsupportedCapabilityError("response_format")
            state = payload.get("a2a_state")
            if state == "completed" and isinstance(payload.get("result"), dict):
                return self._expect_mapping(payload["result"], "result")
            if isinstance(payload.get("result_payload"), dict):
                return self._expect_mapping(payload["result_payload"], "result_payload")
            if isinstance(payload.get("result"), str):
                return {"role": "agent", "parts": [{"type": "text", "text": payload["result"]}]}
            if isinstance(payload.get("message"), dict):
                return self._expect_mapping(payload["message"], "message")
            external_task_id = payload.get("task_id")
            status_url = payload.get("status_url")
            if not isinstance(external_task_id, str):
                raise A2AUnsupportedCapabilityError("response_task_id")
            if not isinstance(status_url, str):
                status_url = f"{endpoint.endpoint_url.rstrip('/')}/{external_task_id}"
            for _ in range(5):
                follow_up = await client.get(status_url, headers=headers)
                follow_up.raise_for_status()
                follow_payload = follow_up.json()
                if not isinstance(follow_payload, dict):
                    continue
                if follow_payload.get("a2a_state") != "completed":
                    continue
                if isinstance(follow_payload.get("result"), dict):
                    return self._expect_mapping(follow_payload["result"], "result")
                if isinstance(follow_payload.get("result_payload"), dict):
                    return self._expect_mapping(follow_payload["result_payload"], "result_payload")
            raise A2AUnsupportedCapabilityError("completion")
        finally:
            if should_close:
                await client.aclose()

    async def _sanitize_result(
        self,
        *,
        calling_agent_id: UUID,
        calling_agent_fqn: str,
        endpoint_id: UUID,
        workspace_id: UUID,
        execution_id: UUID | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        text = extract_text(payload)
        result = await self.tool_gateway.sanitize_tool_output(
            text,
            agent_id=calling_agent_id,
            agent_fqn=calling_agent_fqn,
            tool_fqn=f"a2a:{endpoint_id}",
            execution_id=execution_id,
            session=self.repository.session,
            workspace_id=workspace_id,
        )
        return replace_text(payload, result.output)

    def _require_https(self, url: str) -> None:
        if urlparse(url).scheme != "https":
            raise A2AHttpsRequiredError()
