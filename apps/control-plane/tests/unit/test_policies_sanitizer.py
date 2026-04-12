from __future__ import annotations

from platform.policies.models import EnforcementComponent
from uuid import uuid4

import pytest

from tests.policies_support import InMemoryPolicyRepository


@pytest.mark.asyncio
async def test_sanitizer_redacts_all_supported_secret_patterns() -> None:
    from platform.policies.sanitizer import OutputSanitizer

    repository = InMemoryPolicyRepository()
    sanitizer = OutputSanitizer(repository)
    result = await sanitizer.sanitize(
        (
            "Bearer abcdefghi sk-ABCDEFGH eyJabc.eyJdef.signature "
            "postgres://user:pass@db/name password=topsecret"
        ),
        agent_id=uuid4(),
        agent_fqn="finance:agent",
        tool_fqn="finance:exporter",
        execution_id=uuid4(),
        workspace_id=uuid4(),
    )

    assert result.redaction_count == 5
    assert set(result.redacted_types) == {
        "bearer_token",
        "api_key",
        "jwt_token",
        "connection_string",
        "password_literal",
    }
    assert "[REDACTED:bearer_token]" in result.output
    assert all(
        record.enforcement_component is EnforcementComponent.sanitizer
        for record in repository.blocked_records.values()
    )
    assert all(
        "topsecret" not in str(record.policy_rule_ref)
        for record in repository.blocked_records.values()
    )


@pytest.mark.asyncio
async def test_sanitizer_passes_clean_output_unchanged() -> None:
    from platform.policies.sanitizer import OutputSanitizer

    repository = InMemoryPolicyRepository()
    sanitizer = OutputSanitizer(repository)
    result = await sanitizer.sanitize(
        "nothing sensitive here",
        agent_id=uuid4(),
        agent_fqn="finance:agent",
        tool_fqn="finance:exporter",
        execution_id=None,
        workspace_id=None,
    )

    assert result.output == "nothing sensitive here"
    assert result.redaction_count == 0
    assert result.redacted_types == []
    assert repository.blocked_records == {}
