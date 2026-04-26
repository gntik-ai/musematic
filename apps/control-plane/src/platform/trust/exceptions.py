from __future__ import annotations

from platform.common.exceptions import PlatformError


class TrustError(PlatformError):
    status_code = 400

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(code, message, details)


class CertificationNotFoundError(TrustError):
    status_code = 404

    def __init__(self, certification_id: object) -> None:
        super().__init__(
            "TRUST_CERTIFICATION_NOT_FOUND",
            "Certification not found",
            {"certification_id": str(certification_id)},
        )


class CertifierNotFoundError(TrustError):
    status_code = 404

    def __init__(self, certifier_id: object) -> None:
        super().__init__(
            "TRUST_CERTIFIER_NOT_FOUND",
            "Certifier not found",
            {"certifier_id": str(certifier_id)},
        )


class ContractNotFoundError(TrustError):
    status_code = 404

    def __init__(self, contract_id: object) -> None:
        super().__init__(
            "TRUST_CONTRACT_NOT_FOUND",
            "Contract not found",
            {"contract_id": str(contract_id)},
        )


class RecertificationRequestNotFoundError(TrustError):
    status_code = 404

    def __init__(self, request_id: object) -> None:
        super().__init__(
            "TRUST_RECERTIFICATION_REQUEST_NOT_FOUND",
            "Recertification request not found",
            {"request_id": str(request_id)},
        )


class CertificationStateError(TrustError):
    def __init__(self, message: str, *, certification_id: object | None = None) -> None:
        details: dict[str, object] | None = (
            {"certification_id": str(certification_id)} if certification_id is not None else None
        )
        super().__init__("TRUST_CERTIFICATION_STATE_ERROR", message, details)


class CertificationBlockedError(TrustError):
    status_code = 409

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(
            "TRUST_CERTIFICATION_BLOCKED",
            "Certification request is blocked",
            {"reason": reason, "detail": detail},
        )


class InvalidStateTransitionError(TrustError):
    def __init__(self, current_state: str, target_state: str) -> None:
        super().__init__(
            "TRUST_INVALID_STATE_TRANSITION",
            f"Invalid trust state transition from {current_state} to {target_state}",
            {
                "current_state": current_state,
                "target_state": target_state,
            },
        )


class GuardrailBlockedError(TrustError):
    status_code = 403

    def __init__(self, layer: str, policy_basis: str) -> None:
        super().__init__(
            "TRUST_GUARDRAIL_BLOCKED",
            "The request was blocked by trust guardrails",
            {"layer": layer, "policy_basis": policy_basis},
        )


class CircuitBreakerTrippedError(TrustError):
    status_code = 429

    def __init__(self, agent_id: str) -> None:
        super().__init__(
            "TRUST_CIRCUIT_BREAKER_TRIPPED",
            "The circuit breaker is tripped for the requested agent",
            {"agent_id": agent_id},
        )


class ATERunError(TrustError):
    status_code = 502

    def __init__(self, message: str, *, simulation_id: str | None = None) -> None:
        details: dict[str, object] | None = (
            {"simulation_id": simulation_id} if simulation_id is not None else None
        )
        super().__init__("TRUST_ATE_RUN_ERROR", message, details)


class OJEConfigError(TrustError):
    def __init__(self, message: str, *, fqn: str | None = None) -> None:
        details: dict[str, object] | None = {"fqn": fqn} if fqn is not None else None
        super().__init__("TRUST_OJE_CONFIG_ERROR", message, details)


class PreScreenerError(TrustError):
    def __init__(self, message: str, *, rule_set_id: object | None = None) -> None:
        details: dict[str, object] | None = (
            {"rule_set_id": str(rule_set_id)} if rule_set_id is not None else None
        )
        super().__init__("TRUST_PRESCREENER_ERROR", message, details)


class ContractConflictError(TrustError):
    status_code = 409

    def __init__(self, code: str, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(code, message, details)


class ModerationProviderError(TrustError):
    status_code = 502

    def __init__(self, provider: str, message: str = "Moderation provider failed") -> None:
        super().__init__(
            "TRUST_MODERATION_PROVIDER_ERROR",
            message,
            {"provider": provider},
        )


class ModerationProviderTimeoutError(ModerationProviderError):
    status_code = 504

    def __init__(self, provider: str) -> None:
        super().__init__(provider, "Moderation provider timed out")


class ModerationPolicyNotFoundError(TrustError):
    status_code = 404

    def __init__(self, policy_id: object) -> None:
        super().__init__(
            "TRUST_MODERATION_POLICY_NOT_FOUND",
            "Moderation policy not found",
            {"policy_id": str(policy_id)},
        )


class ModerationCostCapExceededError(TrustError):
    status_code = 429

    def __init__(self, workspace_id: object) -> None:
        super().__init__(
            "TRUST_MODERATION_COST_CAP_EXCEEDED",
            "Content moderation monthly cost cap exceeded",
            {"workspace_id": str(workspace_id)},
        )


class ResidencyDisallowedProviderError(TrustError):
    status_code = 403

    def __init__(self, provider: str) -> None:
        super().__init__(
            "TRUST_MODERATION_RESIDENCY_DISALLOWED",
            "Provider egress is disallowed by residency policy",
            {"provider": provider},
        )


class InvalidModerationPolicyError(TrustError):
    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__("TRUST_MODERATION_POLICY_INVALID", message)
