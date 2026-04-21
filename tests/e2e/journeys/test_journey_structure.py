from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

VALID_CONTEXTS = {
    "a2a",
    "accounts",
    "agentops",
    "analytics",
    "audit",
    "auth",
    "connectors",
    "context-engineering",
    "discovery",
    "evaluation",
    "execution",
    "fleets",
    "governance",
    "ibor",
    "interactions",
    "knowledge",
    "marketplace",
    "mcp",
    "memory",
    "notifications",
    "policies",
    "reasoning",
    "registry",
    "runtime",
    "storage",
    "trust",
    "websocket",
    "workflows",
    "workspaces",
}
JOURNEY_FILE_PATTERN = re.compile(r"test_j\d{2}_[a-z_]+\.py$")
HELPER_ASSERT_NAMES = {"wait_for_execution", "assert_event_order", "assert_checkpoint_resumed"}
HELPER_CALLS_REQUIRING_JOURNEY_ID = {
    "attach_contract",
    "create_governance_chain",
    "create_workspace",
    "register_full_agent",
}


@dataclass(slots=True)
class JourneySummary:
    journey_id: str
    steps: int
    bare_asserts: int
    helper_asserts: int
    contexts: int

    @property
    def total_assertion_points(self) -> int:
        return self.steps + self.bare_asserts + self.helper_asserts


class StepBlockCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.step_nodes: list[ast.With | ast.AsyncWith] = []
        self.step_line_numbers: set[int] = set()

    def visit_With(self, node: ast.With) -> Any:
        if _contains_journey_step(node.items):
            self.step_nodes.append(node)
            self._remember_lines(node)
        self.generic_visit(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> Any:
        if _contains_journey_step(node.items):
            self.step_nodes.append(node)
            self._remember_lines(node)
        self.generic_visit(node)

    def _remember_lines(self, node: ast.With | ast.AsyncWith) -> None:
        for child in ast.walk(node):
            lineno = getattr(child, "lineno", None)
            if lineno is not None:
                self.step_line_numbers.add(int(lineno))


class AssertionCollector(ast.NodeVisitor):
    def __init__(self, excluded_lines: set[int]) -> None:
        self.excluded_lines = excluded_lines
        self.assert_lines: set[int] = set()
        self.helper_assert_lines: set[int] = set()

    def visit_Assert(self, node: ast.Assert) -> Any:
        if node.lineno not in self.excluded_lines:
            self.assert_lines.add(int(node.lineno))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> Any:
        name = _call_name(node)
        if name.startswith("assert_") or name in HELPER_ASSERT_NAMES:
            self.helper_assert_lines.add(int(node.lineno))
        self.generic_visit(node)


class JourneyIdUsageCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[str] = []

    def visit_Call(self, node: ast.Call) -> Any:
        name = _call_name(node)
        if name in HELPER_CALLS_REQUIRING_JOURNEY_ID:
            has_keyword = any(keyword.arg == "journey_id" for keyword in node.keywords if keyword.arg)
            first_arg = node.args[1] if name == "register_full_agent" and len(node.args) > 1 else (
                node.args[0] if node.args else None
            )
            has_positional = isinstance(first_arg, ast.Name) and first_arg.id == "JOURNEY_ID"
            if not has_keyword and not has_positional:
                self.violations.append(f"line {node.lineno}: call to `{name}` missing journey_id")
        self.generic_visit(node)


@pytest.mark.parametrize("journey_file", [None], ids=["all-journeys"])
def test_all_journeys_meet_structure(journey_file) -> None:
    del journey_file
    journeys_dir = Path(__file__).resolve().parent
    files = sorted(
        path
        for path in journeys_dir.glob("test_j[0-9][0-9]_*.py")
        if path.name != Path(__file__).name
    )
    if not files:
        pytest.skip("No journey files discovered yet")

    summaries: list[JourneySummary] = []
    violations: list[str] = []

    for path in files:
        file_violations, summary = _validate_journey_file(path)
        if file_violations:
            violations.append(f"{path.name}:")
            violations.extend(f"  - {item}" for item in file_violations)
        if summary is not None:
            summaries.append(summary)

    if violations:
        raise AssertionError("journey structure violations:\n\n" + "\n".join(violations))

    lines = [
        "Journey | Steps | Bare asserts | Helper asserts | Total | Contexts",
        "--------+-------+--------------+----------------+-------+---------",
    ]
    for summary in summaries:
        lines.append(
            f"{summary.journey_id:>6} | {summary.steps:>5} | {summary.bare_asserts:>12} | "
            f"{summary.helper_asserts:>14} | {summary.total_assertion_points:>5} | {summary.contexts:>8}"
        )
    print("\n".join(lines))


def _validate_journey_file(path: Path) -> tuple[list[str], JourneySummary]:
    text = path.read_text(encoding="utf-8")
    violations: list[str] = []
    if not JOURNEY_FILE_PATTERN.match(path.name):
        violations.append("journey file name must match pattern test_jNN_persona_hint.py")

    tree = ast.parse(text, filename=str(path))
    inventory = _parse_context_inventory(text, tree)
    invalid_contexts = sorted({item for item in inventory if item not in VALID_CONTEXTS})
    if invalid_contexts:
        violations.append(
            "unknown context(s) "
            + ", ".join(repr(item) for item in invalid_contexts)
            + "; must be one of: "
            + ", ".join(sorted(VALID_CONTEXTS))
        )
    if len(set(inventory) & VALID_CONTEXTS) < 4:
        violations.append(
            f"cross-context inventory has {len(set(inventory) & VALID_CONTEXTS)} valid contexts (required >= 4)"
        )

    journey_id = _module_constant(tree, "JOURNEY_ID")
    if not isinstance(journey_id, str) or not re.fullmatch(r"j\d{2}", journey_id):
        violations.append("JOURNEY_ID must be 'j01'..'j09'")
        resolved_journey_id = path.stem[5:8]
    else:
        resolved_journey_id = journey_id

    timeout_seconds = _module_constant(tree, "TIMEOUT_SECONDS")
    if not isinstance(timeout_seconds, int) or not 60 <= timeout_seconds <= 900:
        violations.append("TIMEOUT_SECONDS must be 60-900")

    markers = _collect_markers(tree)
    expected_marker = f"{resolved_journey_id}_{path.stem.split('_', 2)[-1]}"
    if "journey" not in markers:
        violations.append("missing marker(s): pytest.mark.journey")
    if expected_marker not in markers:
        violations.append(f"missing marker(s): pytest.mark.{expected_marker}")
    if "timeout" not in markers:
        violations.append("missing marker(s): pytest.mark.timeout(TIMEOUT_SECONDS)")

    step_collector = StepBlockCollector()
    step_collector.visit(tree)
    assertion_collector = AssertionCollector(step_collector.step_line_numbers)
    assertion_collector.visit(tree)
    journey_id_usage = JourneyIdUsageCollector()
    journey_id_usage.visit(tree)
    violations.extend(journey_id_usage.violations)

    steps = len(step_collector.step_nodes)
    bare_asserts = len(assertion_collector.assert_lines)
    helper_asserts = len(assertion_collector.helper_assert_lines)
    total_assertion_points = steps + bare_asserts + helper_asserts

    if steps < 10:
        violations.append(f"journey_step decorators/contexts: {steps} (required >= 10)")
    if total_assertion_points < 15:
        violations.append(f"assertion points: {total_assertion_points} (required >= 15)")

    return violations, JourneySummary(
        journey_id=resolved_journey_id,
        steps=steps,
        bare_asserts=bare_asserts,
        helper_asserts=helper_asserts,
        contexts=len(set(inventory) & VALID_CONTEXTS),
    )


def _parse_context_inventory(text: str, tree: ast.Module) -> list[str]:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == "# Cross-context inventory:":
            contexts: list[str] = []
            for candidate in lines[index + 1 :]:
                stripped = candidate.strip()
                if not stripped:
                    break
                if not stripped.startswith("# - "):
                    break
                contexts.append(stripped[4:].strip())
            if contexts:
                return contexts
    fallback = _module_constant(tree, "CROSS_CONTEXT_INVENTORY")
    if isinstance(fallback, list):
        return [str(item) for item in fallback]
    return []


def _module_constant(tree: ast.Module, name: str) -> Any:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    return None


def _contains_journey_step(items: list[ast.withitem]) -> bool:
    for item in items:
        expr = item.context_expr
        if isinstance(expr, ast.Call) and _call_name(expr) == "journey_step":
            return True
    return False


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _collect_markers(tree: ast.Module) -> set[str]:
    markers: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        for decorator in node.decorator_list:
            marker = _marker_name(decorator)
            if marker:
                markers.add(marker)
    return markers


def _marker_name(node: ast.AST) -> str | None:
    current = node
    if isinstance(current, ast.Call):
        current = current.func
    if not isinstance(current, ast.Attribute):
        return None
    if current.attr == "mark":
        return None
    return current.attr
