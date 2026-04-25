from __future__ import annotations

import re
from dataclasses import dataclass
from platform.privacy_compliance.models import PrivacyDLPRule
from uuid import UUID


@dataclass(frozen=True, slots=True)
class DLPMatch:
    rule_id: UUID
    rule_name: str
    classification: str
    action: str
    start: int
    end: int

    @property
    def summary(self) -> str:
        return f"{self.classification}:{self.rule_name}"


@dataclass(frozen=True, slots=True)
class DLPEventInput:
    rule_id: UUID
    rule_name: str
    classification: str
    action_taken: str
    match_summary: str
    workspace_id: UUID | None


@dataclass(frozen=True, slots=True)
class DLPScanResult:
    output_text: str
    blocked: bool
    events: list[DLPEventInput]


class DLPScanner:
    def __init__(self, rules: list[PrivacyDLPRule]) -> None:
        self.rules = rules
        self._compiled = [
            (rule, re.compile(rule.pattern, re.IGNORECASE))
            for rule in rules
            if rule.enabled
        ]

    def scan(self, text: str, workspace_id: UUID | None) -> list[DLPMatch]:
        matches: list[DLPMatch] = []
        for rule, pattern in self._compiled:
            if rule.workspace_id is not None and rule.workspace_id != workspace_id:
                continue
            for match in pattern.finditer(text):
                if rule.name == "credit_card" and not _luhn_valid(match.group(0)):
                    continue
                matches.append(
                    DLPMatch(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        classification=rule.classification,
                        action=rule.action,
                        start=match.start(),
                        end=match.end(),
                    )
                )
        return matches

    def apply_actions(self, text: str, matches: list[DLPMatch]) -> DLPScanResult:
        blocked = any(match.action == "block" for match in matches)
        output = text
        for match in sorted(matches, key=lambda item: item.start, reverse=True):
            if match.action == "redact":
                output = (
                    output[: match.start]
                    + f"[REDACTED:{match.classification}]"
                    + output[match.end :]
                )
        return DLPScanResult(
            output_text=output,
            blocked=blocked,
            events=[
                DLPEventInput(
                    rule_id=match.rule_id,
                    rule_name=match.rule_name,
                    classification=match.classification,
                    action_taken=match.action,
                    match_summary=match.summary,
                    workspace_id=None,
                )
                for match in matches
            ],
        )


def _luhn_valid(value: str) -> bool:
    digits = [int(char) for char in re.sub(r"\D", "", value)]
    if len(digits) < 13:
        return False
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0

