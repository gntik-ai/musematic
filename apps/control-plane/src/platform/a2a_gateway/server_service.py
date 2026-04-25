from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from platform.a2a_gateway.card_generator import AgentCardGenerator
from platform.a2a_gateway.events import A2AEventPayload, A2AEventPublisher, A2AEventType
from platform.a2a_gateway.exceptions import (
    A2AAgentNotFoundError,
    A2AAuthenticationError,
    A2AAuthorizationError,
    A2AInvalidTaskStateError,
    A2APayloadTooLargeError,
    A2AProtocolVersionError,
    A2ARateLimitError,
    A2ATaskNotFoundError,
)
from platform.a2a_gateway.models import A2AAuditRecord, A2ADirection, A2ATask, A2ATaskState
from platform.a2a_gateway.repository import A2AGatewayRepository
from platform.a2a_gateway.schemas import (
    A2AFollowUpRequest,
    A2ATaskResponse,
    A2ATaskStatusResponse,
    A2ATaskSubmitRequest,
)
from platform.audit.dependencies import build_audit_chain_service
from platform.auth.exceptions import (
    AccessTokenExpiredError,
    InactiveUserError,
    InvalidAccessTokenError,
)
from platform.auth.service import AuthService
from platform.common.audit_hook import audit_chain_hook
from platform.common.clients.redis import AsyncRedisClient, RateLimitResult
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.interactions.models import InteractionState, MessageType
from platform.interactions.repository import InteractionsRepository
from platform.policies.gateway import ToolGatewayService
from platform.policies.models import EnforcementComponent, PolicyBlockedActionRecord
from platform.registry.models import AgentProfile, LifecycleStatus
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class A2AServerService:
    def __init__(
        self,
        *,
        repository: A2AGatewayRepository,
        settings: PlatformSettings,
        auth_service: AuthService,
        tool_gateway: ToolGatewayService,
        redis_client: AsyncRedisClient,
        event_publisher: A2AEventPublisher,
        card_generator: AgentCardGenerator,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.auth_service = auth_service
        self.tool_gateway = tool_gateway
        self.redis_client = redis_client
        self.event_publisher = event_publisher
        self.card_generator = card_generator

    @property
    def session(self) -> AsyncSession:
        return self.repository.session

    async def authenticate(self, token: str) -> dict[str, Any]:
        try:
            return await self.auth_service.validate_token(token)
        except (InvalidAccessTokenError, AccessTokenExpiredError, InactiveUserError) as exc:
            raise A2AAuthenticationError(str(exc)) from exc

    async def get_platform_agent_card(self, *, base_url: str) -> dict[str, Any]:
        return await self.card_generator.generate_platform_card(self.session, base_url=base_url)

    async def submit_task(
        self,
        request: A2ATaskSubmitRequest,
        *,
        principal: dict[str, Any],
    ) -> A2ATaskResponse:
        self._validate_protocol(request.protocol_version)
        self._validate_payload_size(request)
        agent = await self._resolve_agent(request.agent_fqn)
        principal_id = self._principal_id(principal)

        if not self._principal_can_access_workspace(principal, agent.workspace_id):
            await self._record_denial(
                agent=agent,
                principal_id=principal_id,
                action="authz_failed",
                block_reason="workspace_denied",
            )
            raise A2AAuthorizationError()

        gate = await self.tool_gateway.validate_tool_invocation(
            agent_id=agent.id,
            agent_fqn=agent.fqn,
            tool_fqn="a2a:inbound",
            declared_purpose="a2a_inbound",
            execution_id=None,
            workspace_id=agent.workspace_id,
            session=self.session,
        )
        if not gate.allowed:
            await self._record_denial(
                agent=agent,
                principal_id=principal_id,
                action="authz_failed",
                block_reason=gate.block_reason or "policy_denied",
                policy_decision=gate.model_dump(mode="json"),
                policy_rule_ref=gate.policy_rule_ref,
            )
            raise A2AAuthorizationError()

        rate_limit = await self._check_rate_limit(principal_id)
        if not rate_limit.allowed:
            await self._create_audit(
                task=None,
                direction=A2ADirection.inbound,
                principal_id=principal_id,
                agent_fqn=agent.fqn,
                action="rate_limited",
                result="denied",
                workspace_id=agent.workspace_id,
                error_code="rate_limit_exceeded",
            )
            await self.repository.create_policy_blocked_record(
                PolicyBlockedActionRecord(
                    agent_id=agent.id,
                    agent_fqn=agent.fqn,
                    enforcement_component=EnforcementComponent.tool_gateway,
                    action_type="a2a_inbound_submit",
                    target="a2a:inbound",
                    block_reason="rate_limit_exceeded",
                    policy_rule_ref={"retry_after_ms": rate_limit.retry_after_ms},
                    execution_id=None,
                    workspace_id=agent.workspace_id,
                )
            )
            raise A2ARateLimitError(rate_limit.retry_after_ms)

        interactions_repo = InteractionsRepository(self.session)
        conversation_id = request.conversation_id
        if conversation_id is None:
            conversation = await interactions_repo.create_conversation(
                workspace_id=agent.workspace_id,
                title=f"A2A task for {agent.fqn}",
                created_by=str(principal_id),
                metadata={"source": "a2a_gateway"},
            )
            conversation_id = conversation.id
        interaction = await interactions_repo.create_interaction(
            conversation_id=conversation_id,
            workspace_id=agent.workspace_id,
            goal_id=None,
            state=InteractionState.running,
        )
        await interactions_repo.create_message(
            interaction_id=interaction.id,
            parent_message_id=None,
            sender_identity=str(principal_id),
            message_type=MessageType.user,
            content=extract_text(request.message.model_dump(mode="json")),
            metadata={"a2a_message": request.message.model_dump(mode="json")},
        )
        task = await self.repository.create_task(
            A2ATask(
                task_id=f"a2a-task-{uuid4().hex[:8]}",
                direction=A2ADirection.inbound,
                a2a_state=A2ATaskState.submitted,
                agent_fqn=agent.fqn,
                principal_id=principal_id,
                workspace_id=agent.workspace_id,
                interaction_id=interaction.id,
                conversation_id=conversation_id,
                external_endpoint_id=None,
                protocol_version=request.protocol_version or self.settings.A2A_PROTOCOL_VERSION,
                submitted_message=request.message.model_dump(mode="json"),
            )
        )
        await self._record_task_event(
            task,
            action="task_submitted",
            result="success",
            event_type=A2AEventType.task_submitted,
        )
        return A2ATaskResponse(
            task_id=task.task_id,
            a2a_state=task.a2a_state,
            agent_fqn=task.agent_fqn,
            created_at=task.created_at,
        )

    async def get_task_status(
        self,
        task_id: str,
        *,
        principal: dict[str, Any],
    ) -> A2ATaskStatusResponse:
        task = await self._require_task_access(task_id, principal)
        await self._progress_task(task)
        return self._status_response(task)

    async def cancel_task(
        self,
        task_id: str,
        *,
        principal: dict[str, Any],
    ) -> A2ATaskStatusResponse:
        task = await self._require_task_access(task_id, principal)
        if task.a2a_state is A2ATaskState.cancelled:
            return self._status_response(task)
        if task.a2a_state in {A2ATaskState.completed, A2ATaskState.failed}:
            return self._status_response(task)
        await self.repository.update_task_state(
            task,
            a2a_state=A2ATaskState.cancellation_pending,
            cancellation_requested_at=datetime.now(UTC),
        )
        await self._record_task_event(
            task,
            action="task_cancel_requested",
            result="success",
            event_type=A2AEventType.task_state_changed,
        )
        return self._status_response(task)

    async def submit_follow_up(
        self,
        task_id: str,
        request: A2AFollowUpRequest,
        *,
        principal: dict[str, Any],
    ) -> A2ATaskStatusResponse:
        task = await self._require_task_access(task_id, principal)
        if task.a2a_state is not A2ATaskState.input_required:
            raise A2AInvalidTaskStateError(task.a2a_state.value)
        if task.workspace_id is None or task.conversation_id is None:
            raise A2AInvalidTaskStateError(task.a2a_state.value)

        interactions_repo = InteractionsRepository(self.session)
        interaction = await interactions_repo.create_interaction(
            conversation_id=task.conversation_id,
            workspace_id=task.workspace_id,
            goal_id=None,
            state=InteractionState.running,
        )
        await interactions_repo.create_message(
            interaction_id=interaction.id,
            parent_message_id=None,
            sender_identity=str(self._principal_id(principal)),
            message_type=MessageType.user,
            content=extract_text(request.message.model_dump(mode="json")),
            metadata={"a2a_message": request.message.model_dump(mode="json")},
        )
        task.interaction_id = interaction.id
        task.submitted_message = request.message.model_dump(mode="json")
        await self.repository.update_task_state(
            task,
            a2a_state=A2ATaskState.working,
            result_payload=None,
            idle_timeout_at=None,
        )
        await self._record_task_event(
            task,
            action="task_state_changed",
            result="success",
            event_type=A2AEventType.task_state_changed,
        )
        return self._status_response(task)

    async def run_idle_timeout_scan(self) -> int:
        tasks = await self.repository.list_tasks_idle_expired()
        for task in tasks:
            await self.repository.update_task_state(
                task,
                a2a_state=A2ATaskState.cancelled,
                error_code="idle_timeout",
                error_message="Task was cancelled after waiting for follow-up input.",
                idle_timeout_at=None,
            )
            await self._record_task_event(
                task,
                action="task_cancelled",
                result="success",
                event_type=A2AEventType.task_cancelled,
            )
        return len(tasks)

    async def _resolve_agent(self, agent_fqn: str) -> AgentProfile:
        result = await self.session.execute(
            select(AgentProfile).where(
                AgentProfile.fqn == agent_fqn,
                AgentProfile.status == LifecycleStatus.published,
                AgentProfile.deleted_at.is_(None),
            )
        )
        agent = result.scalar_one_or_none()
        if agent is None:
            raise A2AAgentNotFoundError(agent_fqn)
        return agent

    async def _check_rate_limit(self, principal_id: UUID) -> RateLimitResult:
        return await self.redis_client.check_rate_limit(
            "a2a",
            str(principal_id),
            self.settings.A2A_RATE_LIMIT_PER_PRINCIPAL_PER_MINUTE,
            60_000,
        )

    async def _require_task_access(
        self,
        task_id: str,
        principal: dict[str, Any],
    ) -> A2ATask:
        task = await self.repository.get_task_by_task_id(task_id)
        if task is None:
            raise A2ATaskNotFoundError(task_id)
        principal_id = self._principal_id(principal)
        if (
            task.principal_id is not None
            and task.principal_id != principal_id
            and not self._is_operator(principal)
        ):
            raise A2AAuthorizationError()
        return task

    async def _progress_task(self, task: A2ATask) -> None:
        if task.a2a_state in {
            A2ATaskState.completed,
            A2ATaskState.failed,
            A2ATaskState.cancelled,
        }:
            return
        if task.a2a_state is A2ATaskState.cancellation_pending:
            await self.repository.update_task_state(task, a2a_state=A2ATaskState.cancelled)
            await self._record_task_event(
                task,
                action="task_cancelled",
                result="success",
                event_type=A2AEventType.task_cancelled,
            )
            return

        interaction_state = await self._interaction_state(task)
        if interaction_state is InteractionState.waiting:
            await self._set_input_required(task)
            return
        if interaction_state is InteractionState.failed:
            await self._set_failed(task)
            return
        if interaction_state is InteractionState.canceled:
            await self.repository.update_task_state(task, a2a_state=A2ATaskState.cancelled)
            await self._record_task_event(
                task,
                action="task_cancelled",
                result="success",
                event_type=A2AEventType.task_cancelled,
            )
            return

        message_text = extract_text(task.submitted_message)
        lowered = message_text.lower()
        if task.a2a_state is A2ATaskState.submitted:
            await self.repository.update_task_state(task, a2a_state=A2ATaskState.working)
            await self._record_task_event(
                task,
                action="task_state_changed",
                result="success",
                event_type=A2AEventType.task_state_changed,
            )
            return
        if "clarify" in lowered or "need more" in lowered:
            await self._set_input_required(task)
            return
        if "fail" in lowered or "error" in lowered:
            await self._set_failed(task)
            return

        result_text = f"Completed A2A task for {task.agent_fqn}: {message_text or 'ok'}"
        result_payload = build_result_message(result_text)
        sanitized = await self._sanitize_result(task, result_payload)
        await self.repository.update_task_state(
            task,
            a2a_state=A2ATaskState.completed,
            result_payload=sanitized,
            error_code=None,
            error_message=None,
            idle_timeout_at=None,
        )
        await self._record_task_event(
            task,
            action="task_completed",
            result="success",
            event_type=A2AEventType.task_completed,
        )

    async def _set_input_required(self, task: A2ATask) -> None:
        prompt = build_prompt_message("Please provide the requested clarification.")
        await self.repository.update_task_state(
            task,
            a2a_state=A2ATaskState.input_required,
            result_payload=prompt,
            idle_timeout_at=datetime.now(UTC)
            + timedelta(minutes=self.settings.A2A_TASK_IDLE_TIMEOUT_MINUTES),
        )
        await self._record_task_event(
            task,
            action="task_state_changed",
            result="success",
            event_type=A2AEventType.task_state_changed,
        )

    async def _set_failed(self, task: A2ATask) -> None:
        await self.repository.update_task_state(
            task,
            a2a_state=A2ATaskState.failed,
            error_code="agent_execution_error",
            error_message="The agent was unable to complete the task.",
        )
        await self._record_task_event(
            task,
            action="task_failed",
            result="error",
            event_type=A2AEventType.task_failed,
        )

    async def _interaction_state(self, task: A2ATask) -> InteractionState | None:
        if task.interaction_id is None or task.workspace_id is None:
            return None
        interactions_repo = InteractionsRepository(self.session)
        interaction = await interactions_repo.get_interaction(
            task.interaction_id,
            task.workspace_id,
        )
        return interaction.state if interaction is not None else None

    async def _sanitize_result(
        self,
        task: A2ATask,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        text = extract_text(payload)
        agent = await self._resolve_agent(task.agent_fqn)
        result = await self.tool_gateway.sanitize_tool_output(
            text,
            agent_id=agent.id,
            agent_fqn=agent.fqn,
            tool_fqn="a2a:inbound",
            execution_id=None,
            session=self.session,
            workspace_id=task.workspace_id,
        )
        sanitized_payload = replace_text(payload, result.output)
        if result.redaction_count > 0:
            await self._create_audit(
                task=task,
                direction=A2ADirection.inbound,
                principal_id=task.principal_id,
                agent_fqn=task.agent_fqn,
                action="sanitized",
                result="success",
                workspace_id=task.workspace_id,
                policy_decision={
                    "redaction_count": result.redaction_count,
                    "redacted_types": result.redacted_types,
                },
            )
        return sanitized_payload

    async def _record_denial(
        self,
        *,
        agent: AgentProfile,
        principal_id: UUID,
        action: str,
        block_reason: str,
        policy_decision: dict[str, Any] | None = None,
        policy_rule_ref: dict[str, Any] | None = None,
    ) -> None:
        await self._create_audit(
            task=None,
            direction=A2ADirection.inbound,
            principal_id=principal_id,
            agent_fqn=agent.fqn,
            action=action,
            result="denied",
            workspace_id=agent.workspace_id,
            error_code="authorization_error",
            policy_decision=policy_decision,
        )
        await self.repository.create_policy_blocked_record(
            PolicyBlockedActionRecord(
                agent_id=agent.id,
                agent_fqn=agent.fqn,
                enforcement_component=EnforcementComponent.tool_gateway,
                action_type="a2a_inbound_submit",
                target="a2a:inbound",
                block_reason=block_reason,
                policy_rule_ref=policy_rule_ref,
                execution_id=None,
                workspace_id=agent.workspace_id,
            )
        )

    async def _record_task_event(
        self,
        task: A2ATask,
        *,
        action: str,
        result: str,
        event_type: A2AEventType,
        error_code: str | None = None,
        policy_decision: dict[str, Any] | None = None,
    ) -> None:
        audit = await self._create_audit(
            task=task,
            direction=task.direction,
            principal_id=task.principal_id,
            agent_fqn=task.agent_fqn,
            action=action,
            result=result,
            workspace_id=task.workspace_id,
            error_code=error_code,
            policy_decision=policy_decision,
        )
        await self.repository.update_task_state(task, last_event_id=str(audit.id))
        details = {"action": action}
        if error_code is not None:
            details["error_code"] = error_code
        await self.event_publisher.publish(
            event_type=event_type,
            key=task.task_id,
            payload=A2AEventPayload(
                task_id=task.task_id,
                workspace_id=task.workspace_id,
                principal_id=task.principal_id,
                agent_fqn=task.agent_fqn,
                state=task.a2a_state.value,
                direction=task.direction.value,
                details=details,
            ),
            correlation_ctx=self._correlation(task),
        )

    async def _create_audit(
        self,
        *,
        task: A2ATask | None,
        direction: A2ADirection,
        principal_id: UUID | None,
        agent_fqn: str,
        action: str,
        result: str,
        workspace_id: UUID | None,
        error_code: str | None = None,
        policy_decision: dict[str, Any] | None = None,
    ) -> A2AAuditRecord:
        record = await self.repository.create_audit_record(
            A2AAuditRecord(
                task_id=task.id if task is not None else None,
                direction=direction,
                principal_id=principal_id,
                agent_fqn=agent_fqn,
                action=action,
                result=result,
                policy_decision=policy_decision,
                workspace_id=workspace_id,
                error_code=error_code,
            )
        )
        audit_chain = build_audit_chain_service(self.session, self.settings)
        await audit_chain_hook(
            audit_chain,
            record.id,
            "a2a_gateway",
            {
                "task_id": record.task_id,
                "direction": record.direction.value,
                "principal_id": record.principal_id,
                "agent_fqn": record.agent_fqn,
                "action": record.action,
                "result": record.result,
                "policy_decision": record.policy_decision,
                "workspace_id": record.workspace_id,
                "error_code": record.error_code,
            },
        )
        return record

    def _validate_protocol(self, protocol_version: str | None) -> None:
        if protocol_version is None:
            return
        if protocol_version != self.settings.A2A_PROTOCOL_VERSION:
            raise A2AProtocolVersionError([self.settings.A2A_PROTOCOL_VERSION])

    def _validate_payload_size(self, request: A2ATaskSubmitRequest) -> None:
        payload_size = len(json.dumps(request.model_dump(mode="json")).encode("utf-8"))
        if payload_size > self.settings.A2A_MAX_PAYLOAD_BYTES:
            raise A2APayloadTooLargeError(self.settings.A2A_MAX_PAYLOAD_BYTES)

    def _principal_id(self, principal: dict[str, Any]) -> UUID:
        raw = principal.get("sub")
        if not isinstance(raw, str):
            raise A2AAuthenticationError()
        return UUID(raw)

    def _principal_can_access_workspace(
        self,
        principal: dict[str, Any],
        workspace_id: UUID,
    ) -> bool:
        if self._is_operator(principal):
            return True
        explicit_workspace = principal.get("workspace_id")
        if isinstance(explicit_workspace, str) and explicit_workspace == str(workspace_id):
            return True
        roles = principal.get("roles")
        if isinstance(roles, list):
            for role in roles:
                if not isinstance(role, dict):
                    continue
                role_workspace = role.get("workspace_id")
                if role_workspace in {None, str(workspace_id)}:
                    return True
        return explicit_workspace is None and not roles

    def _is_operator(self, principal: dict[str, Any]) -> bool:
        roles = principal.get("roles")
        if not isinstance(roles, list):
            return False
        operator_roles = {"owner", "admin", "platform_operator", "operator"}
        return any(isinstance(role, dict) and role.get("role") in operator_roles for role in roles)

    def _status_response(self, task: A2ATask) -> A2ATaskStatusResponse:
        return A2ATaskStatusResponse(
            task_id=task.task_id,
            a2a_state=task.a2a_state,
            agent_fqn=task.agent_fqn,
            result=task.result_payload,
            error_code=task.error_code,
            error_message=task.error_message,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )

    def _correlation(self, task: A2ATask) -> CorrelationContext:
        return CorrelationContext(
            workspace_id=task.workspace_id,
            conversation_id=task.conversation_id,
            interaction_id=task.interaction_id,
            agent_fqn=task.agent_fqn,
            correlation_id=uuid4(),
        )


def extract_text(message: dict[str, Any]) -> str:
    parts = message.get("parts", []) if isinstance(message, dict) else []
    texts: list[str] = []
    for part in parts:
        if (
            isinstance(part, dict)
            and part.get("type") == "text"
            and isinstance(part.get("text"), str)
        ):
            texts.append(part["text"])
    return "\n".join(texts).strip()


def replace_text(message: dict[str, Any], text: str) -> dict[str, Any]:
    payload = dict(message)
    parts = payload.get("parts")
    if not isinstance(parts, list) or not parts:
        payload["parts"] = [{"type": "text", "text": text}]
        return payload
    replaced = False
    new_parts: list[dict[str, Any]] = []
    for part in parts:
        if not replaced and isinstance(part, dict) and part.get("type") == "text":
            updated = dict(part)
            updated["text"] = text
            new_parts.append(updated)
            replaced = True
            continue
        if isinstance(part, dict):
            new_parts.append(dict(part))
        else:
            new_parts.append({"type": "text", "text": str(part)})
    payload["parts"] = new_parts
    return payload


def build_result_message(text: str) -> dict[str, Any]:
    return {"role": "agent", "parts": [{"type": "text", "text": text}]}


def build_prompt_message(text: str) -> dict[str, Any]:
    return {
        "role": "system",
        "parts": [{"type": "text", "text": text}],
        "prompt": text,
    }
