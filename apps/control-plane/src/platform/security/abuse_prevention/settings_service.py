"""Abuse-prevention settings CRUD (UPD-050 T012).

Wraps the ``abuse_prevention_settings`` table behind an allowlist + JSON
validation gate. Every mutation records an audit-chain entry and emits
a ``security.setting_changed`` Kafka event.
"""

from __future__ import annotations

import json
from platform.audit.service import AuditChainService
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.logging import get_logger
from platform.security.abuse_prevention.events import (
    AbuseEventType,
    SettingChangedPayload,
    publish_abuse_event,
)
from platform.security.abuse_prevention.exceptions import SettingKeyUnknownError
from platform.security.abuse_prevention.models import AbusePreventionSetting
from platform.security.abuse_prevention.schemas import ABUSE_SETTING_KEYS
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

LOGGER = get_logger(__name__)


# Lightweight value-shape validators per setting. The settings_value_json
# column is JSONB so anything serializable goes in; these checks keep
# operators from accidentally storing the wrong shape.
_VALIDATORS: dict[str, tuple[type, ...]] = {
    "velocity_per_ip_hour": (int,),
    "velocity_per_asn_hour": (int,),
    "velocity_per_email_domain_day": (int,),
    "captcha_enabled": (bool,),
    "captcha_provider": (str,),
    "geo_block_mode": (str,),
    "geo_block_country_codes": (list,),
    "fraud_scoring_provider": (str,),
    "fraud_scoring_threshold": (int, float),
    "disposable_email_blocking": (bool,),
    "auto_suspension_cost_burn_multiplier": (int, float),
    "auto_suspension_velocity_repeat_threshold": (int,),
}


class AbusePreventionSettingsService:
    """CRUD façade over `abuse_prevention_settings`.

    The session passed in is the regular tenant-scoped session — the
    settings rows are not tenant-scoped (they apply globally to the
    default tenant per spec) but they live in a regular table that
    RLS does not gate.
    """

    def __init__(
        self,
        *,
        session: AsyncSession,
        audit_chain: AuditChainService | None,
        event_producer: EventProducer | None,
    ) -> None:
        self._session = session
        self._audit = audit_chain
        self._producer = event_producer

    async def get(self, setting_key: str) -> Any:
        if setting_key not in ABUSE_SETTING_KEYS:
            raise SettingKeyUnknownError(setting_key)
        result = await self._session.execute(
            select(AbusePreventionSetting).where(
                AbusePreventionSetting.setting_key == setting_key
            )
        )
        row = result.scalar_one_or_none()
        return None if row is None else row.setting_value_json

    async def get_all(self) -> dict[str, Any]:
        result = await self._session.execute(select(AbusePreventionSetting))
        return {row.setting_key: row.setting_value_json for row in result.scalars()}

    async def set(
        self,
        actor_user_id: UUID,
        setting_key: str,
        value: Any,
    ) -> None:
        if setting_key not in ABUSE_SETTING_KEYS:
            raise SettingKeyUnknownError(setting_key)
        expected = _VALIDATORS[setting_key]
        if not isinstance(value, expected):
            raise ValueError(
                f"setting_value_invalid: {setting_key} expects {expected!r}, "
                f"got {type(value).__name__}"
            )
        result = await self._session.execute(
            select(AbusePreventionSetting).where(
                AbusePreventionSetting.setting_key == setting_key
            )
        )
        row = result.scalar_one_or_none()
        from_value: Any
        if row is None:
            row = AbusePreventionSetting(
                setting_key=setting_key,
                setting_value_json=value,
                updated_by_user_id=actor_user_id,
            )
            self._session.add(row)
            from_value = None
        else:
            from_value = row.setting_value_json
            if from_value == value:
                return  # no-op idempotent
            # The column is JSONB; the model is typed dict[str, object] for
            # the most common shape, but JSONB accepts scalars/lists too.
            # Cast through Any to satisfy mypy.
            row.setting_value_json = value  # type: ignore[assignment]
            row.updated_by_user_id = actor_user_id
        await self._session.commit()

        canonical_payload = {
            "setting_key": setting_key,
            "from_value": from_value,
            "to_value": value,
            "actor_user_id": str(actor_user_id),
        }
        if self._audit is not None:
            canonical_bytes = json.dumps(
                canonical_payload, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            await self._audit.append(
                uuid4(),
                "abuse_prevention",
                canonical_bytes,
                event_type=AbuseEventType.setting_changed.value,
                actor_role="super_admin",
                canonical_payload_json=canonical_payload,
            )
        await publish_abuse_event(
            self._producer,
            AbuseEventType.setting_changed,
            SettingChangedPayload(
                setting_key=setting_key,
                from_value=from_value,
                to_value=value,
                actor_user_id=str(actor_user_id),
            ),
            CorrelationContext(correlation_id=uuid4()),
        )
        LOGGER.info(
            "security.setting_changed",
            extra={
                "setting_key": setting_key,
                "from_value": from_value,
                "to_value": value,
                "actor_user_id": str(actor_user_id),
            },
        )
