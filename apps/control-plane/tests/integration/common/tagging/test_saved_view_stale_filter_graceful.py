from __future__ import annotations

from platform.common.tagging.filter_extension import TagLabelFilterParams
from platform.common.tagging.label_service import LabelService
from platform.common.tagging.listing import resolve_filtered_entity_ids
from platform.common.tagging.saved_view_service import SavedViewService
from uuid import uuid4

import pytest
from tests.integration.common.tagging.support import InMemoryTaggingRepository, requester

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_saved_view_with_stale_label_filter_applies_as_empty_result() -> None:
    repo = InMemoryTaggingRepository()
    workspace_id = uuid4()
    owner_id = uuid4()
    entity_id = uuid4()
    saved_views = SavedViewService(repo)
    labels = LabelService(repo)
    view = await saved_views.create(
        requester=requester(owner_id),
        workspace_id=workspace_id,
        name="Finance ops",
        entity_type="agent",
        filters={"label.team": "finance-ops"},
        shared=False,
    )

    result = await resolve_filtered_entity_ids(
        entity_type="agent",
        visible_entity_ids={entity_id},
        filters=TagLabelFilterParams(labels={"team": "finance-ops"}),
        tag_service=None,
        label_service=labels,
    )

    assert result == set()
    assert (await saved_views.get(view.id, requester(owner_id))).id == view.id
