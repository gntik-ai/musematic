from __future__ import annotations

from platform.audit.dependencies import build_audit_chain_service
from platform.audit.service import AuditChainService
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.localization.repository import LocalizationRepository
from platform.localization.service import LocalizationService
from platform.localization.services.locale_file_service import LocaleFileService
from platform.localization.services.locale_resolver import LocaleResolver
from platform.localization.services.preferences_service import PreferencesService
from platform.workspaces.dependencies import get_workspaces_service
from platform.workspaces.service import WorkspacesService
from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def _get_settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _get_producer(request: Request) -> EventProducer | None:
    return cast(EventProducer | None, request.app.state.clients.get("kafka"))


def build_preferences_service(
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    audit_chain: AuditChainService | None,
    workspaces_service: WorkspacesService | None,
) -> PreferencesService:
    del settings
    return PreferencesService(
        LocalizationRepository(session),
        audit_chain=audit_chain,
        producer=producer,
        workspaces_service=workspaces_service,
    )


def build_locale_file_service(
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    audit_chain: AuditChainService | None,
) -> LocaleFileService:
    return LocaleFileService(
        LocalizationRepository(session),
        audit_chain=audit_chain,
        producer=producer,
        lru_size=settings.localization.localization_locale_lru_size,
    )


def build_locale_resolver(settings: PlatformSettings) -> LocaleResolver:
    return LocaleResolver(tuple(settings.localization.localization_supported_locales))


def build_localization_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    audit_chain: AuditChainService | None,
    workspaces_service: WorkspacesService | None,
) -> LocalizationService:
    return LocalizationService(
        build_preferences_service(
            session,
            settings,
            producer,
            audit_chain,
            workspaces_service,
        ),
        build_locale_file_service(session, settings, producer, audit_chain),
        build_locale_resolver(settings),
    )


async def get_preferences_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> PreferencesService:
    settings = _get_settings(request)
    producer = _get_producer(request)
    return build_preferences_service(
        session,
        settings,
        producer,
        build_audit_chain_service(session, settings, producer),
        workspaces_service,
    )


async def get_locale_file_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> LocaleFileService:
    settings = _get_settings(request)
    producer = _get_producer(request)
    return build_locale_file_service(
        session,
        settings,
        producer,
        build_audit_chain_service(session, settings, producer),
    )


async def get_locale_resolver(request: Request) -> LocaleResolver:
    return build_locale_resolver(_get_settings(request))


async def get_localization_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> LocalizationService:
    settings = _get_settings(request)
    producer = _get_producer(request)
    return build_localization_service(
        session=session,
        settings=settings,
        producer=producer,
        audit_chain=build_audit_chain_service(session, settings, producer),
        workspaces_service=workspaces_service,
    )

