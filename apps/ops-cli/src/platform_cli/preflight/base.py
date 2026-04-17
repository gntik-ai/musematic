"""Base interfaces and orchestration for preflight checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class PreflightResult:
    """Outcome of a single preflight check."""

    passed: bool
    message: str
    remediation: str | None = None


class PreflightCheck(Protocol):
    """Protocol implemented by all preflight checks."""

    name: str
    description: str

    async def check(self) -> PreflightResult:
        """Run the check and return the result."""


@dataclass(slots=True)
class PreflightSummary:
    """Aggregated preflight status for a batch of checks."""

    passed: bool
    results: list[tuple[str, PreflightResult]]

    @property
    def passed_count(self) -> int:
        return sum(1 for _, result in self.results if result.passed)

    @property
    def failed_count(self) -> int:
        return len(self.results) - self.passed_count


class PreflightRunner:
    """Run a sequence of preflight checks."""

    def __init__(self, checks: list[PreflightCheck]) -> None:
        self._checks = checks

    async def run(self) -> PreflightSummary:
        """Run all configured checks sequentially and aggregate the result."""

        results: list[tuple[str, PreflightResult]] = []
        for check in self._checks:
            result = await check.check()
            results.append((check.name, result))
        return PreflightSummary(
            passed=all(result.passed for _, result in results),
            results=results,
        )
