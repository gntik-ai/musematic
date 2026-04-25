from __future__ import annotations

from platform.privacy_compliance.events import (
    ConsentRevokedPayload,
    PrivacyEventPublisher,
    PrivacyEventType,
    utcnow,
)
from platform.privacy_compliance.exceptions import ConsentRequired
from platform.privacy_compliance.models import ConsentType, PrivacyConsentRecord
from platform.privacy_compliance.repository import PrivacyComplianceRepository
from uuid import UUID


class ConsentService:
    def __init__(
        self,
        *,
        repository: PrivacyComplianceRepository,
        event_publisher: PrivacyEventPublisher,
    ) -> None:
        self.repository = repository
        self.events = event_publisher

    async def get_state(
        self,
        user_id: UUID,
        workspace_id: UUID | None = None,
    ) -> dict[ConsentType, str]:
        del workspace_id
        records = await self.repository.current_consent_state(user_id)
        state: dict[ConsentType, str] = {}
        for consent_type, record in records.items():
            if record is None:
                state[consent_type] = "never_asked"
            elif record.granted and record.revoked_at is None:
                state[consent_type] = "granted"
            else:
                state[consent_type] = "denied"
        return state

    async def require_or_prompt(self, user_id: UUID, workspace_id: UUID) -> None:
        state = await self.get_state(user_id, workspace_id)
        missing = [
            consent_type.value
            for consent_type, value in state.items()
            if value == "never_asked"
        ]
        if missing:
            raise ConsentRequired(missing)

    async def record_consents(
        self,
        user_id: UUID,
        choices: dict[ConsentType | str, bool],
        workspace_id: UUID | None = None,
    ) -> list[PrivacyConsentRecord]:
        records = []
        for consent_type, granted in choices.items():
            normalized = (
                consent_type.value if isinstance(consent_type, ConsentType) else consent_type
            )
            records.append(
                await self.repository.upsert_consent(
                    user_id=user_id,
                    consent_type=normalized,
                    granted=granted,
                    workspace_id=workspace_id,
                )
            )
        return records

    async def revoke(self, user_id: UUID, consent_type: str) -> PrivacyConsentRecord:
        record = await self.repository.revoke_consent(user_id=user_id, consent_type=consent_type)
        await self.events.publish(
            PrivacyEventType.consent_revoked,
            ConsentRevokedPayload(
                user_id=user_id,
                consent_type=consent_type,
                workspace_id=record.workspace_id,
                occurred_at=utcnow(),
            ),
            key=str(user_id),
        )
        return record

    async def history(self, user_id: UUID) -> list[PrivacyConsentRecord]:
        return await self.repository.get_consent_records(user_id)


DISCLOSURE_TEXT = (
    "Musematic uses AI agents to process requests. Your choices control AI "
    "interaction consent, analytics data collection, and training-corpus use."
)
