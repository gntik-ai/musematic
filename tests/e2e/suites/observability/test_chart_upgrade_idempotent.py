from __future__ import annotations

import pytest

from ._chart_lifecycle import (
    helm_install,
    require_chart_lifecycle_enabled,
    temporary_values_overlay,
    wait_for_ready_pods,
)

pytestmark = [pytest.mark.e2e, pytest.mark.observability, pytest.mark.slow]


def test_observability_chart_upgrade_applies_non_destructive_retention_change() -> None:
    require_chart_lifecycle_enabled()
    helm_install()
    overlay = temporary_values_overlay(
        """
loki:
  loki:
    limits_config:
      retention_period: 2h
"""
    )
    try:
        helm_install(values=overlay)
        assert wait_for_ready_pods()
    finally:
        overlay.unlink(missing_ok=True)
