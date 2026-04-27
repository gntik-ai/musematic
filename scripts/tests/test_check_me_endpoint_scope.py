from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check-me-endpoint-scope.py"


def _module():
    spec = importlib.util.spec_from_file_location("check_me_endpoint_scope", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_me_router_user_id_parameter_is_denied(tmp_path) -> None:
    module = _module()
    _write(
        tmp_path / "apps/control-plane/src/platform/me/router.py",
        "from fastapi import APIRouter\n"
        "router = APIRouter(prefix='/me')\n"
        "@router.get('/sessions')\n"
        "async def list_sessions(user_id: str):\n"
        "    return {}\n",
    )

    violations = module.scan(tmp_path)

    assert len(violations) == 1
    assert "user_id" in violations[0].message


def test_api_v1_me_prefix_user_id_parameter_is_denied(tmp_path) -> None:
    module = _module()
    _write(
        tmp_path / "apps/control-plane/src/platform/privacy/router_self_service.py",
        "from fastapi import APIRouter\n"
        "router = APIRouter(prefix='/api/v1/me')\n"
        "@router.get('/consent')\n"
        "async def list_consents(user_id: str):\n"
        "    return {}\n",
    )

    violations = module.scan(tmp_path)

    assert len(violations) == 1


def test_route_path_me_segment_user_id_parameter_is_denied(tmp_path) -> None:
    module = _module()
    _write(
        tmp_path / "apps/control-plane/src/platform/auth/router.py",
        "from fastapi import APIRouter\n"
        "router = APIRouter(prefix='/api/v1')\n"
        "@router.get('/me/activity')\n"
        "async def activity(user_id: str):\n"
        "    return {}\n",
    )

    violations = module.scan(tmp_path)

    assert len(violations) == 1


def test_me_router_current_user_scope_is_allowed(tmp_path) -> None:
    module = _module()
    _write(
        tmp_path / "apps/control-plane/src/platform/me/router.py",
        "from fastapi import APIRouter, Depends\n"
        "router = APIRouter(prefix='/me')\n"
        "@router.get('/sessions')\n"
        "async def list_sessions(current_user: dict = Depends(lambda: {})):\n"
        "    return {}\n",
    )

    assert module.scan(tmp_path) == []


def test_non_me_user_id_parameter_is_allowed(tmp_path) -> None:
    module = _module()
    _write(
        tmp_path / "apps/control-plane/src/platform/admin/router.py",
        "from fastapi import APIRouter\n"
        "router = APIRouter(prefix='/admin')\n"
        "@router.get('/users/{user_id}')\n"
        "async def get_user(user_id: str):\n"
        "    return {}\n",
    )

    assert module.scan(tmp_path) == []


def test_parse_error_is_reported(tmp_path) -> None:
    module = _module()
    path = tmp_path / "apps/control-plane/src/platform/me/bad.py"
    _write(path, "def nope(:\n")

    try:
        module.scan(tmp_path)
    except module.ParseFailure as exc:
        assert exc.path == path
    else:
        raise AssertionError("expected parse failure")
