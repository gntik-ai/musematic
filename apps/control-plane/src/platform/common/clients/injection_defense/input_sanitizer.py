"""Input sanitisation layer for model router calls."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from platform.common.clients.injection_defense.system_prompt_hardener import quote_user_data
from platform.model_catalog.exceptions import PromptInjectionBlocked
from typing import Any


@dataclass(frozen=True, slots=True)
class InjectionFinding:
    layer: str
    pattern_name: str
    severity: str
    action_taken: str


@dataclass(frozen=True, slots=True)
class SanitizedInput:
    text: str
    findings: list[InjectionFinding]
    blocked: bool = False


def sanitize_text(text: str, patterns: Sequence[Any]) -> SanitizedInput:
    findings: list[InjectionFinding] = []
    sanitized = text
    for pattern in patterns:
        regex = getattr(pattern, "pattern_regex", "")
        action = str(getattr(pattern, "action", "strip"))
        name = str(getattr(pattern, "pattern_name", "unnamed"))
        severity = str(getattr(pattern, "severity", "medium"))
        try:
            compiled = re.compile(regex, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        except re.error:
            continue
        if compiled.search(sanitized) is None:
            continue
        findings.append(
            InjectionFinding(
                layer="input_sanitizer",
                pattern_name=name,
                severity=severity,
                action_taken=action,
            )
        )
        if action == "reject":
            raise PromptInjectionBlocked(
                "PROMPT_INJECTION_BLOCKED",
                "Input matched a reject prompt-injection pattern.",
                {"pattern_name": name, "severity": severity},
            )
        if action == "quote_as_data":
            sanitized = compiled.sub(lambda match: quote_user_data(match.group(0)), sanitized)
        else:
            sanitized = compiled.sub("", sanitized)
    return SanitizedInput(text=sanitized, findings=findings)


def sanitize_messages(
    messages: list[dict[str, Any]],
    patterns: Sequence[Any],
) -> tuple[list[dict[str, Any]], list[InjectionFinding]]:
    sanitized_messages: list[dict[str, Any]] = []
    findings: list[InjectionFinding] = []
    for message in messages:
        cloned = dict(message)
        if cloned.get("role") == "user" and isinstance(cloned.get("content"), str):
            result = sanitize_text(str(cloned["content"]), patterns)
            cloned["content"] = result.text
            findings.extend(result.findings)
        sanitized_messages.append(cloned)
    return sanitized_messages, findings
