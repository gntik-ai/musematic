from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
CONTROL_PLANE_DIR = ROOT / "apps/control-plane"
CONTROL_PLANE_PYTHON = CONTROL_PLANE_DIR / ".venv/bin/python"


@pytest.fixture(scope="session", autouse=True)
def ensure_seeded() -> None:
    """Override the global E2E seed fixture; these tests manage their own data."""


def run_command(
    args: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=cwd or ROOT,
        env={**os.environ, **(env or {})},
        check=False,
        text=True,
        capture_output=True,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"command failed: {' '.join(args)}\nstdout={result.stdout}\nstderr={result.stderr}"
        )
    return result


def require_kubectl_cluster() -> None:
    if shutil.which("kubectl") is None:
        pytest.skip("kubectl is required for live secrets E2E tests")
    result = run_command(["kubectl", "version", "--client"], check=False)
    if result.returncode != 0:
        pytest.skip("kubectl is not usable")
    result = run_command(["kubectl", "get", "namespace", "default"], check=False)
    if result.returncode != 0:
        pytest.skip("a reachable Kubernetes cluster is required")


def control_plane_python(
    code: str,
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    if not CONTROL_PLANE_PYTHON.exists():
        pytest.skip("control-plane venv is required for provider E2E tests")
    return run_command(
        [str(CONTROL_PLANE_PYTHON), "-c", code],
        cwd=CONTROL_PLANE_DIR,
        env={"PYTHONPATH": "src", **(env or {})},
    )


@pytest.fixture(scope="session")
def vault_dev_pod() -> str:
    require_kubectl_cluster()
    namespace = os.getenv("VAULT_NAMESPACE", "platform-security")
    selector = os.getenv("E2E_VAULT_SELECTOR", "app.kubernetes.io/name=vault")
    deadline = time.time() + 180
    while time.time() < deadline:
        result = run_command(
            ["kubectl", "-n", namespace, "get", "pods", "-l", selector, "-o", "json"],
            check=False,
        )
        if result.returncode == 0:
            payload = json.loads(result.stdout or "{}")
            for item in payload.get("items", []):
                name = item.get("metadata", {}).get("name")
                conditions = item.get("status", {}).get("conditions", [])
                ready = any(
                    condition.get("type") == "Ready" and condition.get("status") == "True"
                    for condition in conditions
                )
                if name and ready:
                    return str(name)
        time.sleep(3)
    pytest.skip("Vault dev pod did not become ready")


@pytest.fixture(scope="session")
def vault_root_token(vault_dev_pod: str) -> str:
    namespace = os.getenv("VAULT_NAMESPACE", "platform-security")
    result = run_command(
        [
            "kubectl",
            "-n",
            namespace,
            "exec",
            vault_dev_pod,
            "--",
            "printenv",
            "VAULT_DEV_ROOT_TOKEN_ID",
        ],
        check=False,
    )
    return (result.stdout.strip() if result.returncode == 0 else "") or "root"


@pytest.fixture(scope="session")
def vault_addr(vault_dev_pod: str) -> Iterator[str]:
    namespace = os.getenv("VAULT_NAMESPACE", "platform-security")
    local_port = os.getenv("PORT_VAULT", "30085")
    process = subprocess.Popen(
        [
            "kubectl",
            "-n",
            namespace,
            "port-forward",
            f"pod/{vault_dev_pod}",
            f"{local_port}:8200",
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    time.sleep(2)
    try:
        yield f"http://127.0.0.1:{local_port}"
    finally:
        process.terminate()
        with contextlib.suppress(Exception):
            process.wait(timeout=5)


@pytest.fixture(scope="session")
def kubernetes_secret_seed() -> dict[str, str]:
    require_kubectl_cluster()
    namespace = os.getenv("NAMESPACE", "platform")
    run_command(["kubectl", "create", "namespace", namespace], check=False)
    seed = {
        "secret/data/musematic/dev/oauth/e2e": "oauth-e2e-value",
        "secret/data/musematic/dev/model-providers/e2e": "model-e2e-value",
    }
    for name, value in {
        "musematic-dev-oauth-e2e": seed["secret/data/musematic/dev/oauth/e2e"],
        "musematic-dev-model-providers-e2e": seed[
            "secret/data/musematic/dev/model-providers/e2e"
        ],
    }.items():
        run_command(
            [
                "kubectl",
                "-n",
                namespace,
                "delete",
                "secret",
                name,
                "--ignore-not-found",
            ],
            check=False,
        )
        run_command(
            [
                "kubectl",
                "-n",
                namespace,
                "create",
                "secret",
                "generic",
                name,
                f"--from-literal=value={value}",
            ],
        )
    return seed


@pytest.fixture(scope="session")
def mock_mode_temp_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("vault-mock") / ".vault-secrets.json"
    path.write_text("{}", encoding="utf-8")
    return path
