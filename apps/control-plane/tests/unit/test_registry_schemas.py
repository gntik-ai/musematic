from __future__ import annotations

from platform.registry.schemas import AgentDiscoveryParams, AgentManifest, AgentPatch

import pytest
from pydantic import ValidationError


def test_agent_manifest_validation_and_normalization() -> None:
    manifest = AgentManifest.model_validate(
        {
            "local_name": "finance-runner",
            "version": "1.2.3",
            "purpose": "  Routes finance workflows with deterministic execution guarantees.  ",
            "role_types": ["custom"],
            "custom_role_description": "Owns the full execution chain.",
            "tags": [" finance ", "", "ops"],
            "reasoning_modes": [" chain ", " ", "tool"],
            "display_name": "  Finance Runner  ",
        }
    )

    assert manifest.purpose == "Routes finance workflows with deterministic execution guarantees."
    assert manifest.tags == ["finance", "ops"]
    assert manifest.reasoning_modes == ["chain", "tool"]
    assert manifest.display_name == "Finance Runner"


@pytest.mark.parametrize(
    "payload",
    [
        {
            "local_name": "BadSlug",
            "version": "1.2.3",
            "purpose": "A" * 60,
            "role_types": ["executor"],
        },
        {
            "local_name": "good-slug",
            "version": "1.2",
            "purpose": "A" * 60,
            "role_types": ["executor"],
        },
        {
            "local_name": "good-slug",
            "version": "1.2.3",
            "purpose": "A" * 60,
            "role_types": ["custom"],
        },
    ],
)
def test_agent_manifest_rejects_invalid_payloads(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        AgentManifest.model_validate(payload)


def test_discovery_params_and_patch_defaults() -> None:
    params = AgentDiscoveryParams.model_validate({})
    patch = AgentPatch.model_validate(
        {
            "display_name": "  Registry  ",
            "tags": [" finance ", "", "ops"],
            "visibility_agents": ["finance:*", ""],
        }
    )

    assert params.status.value == "published"
    assert params.maturity_min == 0
    assert params.limit == 20
    assert params.offset == 0
    assert patch.display_name == "Registry"
    assert patch.tags == ["finance", "ops"]
    assert patch.visibility_agents == ["finance:*"]


def test_patch_requires_custom_role_description_when_custom_role_present() -> None:
    with pytest.raises(ValidationError):
        AgentPatch.model_validate({"role_types": ["custom"]})
