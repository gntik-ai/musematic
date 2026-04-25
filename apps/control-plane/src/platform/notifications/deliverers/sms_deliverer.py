from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.notifications.models import DeliveryOutcome, UserAlert
from typing import Any, Protocol, cast
from uuid import UUID

import httpx


class SmsProvider(Protocol):
    async def send_sms(
        self,
        *,
        to: str,
        body: str,
        sender: str | None,
    ) -> SmsDeliveryResult: ...


@dataclass(frozen=True, slots=True)
class SmsDeliveryResult:
    outcome: DeliveryOutcome
    failure_reason: str | None = None
    last_response_status: int | None = None
    error_detail: str | None = None


class TwilioSmsProvider:
    def __init__(self, account_sid: str, auth_token: str, default_sender: str) -> None:
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.default_sender = default_sender

    async def send_sms(
        self,
        *,
        to: str,
        body: str,
        sender: str | None,
    ) -> SmsDeliveryResult:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json",
                    data={
                        "To": to,
                        "From": sender or self.default_sender,
                        "Body": body,
                    },
                    auth=(self.account_sid, self.auth_token),
                )
        except httpx.TimeoutException:
            return SmsDeliveryResult(
                DeliveryOutcome.timed_out,
                failure_reason="timeout",
                error_detail="sms_provider_timeout",
            )
        except httpx.HTTPError:
            return SmsDeliveryResult(
                DeliveryOutcome.timed_out,
                failure_reason="provider_unavailable",
                error_detail="sms_provider_unavailable",
            )
        return _classify_response(response)


class SmsDeliverer:
    def __init__(
        self,
        *,
        redis: object | None,
        secrets: object | None,
        settings: PlatformSettings,
        provider: SmsProvider | None = None,
        deployment: str | None = None,
    ) -> None:
        self.redis = redis
        self.secrets = secrets
        self.settings = settings
        self.provider = provider
        self.deployment = deployment or str(getattr(settings, "profile", "default"))

    async def send(
        self,
        alert: UserAlert,
        phone_number: str,
        config: object | None = None,
        *,
        workspace_id: UUID | None = None,
    ) -> tuple[DeliveryOutcome, str | None]:
        cost_units = _sms_cost_units(config)
        if workspace_id is not None and await self._cost_cap_exceeded(workspace_id, cost_units):
            return DeliveryOutcome.fallback, "cost_cap_exceeded"
        provider = await self._provider()
        result = await provider.send_sms(
            to=phone_number,
            body=build_sms_body(alert, config),
            sender=_sender(config),
        )
        if result.outcome == DeliveryOutcome.success and workspace_id is not None:
            await _increment_cost_counter(self.redis, _cost_key(workspace_id), cost_units)
        return result.outcome, result.error_detail or result.failure_reason

    async def _provider(self) -> SmsProvider:
        if self.provider is not None:
            return self.provider
        path = f"secret/data/notifications/sms-providers/{self.deployment}"
        payload = await _read_secret(self.secrets, path)
        account_sid = str(payload.get("account_sid", ""))
        auth_token = str(payload.get("auth_token", ""))
        default_sender = str(payload.get("default_sender", payload.get("sender", "")))
        return TwilioSmsProvider(account_sid, auth_token, default_sender)

    async def _cost_cap_exceeded(self, workspace_id: UUID, cost_units: int) -> bool:
        cap_units = round(self.settings.notifications.sms_workspace_monthly_cost_cap_eur * 100)
        if cap_units <= 0:
            return True
        current_units = await _get_cost_counter(self.redis, _cost_key(workspace_id))
        return current_units + cost_units > cap_units


def build_sms_body(alert: UserAlert, config: object | None = None) -> str:
    extra = _extra(config)
    deep_link = str(
        extra.get(
            "short_link",
            extra.get("deep_link", extra.get("deep_link_url", "https://app.musematic.ai")),
        )
    )
    if len(deep_link) > 80:
        deep_link = f"{deep_link[:77]}..."
    context = alert.body or ""
    base = f"{alert.title}\n{context}".strip()
    candidate = f"{base}\n{deep_link}" if base else deep_link
    if len(candidate) <= 160:
        return candidate

    suffix = f"\n{deep_link}"
    available = max(0, 160 - len(suffix) - 1)
    if available <= 0:
        return deep_link[-160:]
    return f"{base[:available].rstrip()}…{suffix}"[:160]


def _classify_response(response: httpx.Response) -> SmsDeliveryResult:
    if 200 <= response.status_code < 300:
        return SmsDeliveryResult(DeliveryOutcome.success, last_response_status=response.status_code)
    if response.status_code == 429:
        return SmsDeliveryResult(
            DeliveryOutcome.timed_out,
            failure_reason="rate_limited",
            last_response_status=response.status_code,
            error_detail="sms_rate_limited",
        )
    if response.status_code >= 500:
        return SmsDeliveryResult(
            DeliveryOutcome.timed_out,
            failure_reason="provider_5xx",
            last_response_status=response.status_code,
            error_detail="sms_provider_unavailable",
        )
    return SmsDeliveryResult(
        DeliveryOutcome.failed,
        failure_reason="4xx_permanent",
        last_response_status=response.status_code,
        error_detail="sms_provider_rejected",
    )


def _cost_key(workspace_id: UUID) -> str:
    return f"notifications:sms_cost:{workspace_id}:{datetime.now(UTC):%Y-%m}"


def _sms_cost_units(config: object | None) -> int:
    raw = _extra(config).get("sms_cost_eur", 0.08)
    try:
        return max(1, round(float(raw) * 100))
    except (TypeError, ValueError):
        return 8


def _sender(config: object | None) -> str | None:
    value = _extra(config).get("sender")
    return str(value) if value else None


def _extra(config: object | None) -> dict[str, Any]:
    value = getattr(config, "extra", None)
    return value if isinstance(value, dict) else {}


async def _read_secret(secrets: object | None, path: str) -> dict[str, Any]:
    if secrets is None:
        return {}
    read_secret = getattr(secrets, "read_secret", None)
    if not callable(read_secret):
        return {}
    value = await cast(Any, read_secret)(path)
    return value if isinstance(value, dict) else {}


async def _get_cost_counter(redis: object | None, key: str) -> int:
    if redis is None:
        return 0
    get_method = getattr(redis, "get", None)
    if callable(get_method):
        value = await cast(Any, get_method)(key)
        return _int_value(value)
    client = await _raw_redis_client(redis)
    if client is None:
        return 0
    raw_get = getattr(client, "get", None)
    if not callable(raw_get):
        return 0
    return _int_value(await raw_get(key))


async def _increment_cost_counter(redis: object | None, key: str, amount: int) -> None:
    if redis is None:
        return
    client = await _raw_redis_client(redis)
    if client is not None:
        incrby = getattr(client, "incrby", None)
        expire = getattr(client, "expire", None)
        if callable(incrby):
            await incrby(key, amount)
            if callable(expire):
                await expire(key, 35 * 24 * 60 * 60)
            return
    get_method = getattr(redis, "get", None)
    set_method = getattr(redis, "set", None)
    if callable(get_method) and callable(set_method):
        current = _int_value(await cast(Any, get_method)(key))
        try:
            await cast(Any, set_method)(key, str(current + amount), ttl=35 * 24 * 60 * 60)
        except TypeError:
            await cast(Any, set_method)(key, str(current + amount).encode(), 35 * 24 * 60 * 60)


async def _raw_redis_client(redis: object) -> object | None:
    client = getattr(redis, "client", None)
    if client is not None:
        return cast(object, client)
    get_client = getattr(redis, "_get_client", None)
    if callable(get_client):
        return cast(object, await cast(Any, get_client)())
    return None


def _int_value(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    try:
        return int(str(value))
    except ValueError:
        return 0
