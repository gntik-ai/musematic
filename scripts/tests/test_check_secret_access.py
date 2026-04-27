from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check-secret-access.py"


def _module():
    spec = importlib.util.spec_from_file_location("check_secret_access", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_python_secret_env_read_is_denied(tmp_path) -> None:
    module = _module()
    _write(
        tmp_path / "apps/control-plane/src/platform/auth/service.py",
        "import os\nvalue = os.getenv('PLATFORM_API_KEY')\n",
    )

    violations = module.scan(tmp_path)

    assert len(violations) == 1
    assert "PLATFORM_API_KEY" in violations[0].message


def test_python_non_secret_env_read_is_allowed(tmp_path) -> None:
    module = _module()
    _write(
        tmp_path / "apps/control-plane/src/platform/auth/service.py",
        "import os\nvalue = os.getenv('PLATFORM_API_VERSION')\n",
    )

    assert module.scan(tmp_path) == []


def test_secret_provider_impl_is_excluded(tmp_path) -> None:
    module = _module()
    _write(
        tmp_path / "apps/control-plane/src/platform/common/secret_provider.py",
        "import os\nvalue = os.getenv('PLATFORM_API_KEY')\n",
    )

    assert module.scan(tmp_path) == []


def test_go_secret_env_read_is_denied(tmp_path) -> None:
    module = _module()
    _write(
        tmp_path / "services/runtime-controller/main.go",
        'package main\nimport "os"\nvar _ = os.Getenv("RUNTIME_TOKEN")\n',
    )

    violations = module.scan(tmp_path)

    assert len(violations) == 1
    assert "RUNTIME_TOKEN" in violations[0].message


def test_go_shared_secrets_package_is_excluded(tmp_path) -> None:
    module = _module()
    _write(
        tmp_path / "services/shared/secrets/client.go",
        'package secrets\nimport "os"\nvar _ = os.Getenv("VAULT_TOKEN")\n',
    )

    assert module.scan(tmp_path) == []


def test_parse_error_is_reported(tmp_path) -> None:
    module = _module()
    path = tmp_path / "apps/control-plane/src/platform/auth/bad.py"
    _write(path, "def nope(:\n")

    try:
        module.scan(tmp_path)
    except module.ParseFailure as exc:
        assert exc.path == path
    else:
        raise AssertionError("expected parse failure")


def test_vault_resolver_direct_call_is_denied(tmp_path) -> None:
    module = _module()
    _write(
        tmp_path / "apps/control-plane/src/platform/auth/service.py",
        "def f(vault):\n    return vault.resolve('path', 'key')\n",
    )

    violations = module.scan(tmp_path)

    assert len(violations) == 1
    assert "VaultResolver.resolve" in violations[0].message


def test_secret_like_logger_fields_are_denied(tmp_path) -> None:
    module = _module()
    _write(
        tmp_path / "apps/control-plane/src/platform/auth/service.py",
        "def f(logger):\n    logger.info('x', token='abc')\n",
    )

    violations = module.scan(tmp_path)

    assert len(violations) == 1
    assert "token" in violations[0].message
