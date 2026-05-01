from __future__ import annotations

from datetime import UTC, datetime
from platform.trust.contract_service import ContractService
from platform.trust.exceptions import ContractNotFoundError
from platform.trust.models import ContractTemplate
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest


class FakeTemplateRepository:
    def __init__(self, templates: list[SimpleNamespace]) -> None:
        self.templates = templates
        self.created_contracts: list[object] = []

    async def list_contract_templates(self) -> list[SimpleNamespace]:
        return [item for item in self.templates if item.is_published]

    async def get_contract_template(self, template_id: UUID) -> SimpleNamespace | None:
        for item in self.templates:
            if item.id == template_id:
                return item
        return None

    async def create_contract(self, contract: object) -> object:
        now = datetime.now(UTC)
        contract.id = uuid4()
        contract.created_at = now
        contract.updated_at = now
        self.created_contracts.append(contract)
        return contract


def _template(
    name: str,
    *,
    published: bool = True,
    platform_authored: bool = True,
) -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid4(),
        name=name,
        description=f"{name} description",
        category="customer-support",
        template_content={
            "task_scope": "Handle customer support safely",
            "expected_outputs": {"required": ["answer"]},
            "quality_thresholds": {"minimum_confidence": 0.7},
            "cost_limit_tokens": 500,
            "escalation_conditions": {"pii_detected": "escalate"},
            "success_criteria": {"must_include_citation": True},
            "enforcement_policy": "warn",
        },
        version_number=1,
        forked_from_template_id=None,
        created_by_user_id=None,
        is_platform_authored=platform_authored,
        is_published=published,
        created_at=now,
        updated_at=now,
    )


def _service(repository: FakeTemplateRepository) -> ContractService:
    return ContractService(
        repository=repository,  # type: ignore[arg-type]
        publisher=None,
    )


@pytest.mark.asyncio
async def test_list_templates_returns_published_platform_templates() -> None:
    templates = [_template(f"template-{index}") for index in range(5)]
    repository = FakeTemplateRepository(templates)

    response = await _service(repository).list_templates()

    assert response.total == 5
    assert all(item.is_platform_authored for item in response.items)
    assert {item.name for item in response.items} == {item.name for item in templates}


@pytest.mark.asyncio
async def test_fork_template_creates_editable_contract_with_attribution_metadata() -> None:
    template = _template("customer-support")
    repository = FakeTemplateRepository([template])
    workspace_id = uuid4()
    requester_id = uuid4()

    response = await _service(repository).fork_template(
        template.id,
        "finance:customer-support",
        workspace_id,
        requester_id,
    )

    assert response.workspace_id == workspace_id
    assert response.agent_id == "finance:customer-support"
    assert response.expected_outputs == {"required": ["answer"]}
    assert response.escalation_conditions is not None
    assert response.escalation_conditions["_forked_from_template_id"] == str(template.id)
    assert response.escalation_conditions["_forked_from_template_version"] == 1


@pytest.mark.asyncio
async def test_fork_template_rejects_unpublished_template() -> None:
    template = _template("draft", published=False)
    repository = FakeTemplateRepository([template])

    with pytest.raises(ContractNotFoundError):
        await _service(repository).fork_template(template.id, "draft-copy", uuid4(), uuid4())


def test_contract_template_forked_from_fk_sets_null_on_delete() -> None:
    foreign_keys = ContractTemplate.__table__.c.forked_from_template_id.foreign_keys

    assert any(fk.ondelete == "SET NULL" for fk in foreign_keys)
