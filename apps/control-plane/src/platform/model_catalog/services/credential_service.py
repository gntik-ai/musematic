from __future__ import annotations

from datetime import UTC, datetime
from platform.common.exceptions import AuthorizationError, NotFoundError, ValidationError
from platform.model_catalog.models import ModelProviderCredential
from platform.model_catalog.repository import ModelCatalogRepository
from platform.model_catalog.schemas import (
    CredentialCreate,
    CredentialListResponse,
    CredentialResponse,
    CredentialRotateRequest,
    CredentialRotateResponse,
)
from platform.security_compliance.services.secret_rotation_service import SecretRotationService
from typing import Protocol
from uuid import UUID


class SecretReader(Protocol):
    async def get(self, path: str, key: str = "value") -> str: ...


class CredentialService:
    def __init__(
        self,
        repository: ModelCatalogRepository,
        *,
        secret_reader: SecretReader | None = None,
        rotation_service: SecretRotationService | None = None,
    ) -> None:
        self.repository = repository
        self.secret_reader = secret_reader
        self.rotation_service = rotation_service

    async def register_credential(self, request: CredentialCreate) -> CredentialResponse:
        await self._verify_vault_ref(request.vault_ref)
        existing = await self.repository.get_credential_by_workspace_provider(
            request.workspace_id,
            request.provider,
        )
        if existing is not None:
            raise ValidationError(
                "MODEL_PROVIDER_CREDENTIAL_DUPLICATE",
                "Credential already exists for this workspace and provider.",
            )
        credential = await self.repository.add(
            ModelProviderCredential(
                workspace_id=request.workspace_id,
                provider=request.provider,
                vault_ref=request.vault_ref,
            )
        )
        return CredentialResponse.model_validate(credential)

    async def get_by_workspace_provider(
        self,
        workspace_id: UUID,
        provider: str,
    ) -> CredentialResponse:
        credential = await self.repository.get_credential_by_workspace_provider(
            workspace_id,
            provider,
        )
        if credential is None:
            raise NotFoundError(
                "MODEL_PROVIDER_CREDENTIAL_NOT_FOUND",
                "Provider credential not found",
            )
        return CredentialResponse.model_validate(credential)

    async def list_credentials(
        self,
        *,
        workspace_id: UUID | None = None,
        provider: str | None = None,
    ) -> CredentialListResponse:
        items = await self.repository.list_credentials(workspace_id=workspace_id, provider=provider)
        return CredentialListResponse(
            items=[CredentialResponse.model_validate(item) for item in items],
            total=len(items),
        )

    async def update_vault_ref(self, credential_id: UUID, vault_ref: str) -> CredentialResponse:
        credential = await self._get(credential_id)
        await self._verify_vault_ref(vault_ref)
        credential.vault_ref = vault_ref
        await self.repository.session.flush()
        return CredentialResponse.model_validate(credential)

    async def delete_credential(self, credential_id: UUID) -> None:
        await self.repository.delete_credential(await self._get(credential_id))

    async def trigger_rotation(
        self,
        credential_id: UUID,
        request: CredentialRotateRequest,
        *,
        requester_id: UUID | None,
    ) -> CredentialRotateResponse:
        if self.rotation_service is None:
            raise ValidationError("ROTATION_SERVICE_UNAVAILABLE", "Rotation service unavailable")
        credential = await self._get(credential_id)
        if request.emergency and request.approved_by == requester_id:
            raise AuthorizationError(
                "TWO_PERSON_APPROVAL_REQUIRED",
                "Emergency rotation requires a distinct second approver.",
            )
        schedule_id = credential.rotation_schedule_id
        if schedule_id is None:
            schedule = await self.rotation_service.create_schedule(
                secret_name=credential.vault_ref,
                secret_type="model_provider",
                rotation_interval_days=90,
                overlap_window_hours=max(24, request.overlap_window_hours),
                vault_path=credential.vault_ref,
            )
            credential.rotation_schedule_id = schedule.id
            schedule_id = schedule.id
        schedule = await self.rotation_service.trigger(
            schedule_id,
            emergency=request.emergency,
            skip_overlap=request.overlap_window_hours == 0,
            requester_id=requester_id,
            approved_by=request.approved_by,
        )
        credential.rotated_at = datetime.now(UTC)
        await self.repository.session.flush()
        return CredentialRotateResponse(
            rotation_schedule_id=schedule.id,
            rotation_state=schedule.rotation_state,
            overlap_ends_at=schedule.overlap_ends_at,
        )

    async def _get(self, credential_id: UUID) -> ModelProviderCredential:
        credential = await self.repository.get_credential(credential_id)
        if credential is None:
            raise NotFoundError(
                "MODEL_PROVIDER_CREDENTIAL_NOT_FOUND",
                "Provider credential not found",
            )
        return credential

    async def _verify_vault_ref(self, vault_ref: str) -> None:
        if self.secret_reader is None:
            return
        try:
            value = await self.secret_reader.get(vault_ref)
        except Exception as exc:
            raise ValidationError(
                "VAULT_REFERENCE_UNAVAILABLE",
                "Vault reference cannot be resolved.",
            ) from exc
        if not value:
            raise ValidationError(
                "VAULT_REFERENCE_EMPTY",
                "Vault reference resolved to an empty credential.",
            )
