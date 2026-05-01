from __future__ import annotations

from datetime import UTC, datetime
from platform.common.exceptions import AuthorizationError, ValidationError
from platform.trust.contract_service import ContractService
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest


class FakeAttachRepository:
    def __init__(
        self,
        contract: SimpleNamespace,
        revision: SimpleNamespace,
        profile: SimpleNamespace,
    ) -> None:
        self.contract = contract
        self.revision = revision
        self.profile = profile
        self.updates: list[tuple[UUID, dict[str, object]]] = []

    async def get_contract(self, contract_id: UUID) -> SimpleNamespace | None:
        if contract_id == self.contract.id:
            return self.contract
        return None

    async def get_agent_revision_with_profile(
        self,
        revision_id: UUID,
    ) -> tuple[SimpleNamespace, SimpleNamespace] | None:
        if revision_id == self.revision.id:
            return self.revision, self.profile
        return None

    async def update_contract(
        self,
        contract_id: UUID,
        data: dict[str, object],
    ) -> SimpleNamespace:
        self.updates.append((contract_id, data))
        for key, value in data.items():
            setattr(self.contract, key, value)
        return self.contract


def _contract(workspace_id: UUID, agent_id: str = "finance:kyc") -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid4(),
        workspace_id=workspace_id,
        agent_id=agent_id,
        is_archived=False,
        attached_revision_id=None,
        created_at=now,
        updated_at=now,
    )


def _repository(
    workspace_id: UUID,
    *,
    contract_agent_id: str = "finance:kyc",
    profile_fqn: str = "finance:kyc",
) -> FakeAttachRepository:
    contract = _contract(workspace_id, contract_agent_id)
    revision = SimpleNamespace(id=uuid4(), workspace_id=workspace_id)
    profile = SimpleNamespace(id=uuid4(), fqn=profile_fqn)
    return FakeAttachRepository(contract, revision, profile)


def _service(repository: FakeAttachRepository) -> ContractService:
    return ContractService(
        repository=repository,  # type: ignore[arg-type]
        publisher=None,
    )


@pytest.mark.asyncio
async def test_attach_to_revision_sets_attached_revision_id() -> None:
    workspace_id = uuid4()
    repository = _repository(workspace_id)
    requester_id = uuid4()

    await _service(repository).attach_to_revision(
        repository.contract.id,
        repository.revision.id,
        requester_id,
        workspace_id=workspace_id,
    )

    assert repository.contract.attached_revision_id == repository.revision.id
    assert repository.updates == [
        (
            repository.contract.id,
            {"attached_revision_id": repository.revision.id, "updated_by": requester_id},
        )
    ]


@pytest.mark.asyncio
async def test_attach_to_revision_allows_reattach_overwrite() -> None:
    workspace_id = uuid4()
    repository = _repository(workspace_id)
    requester_id = uuid4()
    service = _service(repository)
    first_revision_id = repository.revision.id
    second_revision_id = uuid4()

    await service.attach_to_revision(
        repository.contract.id,
        first_revision_id,
        requester_id,
        workspace_id=workspace_id,
    )
    repository.revision.id = second_revision_id
    await service.attach_to_revision(
        repository.contract.id,
        second_revision_id,
        requester_id,
        workspace_id=workspace_id,
    )

    assert repository.contract.attached_revision_id == second_revision_id
    assert [update[1]["attached_revision_id"] for update in repository.updates] == [
        first_revision_id,
        second_revision_id,
    ]


@pytest.mark.asyncio
async def test_attach_to_revision_rejects_workspace_mismatch() -> None:
    workspace_id = uuid4()
    repository = _repository(workspace_id)
    repository.revision.workspace_id = uuid4()

    with pytest.raises(AuthorizationError):
        await _service(repository).attach_to_revision(
            repository.contract.id,
            repository.revision.id,
            uuid4(),
            workspace_id=workspace_id,
        )


@pytest.mark.asyncio
async def test_attach_to_revision_rejects_agent_mismatch() -> None:
    workspace_id = uuid4()
    repository = _repository(workspace_id, contract_agent_id="finance:other")

    with pytest.raises(ValidationError):
        await _service(repository).attach_to_revision(
            repository.contract.id,
            repository.revision.id,
            uuid4(),
            workspace_id=workspace_id,
        )


@pytest.mark.asyncio
async def test_attach_to_revision_rejects_archived_contract() -> None:
    workspace_id = uuid4()
    repository = _repository(workspace_id)
    repository.contract.is_archived = True

    with pytest.raises(ValidationError):
        await _service(repository).attach_to_revision(
            repository.contract.id,
            repository.revision.id,
            uuid4(),
            workspace_id=workspace_id,
        )
