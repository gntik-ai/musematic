from __future__ import annotations

import json
from datetime import UTC, datetime
from platform.trust.exceptions import ATERunError, CertificationNotFoundError
from platform.trust.models import EvidenceType, TrustATEConfiguration, TrustCertificationEvidenceRef
from platform.trust.repository import TrustRepository
from platform.trust.schemas import (
    ATEConfigCreate,
    ATEConfigListResponse,
    ATEConfigResponse,
    ATERunRequest,
    ATERunResponse,
)
from typing import Any
from uuid import UUID, uuid4


class ATEService:
    def __init__(
        self,
        *,
        repository: TrustRepository,
        settings: Any,
        object_storage: Any,
        simulation_controller: Any | None,
        redis_client: Any,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.object_storage = object_storage
        self.simulation_controller = simulation_controller
        self.redis_client = redis_client

    async def create_config(self, workspace_id: str, data: ATEConfigCreate) -> ATEConfigResponse:
        version = await self.repository.get_latest_ate_config_version(workspace_id, data.name) + 1
        await self.repository.deactivate_ate_configs(workspace_id, data.name)
        config = await self.repository.create_ate_config(
            TrustATEConfiguration(
                workspace_id=workspace_id,
                name=data.name,
                version=version,
                description=data.description,
                is_active=True,
                test_scenarios=data.test_scenarios,
                golden_dataset_ref=data.golden_dataset_ref,
                scoring_config=data.scoring_config,
                timeout_seconds=data.timeout_seconds,
            )
        )
        return ATEConfigResponse.model_validate(config)

    async def list_configs(self, workspace_id: str) -> ATEConfigListResponse:
        items = await self.repository.list_ate_configs_for_workspace(workspace_id)
        return ATEConfigListResponse(
            items=[ATEConfigResponse.model_validate(item) for item in items],
            total=len(items),
        )

    async def get_config(self, config_id: UUID) -> ATEConfigResponse:
        item = await self.repository.get_ate_config(config_id)
        if item is None:
            raise LookupError(str(config_id))
        return ATEConfigResponse.model_validate(item)

    async def run(self, request: ATERunRequest) -> ATERunResponse:
        config = await self.repository.get_ate_config(request.ate_config_id)
        if config is None:
            raise ATERunError("ATE configuration not found")
        certification = await self.repository.get_certification(request.certification_id)
        if certification is None:
            raise CertificationNotFoundError(request.certification_id)
        create_simulation = getattr(self.simulation_controller, "create_simulation", None)
        payload = {
            "workspace_id": config.workspace_id,
            "ate_config_id": str(config.id),
            "certification_id": str(certification.id),
            "scenarios": config.test_scenarios,
            "scoring_config": config.scoring_config,
        }
        if create_simulation is not None:
            result = await create_simulation(config=payload)
            simulation_id = str(
                result.get("simulation_id")
                if isinstance(result, dict)
                else getattr(result, "simulation_id", uuid4())
            )
        else:
            simulation_id = str(uuid4())
        ttl = int(config.timeout_seconds) + 300
        await self.redis_client.set(
            self._run_key(simulation_id),
            json.dumps(
                {
                    "simulation_id": simulation_id,
                    "ate_config_id": str(config.id),
                    "certification_id": str(certification.id),
                    "workspace_id": config.workspace_id,
                    "timeout_seconds": config.timeout_seconds,
                    "started_at": datetime.now(UTC).isoformat(),
                    "status": "started",
                }
            ).encode("utf-8"),
            ttl=ttl,
        )
        return ATERunResponse(
            simulation_id=simulation_id,
            ate_config_id=str(config.id),
            certification_id=str(certification.id),
            status="started",
        )

    async def get_run_status(self, simulation_id: str) -> ATERunResponse:
        value = await self.redis_client.get(self._run_key(simulation_id))
        if value is None:
            raise ATERunError("ATE run not found", simulation_id=simulation_id)
        payload = json.loads(value.decode("utf-8"))
        return ATERunResponse(
            simulation_id=payload["simulation_id"],
            ate_config_id=payload["ate_config_id"],
            certification_id=payload["certification_id"],
            status=payload["status"],
        )

    async def handle_simulation_completed(self, event: dict[str, Any]) -> None:
        payload = event.get("payload", event)
        simulation_id = str(payload.get("simulation_id") or "")
        if not simulation_id:
            return
        stored_raw = await self.redis_client.get(self._run_key(simulation_id))
        if stored_raw is None:
            return
        stored = json.loads(stored_raw.decode("utf-8"))
        bucket = self._bucket_name
        result_key = f"ate-results/{simulation_id}/result.json"
        await self.object_storage.create_bucket_if_not_exists(bucket)
        await self.object_storage.upload_object(
            bucket,
            result_key,
            json.dumps(payload, default=str).encode("utf-8"),
            content_type="application/json",
        )
        scenarios = payload.get("scenario_results")
        if not isinstance(scenarios, list):
            scenarios = [payload]
        for index, scenario in enumerate(scenarios, start=1):
            summary = None
            if isinstance(scenario, dict):
                summary = str(
                    scenario.get("summary") or scenario.get("status") or f"scenario-{index}"
                )
            await self.repository.create_evidence_ref(
                TrustCertificationEvidenceRef(
                    certification_id=UUID(str(stored["certification_id"])),
                    evidence_type=EvidenceType.ate_results,
                    source_ref_type="simulation_result",
                    source_ref_id=simulation_id,
                    summary=summary,
                    storage_ref=result_key,
                )
            )
        stored["status"] = "completed"
        stored["result_key"] = result_key
        await self.redis_client.set(
            self._run_key(simulation_id),
            json.dumps(stored).encode("utf-8"),
            ttl=max(300, int(stored.get("timeout_seconds", 3600))),
        )

    async def scan_timed_out_runs(self) -> int:
        await self.redis_client.initialize()
        client = self.redis_client.client
        assert client is not None
        count = 0
        cursor = 0
        now = datetime.now(UTC)
        while True:
            cursor, keys = await client.scan(cursor=cursor, match="trust:ate:run:*", count=100)
            for key in keys:
                raw = await client.get(key)
                if raw is None:
                    continue
                payload = json.loads(raw)
                if payload.get("status") != "started":
                    continue
                started_at = datetime.fromisoformat(payload["started_at"])
                timeout_seconds = int(payload.get("timeout_seconds", 3600))
                if (now - started_at).total_seconds() < timeout_seconds:
                    continue
                await self.repository.create_evidence_ref(
                    TrustCertificationEvidenceRef(
                        certification_id=UUID(str(payload["certification_id"])),
                        evidence_type=EvidenceType.ate_results,
                        source_ref_type="simulation_result",
                        source_ref_id=str(payload["simulation_id"]),
                        summary="timed_out",
                        storage_ref=None,
                    )
                )
                payload["status"] = "timed_out"
                await client.set(key, json.dumps(payload))
                count += 1
            if cursor == 0:
                break
        return count

    @property
    def _bucket_name(self) -> str:
        trust_settings = getattr(self.settings, "trust", None)
        return str(getattr(trust_settings, "evidence_bucket", "trust-evidence"))

    @staticmethod
    def _run_key(simulation_id: str) -> str:
        return f"trust:ate:run:{simulation_id}"
