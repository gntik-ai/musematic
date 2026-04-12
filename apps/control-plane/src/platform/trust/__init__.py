__all__ = [
    "get_ate_service",
    "get_certification_service",
    "get_circuit_breaker_service",
    "get_guardrail_pipeline_service",
    "get_oje_service",
    "get_prescreener_service",
    "get_recertification_service",
    "get_trust_tier_service",
]


def __getattr__(name: str) -> object:
    if name in __all__:
        from platform.trust import dependencies

        return getattr(dependencies, name)
    raise AttributeError(name)
