from __future__ import annotations

import importlib.util
from pathlib import Path


def test_privacy_cascade_adapter_coverage_script_passes() -> None:
    path = Path(__file__).parents[1] / "lint_privacy_cascade_coverage.py"
    spec = importlib.util.spec_from_file_location("lint_privacy_cascade_coverage", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main() == 0
