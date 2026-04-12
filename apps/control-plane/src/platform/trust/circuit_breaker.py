from __future__ import annotations

from pathlib import Path
from platform.interactions.events import AttentionRequestedPayload, publish_attention_requested
from platform.interactions.models import AttentionUrgency
from platform.trust.events import (
    CircuitBreakerActivatedPayload,
    TrustEventPublisher,
    make_correlation,
    utcnow,
)
from platform.trust.exceptions import CircuitBreakerTrippedError
from platform.trust.repository import TrustRepository
from platform.trust.schemas import (
    CircuitBreakerConfigCreate,
    CircuitBreakerConfigListResponse,
    CircuitBreakerConfigResponse,
    CircuitBreakerStatusResponse,
)
from typing import Any
from uuid import UUID, uuid4

SCRIPT_PATH = Path(__file__).resolve().parent / "lua" / "circuit_breaker_check.lua"


class CircuitBreakerService:
    def __init__(
        self,
        *,
        repository: TrustRepository,
        settings: Any,
        producer: Any | None,
        redis_client: Any,
        runtime_controller: Any | None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.events = TrustEventPublisher(producer)
        self.redis_client = redis_client
        self.runtime_controller = runtime_controller
        self._script_sha: str | None = None
        self._producer = producer

    async def load_script(self) -> None:
        await self.redis_client.initialize()
        client = self.redis_client.client
        assert client is not None
        self._script_sha = str(await client.script_load(SCRIPT_PATH.read_text(encoding="utf-8")))

    async def record_failure(
        self,
        agent_id: str,
        workspace_id: str,
        *,
        execution_id: str | None = None,
        fleet_id: str | None = None,
    ) -> CircuitBreakerStatusResponse:
        config = await self.repository.get_circuit_breaker_config(
            workspace_id=workspace_id,
            agent_id=agent_id,
            fleet_id=fleet_id,
        )
        threshold = int(config.failure_threshold if config is not None else 5)
        window_seconds = int(config.time_window_seconds if config is not None else 600)
        tripped_ttl = int(config.tripped_ttl_seconds if config is not None else 3600)
        await self.redis_client.initialize()
        client = self.redis_client.client
        assert client is not None
        if self._script_sha is None:
            await self.load_script()
        assert self._script_sha is not None
        try:
            result = await client.evalsha(
                self._script_sha,
                2,
                self._failures_key(agent_id),
                self._tripped_key(agent_id),
                threshold,
                window_seconds,
                tripped_ttl,
            )
        except Exception:
            result = await client.eval(
                SCRIPT_PATH.read_text(encoding="utf-8"),
                2,
                self._failures_key(agent_id),
                self._tripped_key(agent_id),
                threshold,
                window_seconds,
                tripped_ttl,
            )
        failure_count = int(result[0])
        tripped = bool(int(result[1]))
        status = CircuitBreakerStatusResponse(
            agent_id=agent_id,
            tripped=tripped,
            failure_count=failure_count,
            threshold=threshold,
            time_window_seconds=window_seconds,
        )
        if tripped:
            await self.events.publish_circuit_breaker_activated(
                CircuitBreakerActivatedPayload(
                    agent_id=agent_id,
                    workspace_id=workspace_id,
                    failure_count=failure_count,
                    threshold=threshold,
                    occurred_at=utcnow(),
                ),
                make_correlation(workspace_id=workspace_id, execution_id=execution_id),
            )
            await publish_attention_requested(
                self._producer,
                AttentionRequestedPayload(
                    request_id=uuid4(),
                    workspace_id=self._uuid_from_text(workspace_id),
                    source_agent_fqn=f"trust:circuit-breaker:{agent_id}",
                    target_identity=self._attention_target_identity,
                    urgency=AttentionUrgency.high,
                    related_interaction_id=None,
                    related_goal_id=None,
                ),
                make_correlation(workspace_id=workspace_id, execution_id=execution_id),
            )
            pauser = getattr(self.runtime_controller, "pause_workflow", None)
            if execution_id and pauser is not None:
                await pauser(execution_id, reason=f"trust circuit breaker tripped for {agent_id}")
        return status

    async def is_tripped(self, agent_id: str) -> bool:
        value = await self.redis_client.get(self._tripped_key(agent_id))
        return value is not None

    async def get_status(
        self,
        agent_id: str,
        workspace_id: str,
        *,
        fleet_id: str | None = None,
    ) -> CircuitBreakerStatusResponse:
        await self.redis_client.initialize()
        client = self.redis_client.client
        assert client is not None
        count = int(await client.zcard(self._failures_key(agent_id)))
        config = await self.repository.get_circuit_breaker_config(
            workspace_id=workspace_id,
            agent_id=agent_id,
            fleet_id=fleet_id,
        )
        return CircuitBreakerStatusResponse(
            agent_id=agent_id,
            tripped=await self.is_tripped(agent_id),
            failure_count=count,
            threshold=int(config.failure_threshold if config is not None else 5),
            time_window_seconds=int(config.time_window_seconds if config is not None else 600),
        )

    async def reset(self, agent_id: str) -> None:
        await self.redis_client.delete(self._failures_key(agent_id))
        await self.redis_client.delete(self._tripped_key(agent_id))

    async def ensure_not_tripped(self, agent_id: str) -> None:
        if await self.is_tripped(agent_id):
            raise CircuitBreakerTrippedError(agent_id)

    async def upsert_config(self, data: CircuitBreakerConfigCreate) -> CircuitBreakerConfigResponse:
        item = await self.repository.upsert_circuit_breaker_config(
            workspace_id=data.workspace_id,
            agent_id=data.agent_id,
            fleet_id=data.fleet_id,
            failure_threshold=data.failure_threshold,
            time_window_seconds=data.time_window_seconds,
            tripped_ttl_seconds=data.tripped_ttl_seconds,
            enabled=data.enabled,
        )
        return CircuitBreakerConfigResponse.model_validate(item)

    async def list_configs(self, workspace_id: str) -> CircuitBreakerConfigListResponse:
        items = await self.repository.list_circuit_breaker_configs(workspace_id)
        return CircuitBreakerConfigListResponse(
            items=[CircuitBreakerConfigResponse.model_validate(item) for item in items],
            total=len(items),
        )

    @property
    def _attention_target_identity(self) -> str:
        trust_settings = getattr(self.settings, "trust", None)
        return str(getattr(trust_settings, "attention_target_identity", "platform_admin"))

    @staticmethod
    def _failures_key(agent_id: str) -> str:
        return f"trust:cb:{agent_id}"

    @staticmethod
    def _tripped_key(agent_id: str) -> str:
        return f"trust:cb:tripped:{agent_id}"

    @staticmethod
    def _uuid_from_text(value: str | UUID) -> UUID:
        if isinstance(value, UUID):
            return value
        return UUID(str(value))
