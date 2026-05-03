"""OpenTelemetry counters/histograms for the data_lifecycle BC.

Mirrors the existing ``billing/metrics.py`` pattern: lazy meter import,
silent no-op fallback when the OTel SDK is unavailable.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


class DataLifecycleMetrics:
    def __init__(self) -> None:
        try:
            meter = import_module("opentelemetry.metrics").get_meter(__name__)
            self.export_duration = meter.create_histogram(
                "data_lifecycle_export_duration_seconds"
            )
            self.export_bytes = meter.create_counter(
                "data_lifecycle_export_bytes_total"
            )
            self.export_failures = meter.create_counter(
                "data_lifecycle_export_failures_total"
            )
            self.deletion_grace_queue_depth = meter.create_up_down_counter(
                "data_lifecycle_deletion_grace_queue_depth"
            )
            self.deletion_phase_advance = meter.create_counter(
                "data_lifecycle_deletion_phase_advance_total"
            )
            self.cascade_duration = meter.create_histogram(
                "data_lifecycle_cascade_duration_seconds"
            )
            self.dpa_scan_duration = meter.create_histogram(
                "data_lifecycle_dpa_scan_duration_seconds"
            )
            self.dpa_virus_detected = meter.create_counter(
                "data_lifecycle_dpa_virus_detected_total"
            )
            self.dpa_scan_unavailable = meter.create_counter(
                "data_lifecycle_dpa_scan_unavailable_total"
            )
        except Exception:
            self.export_duration = None
            self.export_bytes = None
            self.export_failures = None
            self.deletion_grace_queue_depth = None
            self.deletion_phase_advance = None
            self.cascade_duration = None
            self.dpa_scan_duration = None
            self.dpa_virus_detected = None
            self.dpa_scan_unavailable = None

    def record_export_completed(
        self, *, scope_type: str, duration_seconds: float, size_bytes: int
    ) -> None:
        attrs = {"scope_type": scope_type}
        _record(self.export_duration, duration_seconds, attrs)
        _add(self.export_bytes, size_bytes, attrs)

    def record_export_failed(self, *, scope_type: str, reason: str) -> None:
        _add(self.export_failures, 1, {"scope_type": scope_type, "reason": reason})

    def record_deletion_phase_advance(self, *, from_phase: str, to_phase: str) -> None:
        _add(
            self.deletion_phase_advance,
            1,
            {"from_phase": from_phase, "to_phase": to_phase},
        )

    def record_cascade_duration(self, *, scope_type: str, duration_seconds: float) -> None:
        _record(self.cascade_duration, duration_seconds, {"scope_type": scope_type})

    def record_dpa_scan(self, *, duration_seconds: float, outcome: str) -> None:
        _record(
            self.dpa_scan_duration,
            duration_seconds,
            {"outcome": outcome},
        )

    def record_dpa_virus_detected(self, *, signature: str) -> None:
        _add(self.dpa_virus_detected, 1, {"signature": signature})

    def record_dpa_scan_unavailable(self) -> None:
        _add(self.dpa_scan_unavailable, 1, {})


def _add(counter: Any, value: int, attributes: dict[str, str]) -> None:
    if counter is None:
        return
    try:
        counter.add(value, attributes=attributes)
    except Exception:
        pass


def _record(histogram: Any, value: float, attributes: dict[str, str]) -> None:
    if histogram is None:
        return
    try:
        histogram.record(value, attributes=attributes)
    except Exception:
        pass
