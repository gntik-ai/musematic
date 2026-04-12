from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from platform.trust.exceptions import ATERunError, CertificationNotFoundError
from platform.trust.models import CertificationStatus
from platform.trust.schemas import ATERunRequest
from uuid import uuid4

import pytest

from tests.trust_support import build_ate_config_create, build_certification, build_trust_bundle


@pytest.mark.asyncio
async def test_ate_service_config_run_completion_and_status() -> None:
    bundle = build_trust_bundle()
    certification = build_certification(status=CertificationStatus.active)
    bundle.repository.certifications.append(certification)

    created = await bundle.ate_service.create_config("workspace-1", build_ate_config_create())
    listed = await bundle.ate_service.list_configs("workspace-1")
    fetched = await bundle.ate_service.get_config(created.id)
    run = await bundle.ate_service.run(
        ATERunRequest(ate_config_id=created.id, certification_id=certification.id)
    )
    await bundle.ate_service.handle_simulation_completed(
        {
            "simulation_id": run.simulation_id,
            "scenario_results": [{"summary": "Scenario A passed"}],
        }
    )
    status = await bundle.ate_service.get_run_status(run.simulation_id)

    assert listed.total == 1
    assert fetched.id == created.id
    assert status.status == "completed"
    assert len(bundle.repository.evidence_refs) == 1
    assert (
        "trust-evidence",
        f"ate-results/{run.simulation_id}/result.json",
    ) in bundle.object_storage.objects


@pytest.mark.asyncio
async def test_ate_service_marks_timed_out_runs() -> None:
    bundle = build_trust_bundle()
    certification = build_certification(status=CertificationStatus.active)
    bundle.repository.certifications.append(certification)
    config = await bundle.ate_service.create_config("workspace-1", build_ate_config_create())
    run = await bundle.ate_service.run(
        ATERunRequest(ate_config_id=config.id, certification_id=certification.id)
    )
    payload = json.loads(bundle.redis.strings[f"trust:ate:run:{run.simulation_id}"].decode("utf-8"))
    payload["started_at"] = (datetime.now(UTC) - timedelta(seconds=500)).isoformat()
    payload["timeout_seconds"] = 60
    bundle.redis.strings[f"trust:ate:run:{run.simulation_id}"] = json.dumps(payload).encode("utf-8")

    timed_out = await bundle.ate_service.scan_timed_out_runs()
    stored = json.loads(bundle.redis.strings[f"trust:ate:run:{run.simulation_id}"].decode("utf-8"))

    assert timed_out == 1
    assert stored["status"] == "timed_out"
    assert bundle.repository.evidence_refs[-1].summary == "timed_out"


@pytest.mark.asyncio
async def test_ate_service_handles_missing_configs_runs_and_statuses() -> None:
    bundle = build_trust_bundle()

    with pytest.raises(LookupError):
        await bundle.ate_service.get_config(uuid4())
    with pytest.raises(ATERunError):
        await bundle.ate_service.run(
            ATERunRequest(ate_config_id=uuid4(), certification_id=uuid4())
        )
    config = await bundle.ate_service.create_config("workspace-1", build_ate_config_create())
    with pytest.raises(CertificationNotFoundError):
        await bundle.ate_service.run(
            ATERunRequest(ate_config_id=config.id, certification_id=uuid4())
        )
    with pytest.raises(ATERunError):
        await bundle.ate_service.get_run_status("missing")


@pytest.mark.asyncio
async def test_ate_service_fallback_simulation_and_noop_completion_paths() -> None:
    bundle = build_trust_bundle()
    certification = build_certification(status=CertificationStatus.active)
    bundle.repository.certifications.append(certification)
    config = await bundle.ate_service.create_config("workspace-1", build_ate_config_create())
    bundle.ate_service.simulation_controller = None

    run = await bundle.ate_service.run(
        ATERunRequest(ate_config_id=config.id, certification_id=certification.id)
    )

    assert run.simulation_id
    await bundle.ate_service.handle_simulation_completed({})
    await bundle.ate_service.handle_simulation_completed({"simulation_id": "unknown"})
    await bundle.ate_service.handle_simulation_completed(
        {"simulation_id": run.simulation_id, "status": "passed"}
    )

    assert bundle.repository.evidence_refs[-1].summary == "passed"


@pytest.mark.asyncio
async def test_ate_service_timeout_scan_ignores_missing_non_started_and_fresh_runs() -> None:
    bundle = build_trust_bundle()

    class _ScanningRedis(type(bundle.redis)):
        async def scan(
            self,
            *,
            cursor: int,
            match: str,
            count: int,
        ) -> tuple[int, list[str]]:
            del match, count
            return (0, ["trust:ate:run:missing", *self.strings.keys()]) if cursor == 0 else (0, [])

    redis = _ScanningRedis()
    bundle.ate_service.redis_client = redis
    now = datetime.now(UTC)
    redis.client = redis
    redis.strings["trust:ate:run:completed"] = json.dumps(
        {
            "simulation_id": "completed",
            "certification_id": str(uuid4()),
            "status": "completed",
            "started_at": now.isoformat(),
        }
    ).encode("utf-8")
    redis.strings["trust:ate:run:fresh"] = json.dumps(
        {
            "simulation_id": "fresh",
            "certification_id": str(uuid4()),
            "status": "started",
            "started_at": now.isoformat(),
            "timeout_seconds": 3600,
        }
    ).encode("utf-8")

    assert await bundle.ate_service.scan_timed_out_runs() == 0
    assert bundle.repository.evidence_refs == []
