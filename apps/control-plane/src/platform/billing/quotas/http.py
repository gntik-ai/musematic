from __future__ import annotations

from decimal import Decimal
from platform.billing.exceptions import (
    ModelTierNotAllowedError,
    NoActiveSubscriptionError,
    OverageCapExceededError,
    OverageRequiredError,
    QuotaExceededError,
    SubscriptionSuspendedError,
)
from platform.billing.quotas.schemas import QuotaCheckResult
from typing import Any
from uuid import UUID

from fastapi import HTTPException


def quota_result_to_http(result: QuotaCheckResult) -> HTTPException | None:
    if result.ok:
        return None
    status_by_decision = {
        "HARD_CAP_EXCEEDED": 402,
        "OVERAGE_REQUIRED": 202,
        "OVERAGE_CAP_EXCEEDED": 402,
        "MODEL_TIER_NOT_ALLOWED": 402,
        "NO_ACTIVE_SUBSCRIPTION": 403,
        "SUSPENDED": 403,
    }
    status_code = status_by_decision.get(result.decision, 403)
    return HTTPException(status_code=status_code, detail=_body(result))


def raise_for_quota_result(result: QuotaCheckResult, *, workspace_id: UUID | None = None) -> None:
    if result.ok:
        return
    if result.decision == "HARD_CAP_EXCEEDED":
        raise QuotaExceededError(
            result.quota_name or "quota",
            _number(result.current),
            _number(result.limit),
            reset_at=result.reset_at,
            plan_slug=result.plan_slug,
            upgrade_url=result.upgrade_url,
            overage_available=result.overage_available,
        )
    if result.decision == "MODEL_TIER_NOT_ALLOWED":
        raise ModelTierNotAllowedError(
            workspace_id or UUID(int=0),
            result.quota_name or "model",
            result.plan_slug or "unknown",
            quota_name=result.quota_name or "allowed_model_tier",
            reset_at=result.reset_at,
            plan_slug=result.plan_slug,
            upgrade_url=result.upgrade_url,
        )
    if result.decision == "OVERAGE_CAP_EXCEEDED":
        raise OverageCapExceededError(
            workspace_id or UUID(int=0),
            str(result.limit or "0"),
            quota_name=result.quota_name,
            reset_at=result.reset_at,
            plan_slug=result.plan_slug,
            upgrade_url=result.upgrade_url,
        )
    if result.decision == "OVERAGE_REQUIRED":
        raise OverageRequiredError(workspace_id or UUID(int=0), result.quota_name or "quota")
    if result.decision == "NO_ACTIVE_SUBSCRIPTION":
        raise NoActiveSubscriptionError(workspace_id or UUID(int=0))
    if result.decision == "SUSPENDED":
        raise SubscriptionSuspendedError(workspace_id or UUID(int=0))
    exception = quota_result_to_http(result)
    if exception is not None:
        raise exception


def quota_error_body(result: QuotaCheckResult) -> dict[str, Any]:
    return _body(result)


def _body(result: QuotaCheckResult) -> dict[str, Any]:
    if result.decision == "OVERAGE_REQUIRED":
        return {
            "status": "paused_quota_exceeded",
            "quota_name": result.quota_name,
            "current": _json_number(result.current),
            "limit": _json_number(result.limit),
            "reset_at": result.reset_at.isoformat() if result.reset_at else None,
            "plan_slug": result.plan_slug,
            "overage_available": result.overage_available,
        }
    code_by_decision = {
        "HARD_CAP_EXCEEDED": "quota_exceeded",
        "OVERAGE_CAP_EXCEEDED": "overage_cap_exceeded",
        "MODEL_TIER_NOT_ALLOWED": "model_tier_not_allowed",
        "NO_ACTIVE_SUBSCRIPTION": "no_active_subscription",
        "SUSPENDED": "subscription_suspended",
    }
    return {
        "code": code_by_decision.get(result.decision, result.decision.lower()),
        "message": result.message or "Billing quota check failed",
        "details": {
            "quota_name": result.quota_name,
            "current": _json_number(result.current),
            "limit": _json_number(result.limit),
            "reset_at": result.reset_at.isoformat() if result.reset_at else None,
            "plan_slug": result.plan_slug,
            "upgrade_url": result.upgrade_url,
            "overage_available": result.overage_available,
        },
    }


def _number(value: Decimal | int | None) -> int | float:
    if isinstance(value, Decimal):
        return float(value)
    return int(value or 0)


def _json_number(value: Decimal | int | None) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    return value
