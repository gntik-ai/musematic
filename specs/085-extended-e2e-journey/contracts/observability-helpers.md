# Observability Helper Contracts

These helpers live under `tests/e2e/journeys/helpers/` and must query real
observability backends.

| Helper | Signature | Success | Failure |
|---|---|---|---|
| `assert_log_contains` | `async (loki_client, labels, substring, within_seconds=30, poll_interval=1.0) -> dict` | Returns the matching Loki log entry. | Fails immediately if Loki readiness fails; otherwise names labels, substring, and most recent volume. |
| `assert_metric_value` | `async (prom_client, query, expected, tolerance=0.01, within_seconds=15, poll_interval=1.0) -> float` | Returns the matching Prometheus value. | Names query, expected value, last value, and payload. |
| `assert_trace_exists` | `async (jaeger_client, trace_id, expected_services, expected_operations=None, within_seconds=30) -> dict` | Returns the matching Jaeger trace payload. | Names missing services and operations. |
| `take_dashboard_snapshot` | `async (grafana_client, dashboard_uid, time_range="now-1h", width=1920, height=1080, output_dir=Path("reports/snapshots"), journey_id="", step="") -> Path | None` | Returns a PNG path. | Returns `None` when the renderer is disabled; raises on other HTTP failures. |
| `run_axe_scan` | `async (page, allowlist_path, impact="moderate") -> list[dict]` | Returns non-allowlisted violations. | Logs allowlisted violations with rule, selector, and tracking context. |

## Negative Matrix

| Condition | Expected behaviour |
|---|---|
| Loki is not ready | `assert_log_contains` fails before polling. |
| Prometheus never returns a value | `assert_metric_value` fails with the last payload. |
| Jaeger trace exists but lacks a service | `assert_trace_exists` fails with actual services. |
| Grafana renderer is absent in `minimal` or `e2e` presets | `take_dashboard_snapshot` returns `None`. |
| Axe violation is not allowlisted | `run_axe_scan` returns it to the caller so the test fails. |
