from __future__ import annotations

from platform.common.tagging.exceptions import LabelExpressionSyntaxError
from platform.policies.models import PolicyScopeType
from platform.policies.schemas import PolicyRulesSchema
from platform.policies.service import PolicyService
from uuid import uuid4

import pytest
from tests.auth_support import RecordingProducer
from tests.policies_support import (
    InMemoryPolicyRepository,
    WorkspacesPolicyStub,
    build_fake_redis,
    build_policy_create,
    build_policy_settings,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_malformed_label_expression_save_is_refused_without_persisting_policy() -> None:
    workspace_id = uuid4()
    repository = InMemoryPolicyRepository()
    _memory, redis_client = build_fake_redis()
    service = PolicyService(
        repository=repository,
        settings=build_policy_settings(),
        producer=RecordingProducer(),
        redis_client=redis_client,
        registry_service=None,
        workspaces_service=WorkspacesPolicyStub(workspace_ids={workspace_id}),
    )

    with pytest.raises(LabelExpressionSyntaxError) as exc_info:
        await service.create_policy(
            build_policy_create(
                scope_type=PolicyScopeType.workspace,
                workspace_id=workspace_id,
                rules=PolicyRulesSchema(label_expression="env=production AND"),
            ),
            created_by=uuid4(),
        )

    assert repository.policies == {}
    assert repository.versions_by_policy == {}
    assert exc_info.value.line == 1
    assert exc_info.value.col > 0
    assert exc_info.value.token
    assert exc_info.value.message
