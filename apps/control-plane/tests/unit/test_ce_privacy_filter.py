from __future__ import annotations

from platform.context_engineering.privacy_filter import PrivacyFilter
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.context_engineering_support import PoliciesServiceStub, build_element


@pytest.mark.asyncio
async def test_privacy_filter_excludes_unauthorized_elements_and_caches_policy_reads() -> None:
    workspace_id = uuid4()
    policies = PoliciesServiceStub(
        policies=[
            {
                "policy_id": "policy-1",
                "allowed_agent_fqns": ["finance:agent"],
                "allowed_classifications": ["public", "internal"],
            }
        ]
    )
    filter_ = PrivacyFilter(policies_service=policies, cache_ttl_seconds=60)
    elements = [
        build_element(data_classification="public"),
        build_element(data_classification="confidential", origin="memory:secret"),
    ]

    allowed, exclusions = await filter_.filter(elements, "finance:agent", workspace_id)
    allowed_again, _ = await filter_.filter(elements, "finance:agent", workspace_id)

    assert len(allowed) == 1
    assert len(allowed_again) == 1
    assert exclusions[0]["policy_id"] == "policy-1"
    assert len(policies.calls) == 1


@pytest.mark.asyncio
async def test_privacy_filter_allows_all_without_policy_service_and_respects_overrides() -> None:
    filter_ = PrivacyFilter(policies_service=None)
    elements = [
        build_element(data_classification="restricted"),
        build_element(data_classification="public"),
    ]

    allowed, exclusions = await filter_.filter(
        elements,
        "finance:agent",
        uuid4(),
        privacy_overrides={"excluded_source_types": ["conversation_history"]},
    )

    assert len(allowed) == 0
    assert len(exclusions) == 2


@pytest.mark.asyncio
async def test_privacy_filter_explicit_levels_and_helper_fallbacks() -> None:
    workspace_id = uuid4()
    filter_ = PrivacyFilter(
        policies_service=PoliciesServiceStub(
            policies=[
                SimpleNamespace(
                    id="policy-2",
                    allowed_agent_fqns=["other:agent"],
                    action="include",
                    classification="internal",
                )
            ]
        )
    )
    elements = [
        build_element(data_classification="restricted"),
        build_element(data_classification="public", origin="conversation:2"),
    ]

    allowed, exclusions = await filter_.filter(
        elements,
        "finance:agent",
        workspace_id,
        privacy_overrides={"allowed_classifications": ["restricted"]},
    )
    _, policy_exclusions = await filter_.filter(
        elements,
        "finance:agent",
        workspace_id,
    )

    assert len(allowed) == 2
    assert policy_exclusions[0]["policy_id"] == "policy-2"
    assert exclusions == []
    assert filter_._is_rank_allowed("public", {"unknown"}) is True
    assert filter_._first_policy_id([SimpleNamespace(id="policy-3")]) == "policy-3"
    assert filter_._string_list(SimpleNamespace(values="bad"), "values") == []
    assert filter_._get(SimpleNamespace(value="x"), "value") == "x"
