from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check-admin-role-gates.py"


def _module():
    spec = importlib.util.spec_from_file_location("check_admin_role_gates", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_endpoint_signature_role_gate_passes(tmp_path: Path) -> None:
    module = _module()
    _write(
        tmp_path / "apps/control-plane/src/platform/admin/routers/vault.py",
        """
from fastapi import APIRouter, Depends
from platform.admin.rbac import require_superadmin

router = APIRouter()

@router.get("/status")
async def status(_current_user=Depends(require_superadmin)):
    return {}
""",
    )

    assert module.scan(tmp_path) == []


def test_endpoint_decorator_role_gate_passes(tmp_path: Path) -> None:
    module = _module()
    _write(
        tmp_path / "apps/control-plane/src/platform/admin/routers/vault.py",
        """
from fastapi import APIRouter, Depends
from platform.admin.rbac import require_admin

router = APIRouter()

@router.post("/flush", dependencies=[Depends(require_admin)])
async def flush():
    return {}
""",
    )

    assert module.scan(tmp_path) == []


def test_missing_role_gate_is_reported(tmp_path: Path) -> None:
    module = _module()
    _write(
        tmp_path / "apps/control-plane/src/platform/admin/routers/vault.py",
        """
from fastapi import APIRouter

router = APIRouter()

@router.post("/flush")
async def flush():
    return {}
""",
    )

    failures = module.scan(tmp_path)

    assert len(failures) == 1
    assert "flush missing admin role gate" in failures[0]
