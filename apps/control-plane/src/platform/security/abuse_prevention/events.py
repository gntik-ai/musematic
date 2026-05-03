"""Kafka events for the abuse-prevention bounded context (UPD-050).

Topic: ``security.abuse_events``. Partition key: tenant_id (UPD-046 R7
— always the default tenant for UPD-050; the partition-key convention
is preserved for forward compatibility with per-tenant abuse rules).

See ``specs/100-abuse-prevention/contracts/abuse-events-kafka.md``.
"""

from __future__ import annotations

from enum import StrEnum
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from typing import Any, Final

from pydantic import BaseModel, Field


class AbuseEventType(StrEnum):
    signup_velocity_hit = "security.signup_velocity_hit"
    signup_disposable_email_blocked = "security.signup_disposable_email_blocked"
    signup_geo_blocked = "security.signup_geo_blocked"
    signup_captcha_failed = "security.signup_captcha_failed"
    signup_fraud_score_high = "security.signup_fraud_score_high"
    suspension_created = "security.suspension_created"
    suspension_lifted = "security.suspension_lifted"
    setting_changed = "security.setting_changed"
    disposable_email_override_changed = "security.disposable_email_override_changed"


class SignupVelocityHitPayload(BaseModel):
    counter_key: str
    counter_window_start: str
    threshold: int
    source_ip: str
    asn: str | None = None
    email_domain: str | None = None


class SignupDisposableEmailBlockedPayload(BaseModel):
    email_domain: str
    source_ip: str


class SignupGeoBlockedPayload(BaseModel):
    source_ip: str
    country_code: str


class SignupCaptchaFailedPayload(BaseModel):
    source_ip: str
    reason: str  # "token_invalid" | "token_replayed" | "provider_error"


class SignupFraudScoreHighPayload(BaseModel):
    user_id: str
    source_ip: str
    risk_score: float
    evidence: dict[str, Any] = Field(default_factory=dict)


class SuspensionCreatedPayload(BaseModel):
    suspension_id: str
    user_id: str
    reason: str
    evidence_summary: str
    suspended_by: str
    suspended_by_user_id: str | None = None


class SuspensionLiftedPayload(BaseModel):
    suspension_id: str
    user_id: str
    lifted_by_user_id: str
    lift_reason: str


class SettingChangedPayload(BaseModel):
    setting_key: str
    from_value: Any
    to_value: Any
    actor_user_id: str


class DisposableEmailOverrideChangedPayload(BaseModel):
    domain: str
    operation: str  # "added" | "removed"
    actor_user_id: str
    reason: str | None = None


ABUSE_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    AbuseEventType.signup_velocity_hit.value: SignupVelocityHitPayload,
    AbuseEventType.signup_disposable_email_blocked.value: SignupDisposableEmailBlockedPayload,
    AbuseEventType.signup_geo_blocked.value: SignupGeoBlockedPayload,
    AbuseEventType.signup_captcha_failed.value: SignupCaptchaFailedPayload,
    AbuseEventType.signup_fraud_score_high.value: SignupFraudScoreHighPayload,
    AbuseEventType.suspension_created.value: SuspensionCreatedPayload,
    AbuseEventType.suspension_lifted.value: SuspensionLiftedPayload,
    AbuseEventType.setting_changed.value: SettingChangedPayload,
    AbuseEventType.disposable_email_override_changed.value: DisposableEmailOverrideChangedPayload,
}


def register_abuse_event_types() -> None:
    for event_type, schema in ABUSE_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


async def publish_abuse_event(
    producer: EventProducer | None,
    event_type: AbuseEventType | str,
    payload: BaseModel,
    correlation: CorrelationContext,
    *,
    source: str = "platform.security.abuse_prevention",
) -> None:
    if producer is None:
        return
    event_name = (
        event_type.value if isinstance(event_type, AbuseEventType) else event_type
    )
    payload_dict = payload.model_dump(mode="json")
    # Use the most natural key per event type.
    key = (
        payload_dict.get("user_id")
        or payload_dict.get("suspension_id")
        or payload_dict.get("counter_key")
        or payload_dict.get("source_ip")
        or str(correlation.correlation_id)
    )
    await producer.publish(
        topic="security.abuse_events",
        key=str(key),
        event_type=event_name,
        payload=payload_dict,
        correlation_ctx=correlation,
        source=source,
    )
