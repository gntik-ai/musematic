"""Kubernetes-specific preflight checks."""

from __future__ import annotations

import subprocess

from platform_cli.preflight.base import PreflightResult


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        check=False,
        text=True,
    )


class KubectlAccessCheck:
    """Validate cluster reachability through kubectl."""

    name = "kubectl-access"
    description = "Verify kubectl can reach the target cluster."

    async def check(self) -> PreflightResult:
        result = _run_command(["kubectl", "cluster-info"])
        if result.returncode == 0:
            return PreflightResult(True, "kubectl cluster-info succeeded")
        return PreflightResult(
            False,
            result.stderr.strip() or "kubectl cluster-info failed",
            "Verify kubeconfig context and cluster network reachability.",
        )


class NamespacePermissionCheck:
    """Validate namespace create permissions via server-side dry-run."""

    name = "namespace-permission"
    description = "Verify namespace creation permissions."

    def __init__(self, namespace: str = "platform") -> None:
        self._namespace = namespace

    async def check(self) -> PreflightResult:
        result = _run_command(
            [
                "kubectl",
                "create",
                "namespace",
                self._namespace,
                "--dry-run=server",
                "-o",
                "yaml",
            ]
        )
        if result.returncode == 0:
            return PreflightResult(True, f"Namespace {self._namespace} can be created")
        return PreflightResult(
            False,
            result.stderr.strip() or "Namespace permission check failed",
            "Grant create permissions for namespaces or choose an existing namespace.",
        )


class StorageClassCheck:
    """Verify that the requested storage class is available."""

    name = "storage-class"
    description = "Verify the configured StorageClass exists."

    def __init__(self, storage_class: str) -> None:
        self._storage_class = storage_class

    async def check(self) -> PreflightResult:
        result = _run_command(["kubectl", "get", "storageclass", self._storage_class])
        if result.returncode == 0:
            return PreflightResult(True, f"StorageClass {self._storage_class} is available")
        return PreflightResult(
            False,
            result.stderr.strip() or f"StorageClass {self._storage_class} not found",
            "Use --storage-class to select an existing StorageClass.",
        )


class IngressControllerCheck:
    """Verify ingress classes can be listed by the current principal."""

    name = "ingress-controller"
    description = "Verify ingress classes can be listed."

    async def check(self) -> PreflightResult:
        result = _run_command(["kubectl", "get", "ingressclass"])
        if result.returncode == 0:
            return PreflightResult(True, "Ingress classes are accessible")
        return PreflightResult(
            False,
            result.stderr.strip() or "Unable to list ingress classes",
            (
                "Install an ingress controller or ensure the current principal can "
                "list ingress classes."
            ),
        )
