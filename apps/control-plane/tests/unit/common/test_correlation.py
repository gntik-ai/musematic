from __future__ import annotations

import asyncio
from platform.common.correlation import CorrelationMiddleware, goal_id_var
from uuid import UUID, uuid4

import httpx
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route


def _app(invoked: list[bool]) -> Starlette:
    async def probe(request: Request) -> JSONResponse:
        invoked.append(True)
        delay = float(request.query_params.get("delay", "0") or "0")
        if delay:
            await asyncio.sleep(delay)
        return JSONResponse(
            {
                "goal_id": goal_id_var.get(),
                "state_goal_id": getattr(request.state, "goal_id", None),
            }
        )

    app = Starlette(routes=[Route("/probe", probe)])
    app.add_middleware(CorrelationMiddleware)
    return app


@pytest.mark.asyncio
async def test_x_goal_id_valid_uuid_sets_context_var() -> None:
    invoked: list[bool] = []
    goal_id = uuid4()
    app = _app(invoked)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/probe", headers={"X-Goal-Id": str(goal_id)})

    assert invoked == [True]
    assert response.status_code == 200
    assert response.json() == {
        "goal_id": str(goal_id),
        "state_goal_id": str(goal_id),
    }
    assert response.headers["X-Goal-Id"] == str(goal_id)


@pytest.mark.asyncio
async def test_x_goal_id_invalid_uuid_returns_422() -> None:
    invoked: list[bool] = []
    app = _app(invoked)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/probe", headers={"X-Goal-Id": "not-a-uuid"})

    assert invoked == []
    assert response.status_code == 422
    assert response.json() == {"error": "invalid X-Goal-Id header"}


@pytest.mark.asyncio
async def test_x_goal_id_absent_is_noop() -> None:
    invoked: list[bool] = []
    app = _app(invoked)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/probe")

    assert invoked == [True]
    assert response.status_code == 200
    assert response.json() == {"goal_id": "", "state_goal_id": None}
    assert "X-Goal-Id" not in response.headers


@pytest.mark.asyncio
async def test_x_goal_id_empty_string_treated_as_absent() -> None:
    invoked: list[bool] = []
    app = _app(invoked)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/probe", headers={"X-Goal-Id": "   "})

    assert invoked == [True]
    assert response.status_code == 200
    assert response.json() == {"goal_id": "", "state_goal_id": None}
    assert "X-Goal-Id" not in response.headers


@pytest.mark.asyncio
async def test_concurrent_requests_do_not_share_goal_id() -> None:
    invoked: list[bool] = []
    first_goal_id = uuid4()
    second_goal_id = uuid4()
    app = _app(invoked)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        first, second = await asyncio.gather(
            client.get("/probe?delay=0.05", headers={"X-Goal-Id": str(first_goal_id)}),
            client.get("/probe?delay=0.01", headers={"X-Goal-Id": str(second_goal_id)}),
        )

    assert invoked == [True, True]
    assert {
        UUID(first.json()["goal_id"]),
        UUID(second.json()["goal_id"]),
    } == {first_goal_id, second_goal_id}
    assert first.json()["state_goal_id"] == str(first_goal_id)
    assert second.json()["state_goal_id"] == str(second_goal_id)
