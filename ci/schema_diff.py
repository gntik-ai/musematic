#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

HTTP_METHODS: frozenset[str] = frozenset(
    {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
)


def load_openapi(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"invalid OpenAPI document: {path}")
    return payload


def _iter_schema_nodes(node: Any, pointer: str = "$") -> list[tuple[str, dict[str, Any]]]:
    items: list[tuple[str, dict[str, Any]]] = []
    if isinstance(node, dict):
        if any(key in node for key in ("type", "properties", "items", "required", "$ref", "allOf", "anyOf", "oneOf")):
            items.append((pointer, node))
        for key, value in node.items():
            items.extend(_iter_schema_nodes(value, f"{pointer}/{key}"))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            items.extend(_iter_schema_nodes(value, f"{pointer}/{index}"))
    return items


def _schema_type(schema: dict[str, Any]) -> str | None:
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        return "|".join(str(item) for item in schema_type)
    if isinstance(schema_type, str):
        return schema_type
    ref = schema.get("$ref")
    if isinstance(ref, str):
        return f"ref:{ref}"
    return None


def detect_breaking_changes(previous: dict[str, Any], current: dict[str, Any]) -> list[str]:
    changes: list[str] = []

    previous_paths = previous.get("paths", {})
    current_paths = current.get("paths", {})
    if isinstance(previous_paths, dict) and isinstance(current_paths, dict):
        for removed_path in sorted(set(previous_paths) - set(current_paths)):
            changes.append(f"removed path: {removed_path}")
        for shared_path in sorted(set(previous_paths) & set(current_paths)):
            prev_methods = {
                key for key, value in previous_paths[shared_path].items() if key in HTTP_METHODS and isinstance(value, dict)
            }
            curr_methods = {
                key for key, value in current_paths[shared_path].items() if key in HTTP_METHODS and isinstance(value, dict)
            }
            for removed_method in sorted(prev_methods - curr_methods):
                changes.append(f"removed operation: {removed_method.upper()} {shared_path}")

    previous_nodes = dict(_iter_schema_nodes(previous))
    current_nodes = dict(_iter_schema_nodes(current))
    for pointer in sorted(set(previous_nodes) & set(current_nodes)):
        previous_node = previous_nodes[pointer]
        current_node = current_nodes[pointer]
        previous_type = _schema_type(previous_node)
        current_type = _schema_type(current_node)
        if previous_type is not None and current_type is not None and previous_type != current_type:
            changes.append(
                f"type changed at {pointer}: {previous_type} -> {current_type}"
            )

        previous_required = set(previous_node.get("required", [])) if isinstance(previous_node.get("required"), list) else set()
        current_required = set(current_node.get("required", [])) if isinstance(current_node.get("required"), list) else set()
        for field_name in sorted(current_required - previous_required):
            changes.append(f"new required field at {pointer}: {field_name}")

    return changes


def _has_breaking_marker(release_body: str) -> bool:
    return "BREAKING:" in release_body


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(
            "usage: schema_diff.py <previous_openapi.json> <current_openapi.json>",
            file=sys.stderr,
        )
        return 2

    previous = Path(argv[1])
    current = Path(argv[2])
    if not previous.exists():
        print(f"previous schema not found: {previous}", file=sys.stderr)
        return 2
    if not current.exists():
        print(f"current schema not found: {current}", file=sys.stderr)
        return 2

    previous_payload = load_openapi(previous)
    current_payload = load_openapi(current)
    changes = detect_breaking_changes(previous_payload, current_payload)
    if not changes:
        print("No breaking changes detected.")
        return 0

    for change in changes:
        print(change, file=sys.stderr)

    release_body = os.environ.get("GH_RELEASE_BODY", "")
    if _has_breaking_marker(release_body):
        print("Breaking changes allowed because GH_RELEASE_BODY contains BREAKING:.", file=sys.stderr)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
