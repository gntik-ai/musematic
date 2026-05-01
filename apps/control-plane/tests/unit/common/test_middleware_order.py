from __future__ import annotations

from platform.main import create_app


def test_user_middleware_order_matches_contract() -> None:
    app = create_app()

    assert [middleware.cls.__name__ for middleware in app.user_middleware] == [
        "TenantResolverMiddleware",
        "CorrelationMiddleware",
        "CorrelationLoggingMiddleware",
        "AuthMiddleware",
        "AdminReadOnlyMiddleware",
        "MaintenanceGateMiddleware",
        "RateLimitMiddleware",
        "DebugCaptureMiddleware",
        "ApiVersioningMiddleware",
    ]
