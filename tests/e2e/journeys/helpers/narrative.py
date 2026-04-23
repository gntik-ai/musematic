from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Iterator

from journeys.helpers import current_test_nodeid


@dataclass(slots=True)
class JourneyStepRecord:
    journey_id: str
    test_nodeid: str
    step_index: int
    description: str
    started_at: str
    duration_ms: int
    status: str
    error: str | None = None


_journey_step_records: ContextVar[list[JourneyStepRecord]] = ContextVar(
    "journey_step_records",
    default=[],
)
_journey_step_counter: ContextVar[int] = ContextVar("journey_step_counter", default=0)


def _journey_id_from_nodeid(nodeid: str) -> str:
    if not nodeid:
        return "unknown"
    stem = nodeid.rsplit("/", 1)[-1].split("::", 1)[0]
    if stem.startswith("test_j") and len(stem) >= 8:
        return stem[5:8]
    return "unknown"


def reset_journey_step_records() -> None:
    _journey_step_records.set([])
    _journey_step_counter.set(0)


def collect_journey_step_records() -> list[JourneyStepRecord]:
    return list(_journey_step_records.get())


@contextmanager
def journey_step(description: str) -> Iterator[None]:
    nodeid = current_test_nodeid()
    records = list(_journey_step_records.get())
    step_index = _journey_step_counter.get() + 1
    _journey_step_counter.set(step_index)
    started_at = datetime.now(UTC)
    error: str | None = None
    status = "passed"

    try:
        yield
    except Exception as exc:
        status = "failed"
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        finished_at = datetime.now(UTC)
        records.append(
            JourneyStepRecord(
                journey_id=_journey_id_from_nodeid(nodeid),
                test_nodeid=nodeid,
                step_index=step_index,
                description=description,
                started_at=started_at.isoformat(),
                duration_ms=max(0, int((finished_at - started_at).total_seconds() * 1000)),
                status=status,
                error=error,
            )
        )
        _journey_step_records.set(records)
