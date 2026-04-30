#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

SECRET_ENV_RE = re.compile(r"(^|_)(SECRET|PASSWORD|API_KEY|TOKEN)(_|$)")
PLATFORM_OAUTH_CLIENT_SECRET_RE = re.compile(r"^PLATFORM_OAUTH_[A-Z0-9]+_CLIENT_SECRET$")
LEGACY_OAUTH_SECRET_RE = re.compile(r"\bOAUTH_SECRET_[A-Z0-9_]*\b")
GO_GETENV_RE = re.compile(r"os\.Getenv\(\s*([\"'])(?P<name>[^\"']+)\1\s*\)")
FORBIDDEN_LOG_FIELDS = {"token", "secret_id", "kv_value", "client_secret"}

PYTHON_SCAN_ROOT = Path("apps/control-plane/src/platform")
GO_SCAN_ROOT = Path("services")
PYTHON_EXCLUDES = {
    Path("apps/control-plane/src/platform/common/secret_provider.py"),
    Path("apps/control-plane/src/platform/connectors/security.py"),
}
GO_EXCLUDE_PREFIXES = (Path("services/shared/secrets"),)
VAULT_RESOLVER_ALLOWED = {
    Path("apps/control-plane/src/platform/common/secret_provider.py"),
    Path("apps/control-plane/src/platform/connectors/security.py"),
}
OAUTH_CLIENT_SECRET_ENV_ALLOWED = {
    Path("apps/control-plane/src/platform/auth/services/oauth_bootstrap.py"),
    Path("apps/control-plane/src/platform/auth/services/oauth_service.py"),
}
BASELINE_EXCEPTIONS = {
    (
        Path("apps/control-plane/src/platform/admin/bootstrap.py"),
        "direct secret-pattern environment read: PLATFORM_SUPERADMIN_PASSWORD",
    ),
    (
        Path("apps/control-plane/src/platform/common/clients/redis.py"),
        "direct secret-pattern environment read: REDIS_PASSWORD",
    ),
    (
        Path("services/reasoning-engine/pkg/persistence/redis.go"),
        "direct secret-pattern environment read: REDIS_PASSWORD",
    ),
    (
        Path("services/runtime-controller/pkg/config/config.go"),
        "direct secret-pattern environment read: REDIS_PASSWORD",
    ),
}


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    message: str


class ParseFailure(Exception):
    def __init__(self, path: Path, error: SyntaxError) -> None:
        super().__init__(f"{path}:{error.lineno}: {error.msg}")
        self.path = path
        self.error = error


def _is_secret_env_name(name: str) -> bool:
    return bool(SECRET_ENV_RE.search(name)) and "API_VERSION" not in name


def _is_oauth_client_secret_env_name(name: str) -> bool:
    return bool(PLATFORM_OAUTH_CLIENT_SECRET_RE.fullmatch(name))


def _is_oauth_client_secret_allowed(path: Path) -> bool:
    normalized = Path(*path.parts[-len(Path("apps/control-plane/src/platform/auth/services/oauth_bootstrap.py").parts) :])
    return normalized in OAUTH_CLIENT_SECRET_ENV_ALLOWED


def _is_excluded(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    if rel in PYTHON_EXCLUDES:
        return True
    return any(rel.is_relative_to(prefix) for prefix in GO_EXCLUDE_PREFIXES)


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _literal_first_arg(node: ast.Call) -> str | None:
    if not node.args:
        return None
    first = node.args[0]
    return first.value if isinstance(first, ast.Constant) and isinstance(first.value, str) else None


class PythonSecretVisitor(ast.NodeVisitor):
    def __init__(self, path: Path, source_lines: list[str]) -> None:
        self.path = path
        self.source_lines = source_lines
        self.violations: list[Violation] = []

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node.func)
        if name in {"os.getenv", "os.environ.get"}:
            env_name = _literal_first_arg(node)
            if (
                env_name is not None
                and _is_secret_env_name(env_name)
                and not (
                    _is_oauth_client_secret_env_name(env_name)
                    and _is_oauth_client_secret_allowed(self.path)
                )
            ):
                self.violations.append(
                    Violation(
                        self.path,
                        node.lineno,
                        f"direct secret-pattern environment read: {env_name}",
                    )
                )

        if name.endswith(".resolve"):
            line = self.source_lines[node.lineno - 1] if node.lineno <= len(self.source_lines) else ""
            if "vault" in line.lower():
                self.violations.append(
                    Violation(
                        self.path,
                        node.lineno,
                        "direct VaultResolver.resolve() call outside SecretProvider boundary",
                    )
                )

        if name.endswith(".info") or name.endswith(".error"):
            for keyword in node.keywords:
                if keyword.arg in FORBIDDEN_LOG_FIELDS:
                    self.violations.append(
                        Violation(
                            self.path,
                            node.lineno,
                            f"forbidden secret-like logger field: {keyword.arg}",
                        )
                    )
        self.generic_visit(node)


def scan_python_file(path: Path) -> list[Violation]:
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        raise ParseFailure(path, exc) from exc
    visitor = PythonSecretVisitor(path, source.splitlines())
    visitor.visit(tree)
    for line_number, line in enumerate(source.splitlines(), start=1):
        for match in LEGACY_OAUTH_SECRET_RE.finditer(line):
            visitor.violations.append(
                Violation(
                    path,
                    line_number,
                    f"legacy OAuth secret environment fallback is forbidden: {match.group(0)}",
                )
            )
    return visitor.violations


def scan_go_file(path: Path) -> list[Violation]:
    violations: list[Violation] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        for legacy_match in LEGACY_OAUTH_SECRET_RE.finditer(line):
            violations.append(
                Violation(
                    path,
                    line_number,
                    "legacy OAuth secret environment fallback is forbidden: "
                    f"{legacy_match.group(0)}",
                )
            )
        for match in GO_GETENV_RE.finditer(line):
            env_name = match.group("name")
            if _is_secret_env_name(env_name):
                violations.append(
                    Violation(
                        path,
                        line_number,
                        f"direct secret-pattern environment read: {env_name}",
                    )
                )
    return violations


def _iter_files(root: Path, scan_root: Path, suffix: str) -> Iterable[Path]:
    base = root / scan_root
    if not base.exists():
        return []
    return (path for path in base.rglob(f"*{suffix}") if path.is_file())


def scan(root: Path) -> list[Violation]:
    root = root.resolve()
    violations: list[Violation] = []
    for path in _iter_files(root, PYTHON_SCAN_ROOT, ".py"):
        if _is_excluded(path, root):
            continue
        rel = path.relative_to(root)
        file_violations = scan_python_file(path)
        if rel in VAULT_RESOLVER_ALLOWED:
            file_violations = [
                item for item in file_violations if "VaultResolver.resolve" not in item.message
            ]
        violations.extend(file_violations)
    for path in _iter_files(root, GO_SCAN_ROOT, ".go"):
        if _is_excluded(path, root):
            continue
        violations.extend(scan_go_file(path))
    return [
        violation
        for violation in violations
        if (violation.path.relative_to(root), violation.message) not in BASELINE_EXCEPTIONS
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check direct secret access outside providers.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)

    try:
        violations = scan(args.root)
    except ParseFailure as exc:
        print(exc, file=sys.stderr)
        return 2

    for violation in violations:
        print(f"{violation.path}:{violation.line}: {violation.message}")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
