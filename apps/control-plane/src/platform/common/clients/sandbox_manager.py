from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from importlib import import_module
from platform.common.config import PlatformSettings, Settings
from platform.common.config import settings as default_settings
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class SandboxExecutionResult:
    execution_id: str
    status: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    artifacts: list[dict[str, Any]] = field(default_factory=list)


class SandboxManagerClient:
    def __init__(self, target: str | None = None, settings: Settings | None = None) -> None:
        self.settings = settings or default_settings
        self.target = target or self.settings.GRPC_SANDBOX_MANAGER
        self.channel: Any | None = None
        self.stub: Any | None = None

    @classmethod
    def from_settings(cls, settings: PlatformSettings) -> SandboxManagerClient:
        return cls(settings=settings)

    async def connect(self) -> None:
        if self.channel is not None:
            return
        grpc = import_module("grpc")
        self.channel = grpc.aio.insecure_channel(self.target)
        self.stub = self.channel

    async def close(self) -> None:
        if self.channel is None:
            return
        close = getattr(self.channel, "close", None)
        if close is not None:
            result = close()
            if hasattr(result, "__await__"):
                await result
        self.channel = None
        self.stub = None

    async def health_check(self) -> bool:
        try:
            await self.connect()
            state_fn = getattr(self.channel, "get_state", None)
            if state_fn is None:
                return True
            state = state_fn(try_to_connect=True)
            return "SHUTDOWN" not in str(state)
        except Exception:
            return False

    async def execute_code(
        self,
        template: str,
        code: str,
        workspace_id: UUID,
        timeout_seconds: int,
    ) -> SandboxExecutionResult:
        """Execute code through sandbox-manager when an RPC stub is available.

        The repository currently does not include generated sandbox protobufs, so
        this wrapper is intentionally tolerant: tests can attach a stub exposing
        ExecuteCode, while local/dev mode returns a deterministic queued result.
        """
        await self.connect()
        execute = getattr(self.stub, "ExecuteCode", None)
        if execute is None:
            return SandboxExecutionResult(
                execution_id=str(uuid.uuid4()),
                status="queued",
                stdout="",
                stderr="sandbox manager ExecuteCode RPC is not available",
                exit_code=None,
                artifacts=[],
            )
        request = {
            "template": template,
            "code": code,
            "workspace_id": str(workspace_id),
            "timeout_seconds": timeout_seconds,
        }
        response = execute(request)
        if hasattr(response, "__await__"):
            response = await response
        if isinstance(response, SandboxExecutionResult):
            return response
        if isinstance(response, dict):
            return SandboxExecutionResult(
                execution_id=str(response.get("execution_id") or uuid.uuid4()),
                status=str(response.get("status") or "completed"),
                stdout=str(response.get("stdout") or ""),
                stderr=str(response.get("stderr") or ""),
                exit_code=response.get("exit_code"),
                artifacts=list(response.get("artifacts") or []),
            )
        return SandboxExecutionResult(
            execution_id=str(getattr(response, "execution_id", uuid.uuid4())),
            status=str(getattr(response, "status", "completed")),
            stdout=str(getattr(response, "stdout", "")),
            stderr=str(getattr(response, "stderr", "")),
            exit_code=getattr(response, "exit_code", None),
            artifacts=list(getattr(response, "artifacts", []) or []),
        )
