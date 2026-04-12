from __future__ import annotations

import re
from platform.policies.models import EnforcementComponent, PolicyBlockedActionRecord
from platform.policies.repository import PolicyRepository
from platform.policies.schemas import SanitizationResult
from typing import ClassVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


class OutputSanitizer:
    SECRET_PATTERNS: ClassVar[dict[str, re.Pattern[str]]] = {
        "bearer_token": re.compile(r"Bearer\s+[A-Za-z0-9._\-]{8,}"),
        "api_key": re.compile(r"\b(?:sk-|key-)[A-Za-z0-9]{8,}\b"),
        "jwt_token": re.compile(r"eyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"),
        "connection_string": re.compile(
            r"(?:postgres|mysql|mongodb|redis|amqp)://[^@\s]+@[^/\s]+(?:/[^\s]*)?"
        ),
        "password_literal": re.compile(r"(?i)(?:password|passwd|pwd)\s*[=:]\s*\S+"),
    }

    def __init__(self, repository: PolicyRepository) -> None:
        self.repository = repository

    async def sanitize(
        self,
        output: str,
        *,
        agent_id: UUID,
        agent_fqn: str,
        tool_fqn: str,
        execution_id: UUID | None,
        workspace_id: UUID | None,
        session: AsyncSession | None = None,
    ) -> SanitizationResult:
        del session
        sanitized = output
        redacted_types: list[str] = []
        redaction_count = 0

        for secret_type, pattern in self.SECRET_PATTERNS.items():
            matches = list(pattern.finditer(sanitized))
            if not matches:
                continue
            sanitized = pattern.sub(f"[REDACTED:{secret_type}]", sanitized)
            redacted_types.append(secret_type)
            redaction_count += len(matches)
            for _ in matches:
                await self.repository.create_blocked_action_record(
                    PolicyBlockedActionRecord(
                        agent_id=agent_id,
                        agent_fqn=agent_fqn,
                        enforcement_component=EnforcementComponent.sanitizer,
                        action_type="sanitizer_redaction",
                        target=secret_type,
                        block_reason="secret_pattern_detected",
                        policy_rule_ref={"tool_fqn": tool_fqn},
                        execution_id=execution_id,
                        workspace_id=workspace_id,
                    )
                )

        return SanitizationResult(
            output=sanitized,
            redaction_count=redaction_count,
            redacted_types=redacted_types,
        )
