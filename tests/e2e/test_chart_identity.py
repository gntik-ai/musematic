from __future__ import annotations

from pathlib import Path


def test_e2e_harness_does_not_fork_helm_charts() -> None:
    root = Path(__file__).parent
    charts = sorted(str(path.relative_to(root)) for path in root.rglob("Chart.yaml"))
    assert charts == [], (
        "tests/e2e must not contain Helm charts; reuse deploy/helm charts instead. "
        f"Found: {charts}"
    )
