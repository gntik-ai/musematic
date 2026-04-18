from __future__ import annotations

import json

import httpx
import pytest
import yaml

from tests.trust_support import admin_user, build_rule_set_create, build_trust_app


def make_transport(app):
    return httpx.ASGITransport(app=app)


@pytest.mark.asyncio
async def test_prescreener_rule_set_endpoint_accepts_yaml_payloads() -> None:
    app, _bundle = build_trust_app(current_user=admin_user())
    payload = build_rule_set_create().model_dump(mode="json")

    async with httpx.AsyncClient(
        transport=make_transport(app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/trust/prescreener/rule-sets",
            content=yaml.safe_dump(payload),
            headers={"content-type": "application/yaml"},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == payload["name"]
    assert body["rule_count"] == len(payload["rules"])


@pytest.mark.asyncio
async def test_prescreener_rule_set_endpoint_still_accepts_json_payloads() -> None:
    app, _bundle = build_trust_app(current_user=admin_user())
    payload = build_rule_set_create().model_dump(mode="json")

    async with httpx.AsyncClient(
        transport=make_transport(app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/trust/prescreener/rule-sets",
            content=json.dumps(payload),
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == payload["name"]
    assert body["rule_count"] == len(payload["rules"])


@pytest.mark.asyncio
async def test_prescreener_rule_set_endpoint_rejects_malformed_yaml() -> None:
    app, _bundle = build_trust_app(current_user=admin_user())

    async with httpx.AsyncClient(
        transport=make_transport(app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/trust/prescreener/rule-sets",
            content="name: [unterminated",
            headers={"content-type": "application/yaml"},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "YAML_PARSE_ERROR"


@pytest.mark.asyncio
async def test_prescreener_yaml_and_json_payloads_produce_equivalent_rule_counts() -> None:
    app, _bundle = build_trust_app(current_user=admin_user())
    payload = build_rule_set_create().model_dump(mode="json")

    async with httpx.AsyncClient(
        transport=make_transport(app),
        base_url="http://testserver",
    ) as client:
        yaml_response = await client.post(
            "/api/v1/trust/prescreener/rule-sets",
            content=yaml.safe_dump(payload),
            headers={"content-type": "application/yaml"},
        )
        json_response = await client.post(
            "/api/v1/trust/prescreener/rule-sets",
            content=json.dumps({**payload, "name": "default-json"}),
            headers={"content-type": "application/json"},
        )

    assert yaml_response.status_code == 201
    assert json_response.status_code == 201
    assert yaml_response.json()["rule_count"] == json_response.json()["rule_count"]
