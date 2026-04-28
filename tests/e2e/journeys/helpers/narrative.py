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


@dataclass(slots=True)
class JourneyArtifactRecord:
    journey_id: str
    test_nodeid: str
    label: str
    href: str
    artifact_type: str


_journey_step_records: ContextVar[list[JourneyStepRecord]] = ContextVar(
    "journey_step_records",
    default=[],
)
_journey_step_counter: ContextVar[int] = ContextVar("journey_step_counter", default=0)
_journey_artifact_records: ContextVar[list[JourneyArtifactRecord]] = ContextVar(
    "journey_artifact_records",
    default=[],
)
_journey_records_by_nodeid: dict[str, list[JourneyStepRecord]] = {}
_journey_artifacts_by_nodeid: dict[str, list[JourneyArtifactRecord]] = {}
_journey_step_counters_by_nodeid: dict[str, int] = {}


def _journey_id_from_nodeid(nodeid: str) -> str:
    if not nodeid:
        return "unknown"
    stem = nodeid.rsplit("/", 1)[-1].split("::", 1)[0]
    if stem.startswith("test_j") and len(stem) >= 8:
        return stem[5:8]
    return "unknown"


def reset_journey_step_records(nodeid: str | None = None) -> None:
    resolved_nodeid = nodeid or current_test_nodeid()
    _journey_step_records.set([])
    _journey_step_counter.set(0)
    _journey_artifact_records.set([])
    if resolved_nodeid:
        _journey_records_by_nodeid[resolved_nodeid] = []
        _journey_artifacts_by_nodeid[resolved_nodeid] = []
        _journey_step_counters_by_nodeid[resolved_nodeid] = 0


def collect_journey_step_records(nodeid: str | None = None) -> list[JourneyStepRecord]:
    resolved_nodeid = nodeid or current_test_nodeid()
    if resolved_nodeid in _journey_records_by_nodeid:
        return list(_journey_records_by_nodeid[resolved_nodeid])
    return list(_journey_step_records.get())


def collect_journey_artifact_records(nodeid: str | None = None) -> list[JourneyArtifactRecord]:
    resolved_nodeid = nodeid or current_test_nodeid()
    if resolved_nodeid in _journey_artifacts_by_nodeid:
        return list(_journey_artifacts_by_nodeid[resolved_nodeid])
    return list(_journey_artifact_records.get())


def _add_artifact(label: str, href: str, artifact_type: str) -> None:
    nodeid = current_test_nodeid()
    records = list(_journey_artifact_records.get())
    artifact = JourneyArtifactRecord(
        journey_id=_journey_id_from_nodeid(nodeid),
        test_nodeid=nodeid,
        label=label,
        href=href,
        artifact_type=artifact_type,
    )
    records.append(artifact)
    _journey_artifact_records.set(records)
    if nodeid:
        _journey_artifacts_by_nodeid.setdefault(nodeid, []).append(artifact)


def add_snapshot_to_report(report, snapshot_path, label) -> None:
    href = str(snapshot_path)
    if report is not None and hasattr(report, "setdefault"):
        report.setdefault("snapshots", []).append({"label": label, "href": href})
    _add_artifact(str(label), href, "snapshot")


def add_link_to_report(label: str, href: str, artifact_type: str = "link") -> None:
    _add_artifact(label, href, artifact_type)


@contextmanager
def journey_step(description: str) -> Iterator[None]:
    nodeid = current_test_nodeid()
    records = list(_journey_step_records.get())
    step_index = _journey_step_counters_by_nodeid.get(nodeid, _journey_step_counter.get()) + 1
    _journey_step_counter.set(step_index)
    if nodeid:
        _journey_step_counters_by_nodeid[nodeid] = step_index
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
        record = JourneyStepRecord(
            journey_id=_journey_id_from_nodeid(nodeid),
            test_nodeid=nodeid,
            step_index=step_index,
            description=description,
            started_at=started_at.isoformat(),
            duration_ms=max(0, int((finished_at - started_at).total_seconds() * 1000)),
            status=status,
            error=error,
        )
        records.append(record)
        _journey_step_records.set(records)
        if nodeid:
            _journey_records_by_nodeid.setdefault(nodeid, []).append(record)
