"""Output validation layer for model router calls."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from platform.common.debug_logging.redaction import SECRET_REGEX
from platform.model_catalog.exceptions import PromptInjectionBlocked
from typing import Any


@dataclass(frozen=True, slots=True)
class OutputValidationResult:
    text: str
    findings: list[dict[str, str]]


_ROLE_REVERSAL_REGEX: tuple[str, ...] = (
    r"ignore (all )?(previous|prior) instructions",
    r"you are now (system|developer|admin)",
    r"reveal (the )?(system|developer) prompt",
)


def validate_output(
    text: str,
    patterns: Sequence[Any],
    *,
    attention_service: Any | None = None,
) -> OutputValidationResult:
    findings: list[dict[str, str]] = []
    sanitized = text
    synthetic_patterns = [
        {
            "pattern_regex": regex,
            "pattern_name": "debug-secret-redaction",
            "severity": "high",
            "action": "redact",
        }
        for regex in SECRET_REGEX
    ] + [
        {
            "pattern_regex": regex,
            "pattern_name": "role-reversal-output",
            "severity": "high",
            "action": "block",
        }
        for regex in _ROLE_REVERSAL_REGEX
    ]
    for pattern in [*synthetic_patterns, *patterns]:
        regex = str(_get(pattern, "pattern_regex", ""))
        action = str(_get(pattern, "action", "redact"))
        severity = str(_get(pattern, "severity", "medium"))
        name = str(_get(pattern, "pattern_name", "unnamed"))
        try:
            compiled = re.compile(regex, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        except re.error:
            continue
        if compiled.search(sanitized) is None:
            continue
        findings.append(
            {
                "layer": "output_validator",
                "pattern_name": name,
                "severity": severity,
                "action_taken": action,
            }
        )
        if severity in {"high", "critical"} and attention_service is not None:
            raise_request = getattr(attention_service, "raise_request", None)
            if callable(raise_request):
                raise_request(
                    "prompt_injection_output_detected",
                    {"pattern_name": name, "severity": severity},
                )
        if action in {"block", "reject"}:
            raise PromptInjectionBlocked(
                "PROMPT_INJECTION_BLOCKED",
                "Output matched a blocking prompt-injection pattern.",
                {"pattern_name": name, "severity": severity},
            )
        sanitized = compiled.sub("[REDACTED]", sanitized)
    return OutputValidationResult(text=sanitized, findings=findings)


def _get(pattern: Any, key: str, default: str) -> Any:
    if isinstance(pattern, dict):
        return pattern.get(key, default)
    return getattr(pattern, key, default)
