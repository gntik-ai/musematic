from __future__ import annotations

from platform.privacy_compliance.events import PrivacyEventPublisher
from platform.privacy_compliance.exceptions import ResidencyViolation
from platform.privacy_compliance.models import PrivacyResidencyConfig
from platform.privacy_compliance.services.residency_service import ResidencyService
from uuid import uuid4

import pytest


class Repo:
    def __init__(self, config=None) -> None:
        self.config = config

    async def get_residency_config(self, workspace_id):
        del workspace_id
        return self.config

    async def upsert_residency_config(self, **kwargs):
        self.config = PrivacyResidencyConfig(id=uuid4(), **kwargs)
        return self.config

    async def delete_residency_config(self, workspace_id):
        del workspace_id
        self.config = None
        return True


@pytest.mark.asyncio
async def test_residency_enforcement_allows_home_and_transfer_regions() -> None:
    workspace_id = uuid4()
    service = ResidencyService(
        repository=Repo(
            PrivacyResidencyConfig(
                id=uuid4(),
                workspace_id=workspace_id,
                region_code="eu-central-1",
                allowed_transfer_regions=["eu-west-1"],
            )
        ),
        event_publisher=PrivacyEventPublisher(None),
    )

    await service.enforce(workspace_id, "eu-central-1")
    await service.enforce(workspace_id, "eu-west-1")
    with pytest.raises(ResidencyViolation):
        await service.enforce(workspace_id, "us-east-1")

