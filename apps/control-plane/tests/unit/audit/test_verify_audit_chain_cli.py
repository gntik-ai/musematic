"""T104 — smoke test for ``tools/verify_audit_chain.py``.

Confirms the CLI module is importable from the control-plane test environment
and that ``--help`` exits cleanly. The full integration (warm chain walk +
cold-storage enumeration) is exercised by the ``audit-chain-integrity`` CI
job which runs against a live cluster.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_module():
    repo_root = Path(__file__).resolve().parents[5]
    script = repo_root / "tools" / "verify_audit_chain.py"
    if not script.exists():
        pytest.skip(f"verify_audit_chain.py not found at {script}")
    spec = importlib.util.spec_from_file_location("verify_audit_chain_cli", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    module = _load_module()
    with pytest.raises(SystemExit) as info:
        module.main(["--help"])
    assert info.value.code == 0
    captured = capsys.readouterr()
    assert "verify" in captured.out.lower() or "audit" in captured.out.lower()


def test_cli_module_exposes_expected_surface() -> None:
    module = _load_module()
    assert callable(module.main)
    # Optional cold-storage scan helper must be present.
    assert callable(module._scan_cold_storage)
    # Warm-chain verifier is the SC-008 entrypoint.
    assert callable(module._verify_warm_chain)


def teardown_module() -> None:
    sys.modules.pop("verify_audit_chain_cli", None)
