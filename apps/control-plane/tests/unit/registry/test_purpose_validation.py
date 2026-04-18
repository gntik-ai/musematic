from __future__ import annotations

from platform.registry.schemas import AgentManifest

import pytest
from pydantic import ValidationError


def _manifest_payload(purpose: str) -> dict[str, object]:
    return {
        "local_name": "finance-runner",
        "version": "1.2.3",
        "purpose": purpose,
        "role_types": ["executor"],
    }


def test_manifest_purpose_too_short() -> None:
    with pytest.raises(ValidationError):
        AgentManifest.model_validate(_manifest_payload("A" * 49))


def test_manifest_purpose_exactly_50() -> None:
    manifest = AgentManifest.model_validate(_manifest_payload("A" * 50))

    assert manifest.purpose == "A" * 50


def test_manifest_purpose_above_50() -> None:
    manifest = AgentManifest.model_validate(_manifest_payload("A" * 100))

    assert manifest.purpose == "A" * 100


def test_manifest_purpose_old_min_rejected() -> None:
    with pytest.raises(ValidationError):
        AgentManifest.model_validate(_manifest_payload("A" * 10))
