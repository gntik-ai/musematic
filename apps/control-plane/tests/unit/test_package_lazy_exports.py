from __future__ import annotations

import platform.analytics as analytics_pkg
import platform.interactions as interactions_pkg
import platform.notifications as notifications_pkg

import pytest


def test_lazy_package_exports_resolve_expected_symbols() -> None:
    from platform.analytics.dependencies import get_analytics_service
    from platform.interactions.dependencies import get_interactions_service
    from platform.notifications.router import router

    assert analytics_pkg.__getattr__("get_analytics_service") is get_analytics_service
    assert interactions_pkg.__getattr__("get_interactions_service") is get_interactions_service
    assert notifications_pkg.__getattr__("router") is router


@pytest.mark.parametrize("package", [analytics_pkg, interactions_pkg, notifications_pkg])
def test_lazy_package_exports_reject_unknown_names(package: object) -> None:
    with pytest.raises(AttributeError):
        package.__getattr__("missing_export")  # type: ignore[attr-defined]
