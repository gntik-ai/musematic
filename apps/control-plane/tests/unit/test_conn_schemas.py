from __future__ import annotations

from platform.connectors.schemas import (
    ConnectorInstanceCreate,
    ConnectorInstanceResponse,
    ConnectorRouteCreate,
)
from uuid import uuid4

import pytest
from pydantic import ValidationError


def test_connector_instance_create_requires_ref_shape() -> None:
    payload = ConnectorInstanceCreate.model_validate(
        {
            "connector_type_slug": "slack",
            "name": "Slack",
            "config": {
                "team_id": "T1",
                "bot_token": {"$ref": "bot_token"},
                "signing_secret": {"$ref": "signing_secret"},
            },
            "credential_refs": {
                "bot_token": "vault/bot_token",
                "signing_secret": "vault/signing_secret",
            },
        }
    )

    assert payload.config["bot_token"] == {"$ref": "bot_token"}

    with pytest.raises(
        ValidationError,
        match=r"Credential references must only contain a '\$ref' field",
    ):
        ConnectorInstanceCreate.model_validate(
            {
                "connector_type_slug": "slack",
                "name": "Broken",
                "config": {"bot_token": {"$ref": "bot_token", "vault_path": "bad"}},
                "credential_refs": {"bot_token": "vault/bot_token"},
            }
        )


def test_connector_instance_response_masks_sensitive_config() -> None:
    response = ConnectorInstanceResponse(
        id=uuid4(),
        workspace_id=uuid4(),
        connector_type_id=uuid4(),
        connector_type_slug="slack",
        name="Slack",
        config={"bot_token": {"$ref": "bot_token"}, "api_key": "secret-value"},
        status="enabled",
        health_status="unknown",
        last_health_check_at=None,
        health_check_error=None,
        messages_sent=0,
        messages_failed=0,
        messages_retried=0,
        messages_dead_lettered=0,
        credential_keys=["bot_token"],
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )

    dumped = response.model_dump(mode="json")

    assert dumped["config"]["bot_token"] == {"$ref": "bot_token"}
    assert dumped["config"]["api_key"] == "[masked]"


def test_connector_route_create_requires_target() -> None:
    ConnectorRouteCreate.model_validate({"name": "To triage", "target_agent_fqn": "ops:triage"})

    with pytest.raises(
        ValidationError,
        match="At least one route target must be provided",
    ):
        ConnectorRouteCreate.model_validate({"name": "Broken"})
