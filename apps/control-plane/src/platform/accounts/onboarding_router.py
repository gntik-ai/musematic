"""Default-tenant onboarding router for UPD-048 FR-024 through FR-031."""

from __future__ import annotations

from platform.accounts.onboarding import OnboardingWizardService
from platform.accounts.schemas import (
    OnboardingStateView,
    OnboardingStepFirstAgent,
    OnboardingStepInvitations,
    OnboardingStepTour,
    OnboardingStepWorkspaceName,
)
from platform.audit.dependencies import build_audit_chain_service
from platform.common import database
from platform.common.config import PlatformSettings
from platform.common.config import settings as default_settings
from platform.common.dependencies import get_current_user
from platform.common.events.producer import EventProducer
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/onboarding", tags=["onboarding"])


@router.get("/state", response_model=OnboardingStateView)
async def get_state(
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(database.get_session),
) -> OnboardingStateView:
    return await _service(request, session).get_or_create_state(_user_id(current_user))


@router.post("/step/workspace-name")
async def step_workspace_name(
    payload: OnboardingStepWorkspaceName,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(database.get_session),
) -> dict[str, object]:
    return await _service(request, session).advance_step(
        _user_id(current_user),
        "workspace-name",
        payload,
    )


@router.post("/step/invitations")
async def step_invitations(
    payload: OnboardingStepInvitations,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(database.get_session),
) -> dict[str, object]:
    return await _service(request, session).advance_step(
        _user_id(current_user),
        "invitations",
        payload,
    )


@router.post("/step/first-agent")
async def step_first_agent(
    payload: OnboardingStepFirstAgent,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(database.get_session),
) -> dict[str, object]:
    return await _service(request, session).advance_step(
        _user_id(current_user),
        "first-agent",
        payload,
    )


@router.post("/step/tour")
async def step_tour(
    payload: OnboardingStepTour,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(database.get_session),
) -> dict[str, object]:
    return await _service(request, session).advance_step(
        _user_id(current_user),
        "tour",
        payload,
    )


@router.post("/dismiss")
async def dismiss(
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(database.get_session),
) -> dict[str, object]:
    return await _service(request, session).dismiss(_user_id(current_user))


@router.post("/relaunch", response_model=OnboardingStateView)
async def relaunch(
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(database.get_session),
) -> OnboardingStateView:
    return await _service(request, session).relaunch(_user_id(current_user))


def _service(request: Request, session: AsyncSession) -> OnboardingWizardService:
    settings = _settings(request)
    producer = _producer(request)
    return OnboardingWizardService(
        session=session,
        settings=settings,
        producer=producer,
        audit_chain=build_audit_chain_service(session, settings, producer),
    )


def _user_id(current_user: dict[str, Any]) -> UUID:
    return UUID(str(current_user["sub"]))


def _settings(request: Request) -> PlatformSettings:
    value = getattr(request.app.state, "settings", None)
    return value if isinstance(value, PlatformSettings) else default_settings


def _producer(request: Request) -> EventProducer | None:
    clients = getattr(request.app.state, "clients", {})
    producer = clients.get("kafka") if isinstance(clients, dict) else None
    return producer if isinstance(producer, EventProducer) else None
