#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import dataclasses
import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable

ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,}$")
SENSITIVE_RE = re.compile(r"(PASSWORD|SECRET|TOKEN|KEY|CREDENTIAL|PRIVATE)", re.I)
SENSITIVE_ENV_OVERRIDES = {
    "PLATFORM_VAULT_APPROLE_ROLE_ID",
    "VAULT_APPROLE_ROLE_ID",
}
CONFIG_RE = re.compile(
    r"(URL|URI|HOST|PORT|ENDPOINT|ADDR|ADDRESS|DSN|BROKERS|REGION|BUCKET|NAMESPACE|DOMAIN|PATH|FILE)",
    re.I,
)
SPECIAL_DESCRIPTIONS = {
    "PLATFORM_SUPERADMIN_PASSWORD_FILE": (
        "Path to a file containing the password, for compatibility with Docker secrets, "
        "sealed-secrets, and CI/CD secret stores. Related Helm value: "
        "`superadmin.passwordSecretRef`. Related requirement: FR-004."
    ),
    "PLATFORM_SUPERADMIN_PASSWORD": (
        "Initial super admin password. Mutually exclusive with "
        "`PLATFORM_SUPERADMIN_PASSWORD_FILE`. Related Helm value: "
        "`superadmin.passwordSecretRef`. Related requirement: FR-004."
    ),
}
VAULT_SENSITIVE_ANNOTATION = "Never log; never persist outside Vault."


@dataclasses.dataclass(slots=True)
class EnvVarEntry:
    name: str
    component: str
    required: str
    default: str
    description: str
    sensitivity: str
    sources: set[str] = dataclasses.field(default_factory=set)


def classify_sensitivity(name: str) -> str:
    if name in SENSITIVE_ENV_OVERRIDES:
        return "sensitive"
    if SENSITIVE_RE.search(name):
        return "sensitive"
    if CONFIG_RE.search(name):
        return "configuration"
    return "informational"


def describe_env_var(name: str, fallback: str) -> str:
    description = SPECIAL_DESCRIPTIONS.get(name, fallback)
    if (
        name.startswith(("PLATFORM_VAULT_", "VAULT_"))
        and classify_sensitivity(name) == "sensitive"
        and VAULT_SENSITIVE_ANNOTATION not in description
    ):
        description = f"{description} {VAULT_SENSITIVE_ANNOTATION}"
    return description


def normalize_default(value: object) -> str:
    if value is dataclasses.MISSING:
        return ""
    if value is None:
        return "`null`"
    if isinstance(value, str):
        return "`\"\"`" if value == "" else f"`{value}`"
    if isinstance(value, bool):
        return "`true`" if value else "`false`"
    return f"`{value}`"


def _literal(node: ast.AST | None) -> object:
    if node is None:
        return dataclasses.MISSING
    try:
        return ast.literal_eval(node)
    except Exception:
        if isinstance(node, ast.Call) and _call_name(node.func) == "Field":
            return _field_default(node)
        return "(computed)"


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _field_default(call: ast.Call) -> object:
    if call.args:
        return _literal(call.args[0])
    for keyword in call.keywords:
        if keyword.arg == "default":
            return _literal(keyword.value)
        if keyword.arg == "default_factory":
            return "(generated at runtime)"
    return dataclasses.MISSING


def _field_description(call: ast.Call) -> str:
    for keyword in call.keywords:
        if keyword.arg == "description":
            value = _literal(keyword.value)
            return value if isinstance(value, str) else ""
    return ""


def _alias_values(node: ast.AST | None) -> list[str]:
    if node is None:
        return []
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.Call) and _call_name(node.func) == "AliasChoices":
        values: list[str] = []
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                values.append(arg.value)
        return values
    return []


def _field_aliases(call: ast.Call) -> list[str]:
    for keyword in call.keywords:
        if keyword.arg in {"validation_alias", "alias"}:
            return _alias_values(keyword.value)
    return []


def _settings_env_prefix(class_node: ast.ClassDef) -> str:
    for item in class_node.body:
        if isinstance(item, ast.Assign):
            targets = [target.id for target in item.targets if isinstance(target, ast.Name)]
            if "model_config" not in targets:
                continue
            if isinstance(item.value, ast.Call) and _call_name(item.value.func) == "SettingsConfigDict":
                for keyword in item.value.keywords:
                    if keyword.arg == "env_prefix":
                        value = _literal(keyword.value)
                        return value if isinstance(value, str) else ""
    return ""


def _is_settings_class(class_node: ast.ClassDef) -> bool:
    if not class_node.name.endswith("Settings"):
        return False
    return any(_call_name(base) == "BaseSettings" for base in class_node.bases) or class_node.name == "PlatformSettings"


def _annotation_name(node: ast.AST | None) -> str:
    if node is None:
        return ""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Subscript):
        return _annotation_name(node.value)
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.BinOp):
        return f"{_annotation_name(node.left)}|{_annotation_name(node.right)}"
    return ""


def _looks_like_nested_settings(item: ast.AnnAssign) -> bool:
    annotation = _annotation_name(item.annotation)
    if annotation.endswith("Settings") and annotation != "PlatformSettings":
        return True
    if isinstance(item.value, ast.Call) and _call_name(item.value.func) == "Field":
        for keyword in item.value.keywords:
            if keyword.arg == "default_factory" and _call_name(keyword.value).endswith("Settings"):
                return True
    return False


def _component_name(class_name: str) -> str:
    return class_name.removesuffix("Settings") or class_name


def _env_name_from_field(env_prefix: str, field_name: str) -> str:
    if field_name.isupper():
        return f"{env_prefix}{field_name}" if env_prefix else field_name
    return f"{env_prefix}{field_name.upper()}"


def parse_settings_entries(config_path: Path) -> list[EnvVarEntry]:
    tree = ast.parse(config_path.read_text(encoding="utf-8"))
    entries: list[EnvVarEntry] = []

    for class_node in [node for node in tree.body if isinstance(node, ast.ClassDef)]:
        if not _is_settings_class(class_node):
            continue
        env_prefix = _settings_env_prefix(class_node)
        component = _component_name(class_node.name)
        for item in class_node.body:
            if not isinstance(item, ast.AnnAssign) or not isinstance(item.target, ast.Name):
                continue
            if _looks_like_nested_settings(item):
                continue

            field_name = item.target.id
            aliases: list[str] = []
            default = dataclasses.MISSING
            description = ""
            if isinstance(item.value, ast.Call) and _call_name(item.value.func) == "Field":
                aliases = _field_aliases(item.value)
                default = _field_default(item.value)
                description = _field_description(item.value)
            else:
                default = _literal(item.value)

            env_names = aliases or [_env_name_from_field(env_prefix, field_name)]
            for env_name in env_names:
                if not ENV_NAME_RE.match(env_name):
                    continue
                entries.append(
                    EnvVarEntry(
                        name=env_name,
                        component=component,
                        required="required" if default is dataclasses.MISSING else "optional",
                        default=normalize_default(default),
                        description=describe_env_var(
                            env_name,
                            description or f"Configures `{field_name}` for {component}.",
                        ),
                        sensitivity=classify_sensitivity(env_name),
                        sources={config_path.as_posix()},
                    )
                )

    entries.extend(_parse_flat_mapping_entries(tree, config_path))
    return entries


def _parse_flat_mapping_entries(tree: ast.Module, config_path: Path) -> list[EnvVarEntry]:
    entries: list[EnvVarEntry] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "mappings" for target in node.targets):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        for key, value in zip(node.value.keys, node.value.values, strict=False):
            if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                continue
            env_name = key.value
            if not ENV_NAME_RE.match(env_name):
                continue
            component = "Platform"
            if isinstance(value, ast.Tuple) and value.elts:
                first = value.elts[0]
                if (
                    len(value.elts) > 1
                    and isinstance(first, ast.Constant)
                    and isinstance(first.value, str)
                ):
                    component = first.value.replace("_", " ").title().replace(" ", "")
            entries.append(
                EnvVarEntry(
                    name=env_name,
                    component=component,
                    required="optional",
                    default="",
                    description=describe_env_var(
                        env_name,
                        "Accepted by the platform flat-settings compatibility mapper.",
                    ),
                    sensitivity=classify_sensitivity(env_name),
                    sources={config_path.as_posix()},
                )
            )
    return entries


def _constant_env_arg(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and ENV_NAME_RE.match(node.value):
        return node.value
    return None


def parse_python_env_entries(root: Path) -> list[EnvVarEntry]:
    entries: list[EnvVarEntry] = []
    if not root.exists():
        return entries
    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        rel = path.as_posix()
        for node in ast.walk(tree):
            env_name: str | None = None
            default = dataclasses.MISSING
            required = "optional"
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if (
                        node.func.attr == "getenv"
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "os"
                    ):
                        env_name = _constant_env_arg(node.args[0] if node.args else None)
                        if len(node.args) > 1:
                            default = _literal(node.args[1])
                        else:
                            required = "required"
                    elif (
                        node.func.attr == "get"
                        and isinstance(node.func.value, ast.Attribute)
                        and node.func.value.attr == "environ"
                    ):
                        env_name = _constant_env_arg(node.args[0] if node.args else None)
                        if len(node.args) > 1:
                            default = _literal(node.args[1])
            elif isinstance(node, ast.Subscript):
                if (
                    isinstance(node.value, ast.Attribute)
                    and node.value.attr == "environ"
                    and isinstance(node.value.value, ast.Name)
                    and node.value.value.id == "os"
                ):
                    env_name = _constant_env_arg(node.slice)
                    required = "required"
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                parent = parents.get(node)
                if _is_handled_env_parent(parent):
                    continue
                env_name = node.value if ENV_NAME_RE.match(node.value) else None
            if not env_name:
                continue
            entries.append(
                EnvVarEntry(
                    name=env_name,
                    component="Other",
                    required=required,
                    default=normalize_default(default),
                    description=describe_env_var(env_name, "Referenced directly by Python code."),
                    sensitivity=classify_sensitivity(env_name),
                    sources={rel},
                )
            )
    return entries


def _is_handled_env_parent(parent: ast.AST | None) -> bool:
    if isinstance(parent, ast.Call) and isinstance(parent.func, ast.Attribute):
        return (
            parent.func.attr == "getenv"
            and isinstance(parent.func.value, ast.Name)
            and parent.func.value.id == "os"
        ) or (
            parent.func.attr == "get"
            and isinstance(parent.func.value, ast.Attribute)
            and parent.func.value.attr == "environ"
        )
    if isinstance(parent, ast.Subscript):
        return (
            isinstance(parent.value, ast.Attribute)
            and parent.value.attr == "environ"
            and isinstance(parent.value.value, ast.Name)
            and parent.value.value.id == "os"
        )
    return False


def parse_go_env_entries(root: Path) -> list[EnvVarEntry]:
    entries: list[EnvVarEntry] = []
    if not root.exists():
        return entries
    patterns = [
        re.compile(r"os\.Getenv\(\s*\"([A-Z][A-Z0-9_]{2,})\"\s*\)"),
        re.compile(r"\b(?:envString|envBool|envInt|envDuration|envFloat)\(\s*\"([A-Z][A-Z0-9_]{2,})\""),
    ]
    for path in sorted(root.rglob("*.go")):
        text = path.read_text(encoding="utf-8")
        for pattern in patterns:
            for match in pattern.finditer(text):
                env_name = match.group(1)
                entries.append(
                    EnvVarEntry(
                        name=env_name,
                        component="GoServices",
                        required="optional",
                        default="",
                        description=describe_env_var(
                            env_name, "Referenced directly by Go service code."
                        ),
                        sensitivity=classify_sensitivity(env_name),
                        sources={path.as_posix()},
                    )
                )
    return entries


def parse_helm_env_entries(root: Path) -> list[EnvVarEntry]:
    entries: list[EnvVarEntry] = []
    if not root.exists():
        return entries
    name_re = re.compile(r"^\s*-\s*name:\s*['\"]?([A-Z][A-Z0-9_]{2,})['\"]?\s*$")
    for path in sorted(root.rglob("*.yaml")):
        for line in path.read_text(encoding="utf-8").splitlines():
            match = name_re.match(line)
            if not match:
                continue
            env_name = match.group(1)
            entries.append(
                EnvVarEntry(
                    name=env_name,
                    component="Helm",
                    required="optional",
                    default="",
                    description=describe_env_var(
                        env_name,
                        "Declared as a Kubernetes container environment variable.",
                    ),
                    sensitivity=classify_sensitivity(env_name),
                    sources={path.as_posix()},
                )
            )
    return entries


def merge_entries(entries: Iterable[EnvVarEntry]) -> list[EnvVarEntry]:
    merged: dict[str, EnvVarEntry] = {}
    priority = {"required": 0, "optional": 1}
    for entry in entries:
        existing = merged.get(entry.name)
        if existing is None:
            merged[entry.name] = dataclasses.replace(entry, sources=set(entry.sources))
            continue
        existing.sources.update(entry.sources)
        if existing.component == "Other" and entry.component != "Other":
            existing.component = entry.component
            existing.description = entry.description
        if existing.default == "" and entry.default:
            existing.default = entry.default
        if priority[entry.required] < priority[existing.required]:
            existing.required = entry.required
        if existing.sensitivity != "sensitive" and entry.sensitivity == "sensitive":
            existing.sensitivity = "sensitive"
    return sorted(merged.values(), key=lambda item: (item.component.lower(), item.name))


def collect_env_vars(repo_root: Path) -> list[EnvVarEntry]:
    config_path = repo_root / "apps/control-plane/src/platform/common/config.py"
    entries: list[EnvVarEntry] = []
    if config_path.exists():
        entries.extend(parse_settings_entries(config_path))
    entries.extend(parse_python_env_entries(repo_root / "apps/control-plane/src/platform"))
    entries.extend(parse_go_env_entries(repo_root / "services"))
    entries.extend(parse_helm_env_entries(repo_root / "deploy/helm"))
    merged = merge_entries(entries)
    for entry in merged:
        relative_sources: set[str] = set()
        for source in entry.sources:
            try:
                relative_sources.add(Path(source).resolve().relative_to(repo_root).as_posix())
            except ValueError:
                relative_sources.add(source)
        entry.sources = relative_sources
    return merged


def render_markdown(entries: Iterable[EnvVarEntry]) -> str:
    groups: dict[str, list[EnvVarEntry]] = defaultdict(list)
    for entry in entries:
        groups[entry.component].append(entry)

    lines = [
        "# Environment Variables",
        "",
        "This page is generated by `scripts/generate-env-docs.py`. Do not edit it manually.",
        "",
        "| Variable | Required | Default | Sensitivity | Description | Sources |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for component in sorted(groups, key=str.lower):
        lines.extend(["", f"## {component}", ""])
        lines.append("| Variable | Required | Default | Sensitivity | Description | Sources |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for entry in sorted(groups[component], key=lambda item: item.name):
            sources = "<br>".join(f"`{source}`" for source in sorted(entry.sources)[:5])
            if len(entry.sources) > 5:
                sources += f"<br>+{len(entry.sources) - 5} more"
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{entry.name}`",
                        entry.required,
                        entry.default or "-",
                        entry.sensitivity,
                        entry.description.replace("|", "\\|"),
                        sources,
                    ]
                )
                + " |"
            )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate the environment variables reference.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    content = render_markdown(collect_env_vars(args.repo_root.resolve()))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
    else:
        print(content, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
