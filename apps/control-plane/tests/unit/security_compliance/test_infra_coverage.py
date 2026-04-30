from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.security_compliance import dependencies as sc_dependencies
from platform.security_compliance.consumers import (
    SECURITY_TOPICS,
    ComplianceEvidenceConsumer,
)
from platform.security_compliance.models import (
    ComplianceControl,
    ComplianceEvidence,
    ComplianceEvidenceMapping,
    JitApproverPolicy,
    JitCredentialGrant,
    PenetrationTest,
    PentestFinding,
    PentestSlaPolicy,
    SecretRotationSchedule,
    SoftwareBillOfMaterials,
    VulnerabilityException,
    VulnerabilityScanResult,
)
from platform.security_compliance.providers.rotatable_secret_provider import (
    RotatableSecretProvider,
)
from platform.security_compliance.repository import SecurityComplianceRepository
from platform.security_compliance.workers.overlap_expirer import (
    build_overlap_expirer,
    run_overlap_expiry,
)
from platform.security_compliance.workers.pentest_overdue_scanner import (
    build_pentest_overdue_scanner,
    run_pentest_overdue_scan,
)
from platform.security_compliance.workers.rotation_scheduler import (
    build_rotation_scheduler,
    run_due_rotations,
)
from types import ModuleType, SimpleNamespace
from typing import Any, ClassVar
from uuid import UUID, uuid4

import pytest


class RedisStub:
    def __init__(self, cached: dict[str, Any] | None = None) -> None:
        self.cached = cached or {}
        self.writes: list[tuple[str, str, dict[str, Any], int]] = []

    async def cache_get(self, namespace: str, key: str) -> dict[str, Any] | None:
        assert namespace == "rotation-state"
        return self.cached.get(key)

    async def cache_set(
        self,
        namespace: str,
        key: str,
        value: dict[str, Any],
        *,
        ttl_seconds: int,
    ) -> None:
        self.writes.append((namespace, key, value, ttl_seconds))


class VaultStub:
    def __init__(
        self,
        values: dict[str, str] | None = None,
        versions: dict[str, dict[int, str]] | None = None,
    ) -> None:
        self.values = values or {}
        self.versions = versions or {}

    async def get(self, path: str, key: str = "value") -> str:
        del key
        if path not in self.values:
            raise RuntimeError("missing secret")
        return self.values[path]

    async def list_versions(self, path: str) -> list[int]:
        return sorted(self.versions.get(path, {}))

    async def get_version(self, path: str, version: int) -> str:
        try:
            return self.versions[path][version]
        except KeyError as exc:
            raise RuntimeError("missing secret version") from exc


class ScalarSequenceStub:
    def __init__(self, items: list[Any]) -> None:
        self._items = items

    def all(self) -> list[Any]:
        return list(self._items)


class ExecuteResultStub:
    def __init__(
        self,
        *,
        scalar: Any | None = None,
        items: list[Any] | None = None,
        rowcount: int = 0,
    ) -> None:
        self._scalar = scalar
        self._items = items or []
        self.rowcount = rowcount

    def scalar_one_or_none(self) -> Any | None:
        return self._scalar

    def scalars(self) -> ScalarSequenceStub:
        return ScalarSequenceStub(self._items)


class SessionStub:
    def __init__(self, execute_results: list[ExecuteResultStub]) -> None:
        self.execute_results = execute_results
        self.get_results: dict[tuple[type[Any], UUID], Any] = {}
        self.added: list[Any] = []
        self.flush_calls = 0

    def add(self, item: Any) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        self.flush_calls += 1

    async def execute(self, statement: Any) -> ExecuteResultStub:
        del statement
        return self.execute_results.pop(0)

    async def get(self, model: type[Any], identifier: UUID) -> Any | None:
        return self.get_results.get((model, identifier))


class FakeScheduler:
    def __init__(self, timezone: str) -> None:
        self.timezone = timezone
        self.jobs: list[dict[str, Any]] = []

    def add_job(self, func: Any, trigger: str, **kwargs: Any) -> None:
        self.jobs.append({"func": func, "trigger": trigger, **kwargs})


class DependencyRepositoryMarker:
    def __init__(self, session: object) -> None:
        self.session = session


class DependencySecretProviderMarker:
    def __init__(
        self,
        settings: PlatformSettings,
        redis_client: object | None,
        secret_provider: object | None = None,
    ) -> None:
        self.settings = settings
        self.redis_client = redis_client
        self.secret_provider = secret_provider


def _install_fake_scheduler(monkeypatch: pytest.MonkeyPatch) -> None:
    apscheduler = ModuleType("apscheduler")
    schedulers = ModuleType("apscheduler.schedulers")
    asyncio_mod = ModuleType("apscheduler.schedulers.asyncio")
    asyncio_mod.AsyncIOScheduler = FakeScheduler  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "apscheduler", apscheduler)
    monkeypatch.setitem(sys.modules, "apscheduler.schedulers", schedulers)
    monkeypatch.setitem(sys.modules, "apscheduler.schedulers.asyncio", asyncio_mod)


def _with_id(item: Any) -> Any:
    item.id = uuid4()
    return item


@pytest.mark.asyncio
async def test_security_compliance_dependency_factories_wire_app_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = PlatformSettings(profile="test")
    kafka = object()
    redis = object()
    object_storage = object()
    audit_chain = object()
    session = object()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=settings,
                clients={"kafka": kafka, "redis": redis, "object_storage": object_storage},
            )
        )
    )

    monkeypatch.setattr(sc_dependencies, "SecurityComplianceRepository", DependencyRepositoryMarker)
    monkeypatch.setattr(sc_dependencies, "RotatableSecretProvider", DependencySecretProviderMarker)
    monkeypatch.setattr(
        sc_dependencies,
        "build_audit_chain_service",
        lambda built_session, built_settings, built_producer: (
            audit_chain,
            built_session,
            built_settings,
            built_producer,
        ),
    )

    assert sc_dependencies._settings(request) is settings  # type: ignore[arg-type]
    assert sc_dependencies._producer(request) is kafka  # type: ignore[arg-type]
    assert sc_dependencies._redis(request) is redis  # type: ignore[arg-type]

    sbom = await sc_dependencies.get_sbom_service(request, session)  # type: ignore[arg-type]
    vuln = await sc_dependencies.get_vuln_scan_service(request, session)  # type: ignore[arg-type]
    rotation = await sc_dependencies.get_rotation_service(request, session)  # type: ignore[arg-type]
    jit = await sc_dependencies.get_jit_service(request, session)  # type: ignore[arg-type]
    pentest = await sc_dependencies.get_pentest_service(request, session)  # type: ignore[arg-type]
    compliance = await sc_dependencies.get_compliance_service(request, session)  # type: ignore[arg-type]

    assert sbom.repository.session is session
    assert sbom.producer is kafka
    assert sbom.audit_chain[0] is audit_chain  # type: ignore[index]
    assert vuln.repository.session is session
    assert vuln.producer is kafka
    assert rotation.provider.settings is settings
    assert rotation.provider.redis_client is redis
    assert rotation.audit_chain[0] is audit_chain  # type: ignore[index]
    assert jit.settings is settings
    assert jit.redis_client is redis
    assert pentest.repository.session is session
    assert compliance.settings is settings
    assert compliance.object_storage is object_storage
    assert compliance.audit_chain[0] is audit_chain  # type: ignore[index]


@pytest.mark.asyncio
async def test_rotatable_secret_provider_reads_cache_provider_and_writes_state() -> None:
    redis = RedisStub({"db-password": {"current": "cached-current", "previous": "cached-old"}})
    provider = RotatableSecretProvider(
        PlatformSettings(profile="test"),
        redis_client=redis,  # type: ignore[arg-type]
        secret_provider=VaultStub(),
    )

    assert await provider.get_current("db-password") == "cached-current"
    assert await provider.get_previous("db-password") == "cached-old"
    assert await provider.validate_either("db-password", "cached-current") is True
    assert await provider.validate_either("db-password", "cached-old") is True

    await provider.cache_rotation_state("db-password", {"current": "next"}, ttl_seconds=7)
    assert redis.writes == [("rotation-state", "db-password", {"current": "next"}, 7)]
    await RotatableSecretProvider(
        PlatformSettings(profile="dev"),
        secret_provider=VaultStub(),
    ).cache_rotation_state("api-key", {"current": "next"})

    secret_path = "secret/data/musematic/dev/audit-chain/api-key"
    env_provider = RotatableSecretProvider(
        PlatformSettings(profile="dev"),
        secret_provider=VaultStub(
            values={secret_path: "provider-current"},
            versions={secret_path: {1: "provider-old", 2: "provider-current"}},
        ),
    )
    assert await env_provider.get_current("api-key") == "provider-current"
    assert await env_provider.get_previous("api-key") == "provider-old"

    with pytest.raises(RuntimeError):
        await RotatableSecretProvider(
            PlatformSettings(profile="dev"),
            secret_provider=VaultStub(),
        ).get_current("missing")
    with pytest.raises(RuntimeError):
        await RotatableSecretProvider(
            PlatformSettings(profile="dev"),
            secret_provider=VaultStub(
                values={"secret/data/musematic/dev/audit-chain/none-secret": ""}
            ),
        ).get_current("none-secret")


@pytest.mark.asyncio
async def test_security_compliance_repository_methods_delegate_to_session() -> None:
    now = datetime.now(UTC)
    user_id = uuid4()
    control = _with_id(
        ComplianceControl(
            framework="soc2",
            control_id="CC1.1",
            description="Control description",
            evidence_requirements=["security.scan.completed"],
        )
    )
    evidence = _with_id(
        ComplianceEvidence(
            control_id=control.id,
            evidence_type="manual",
            evidence_ref="s3://bucket/key",
            collected_at=now,
        )
    )
    mapping = _with_id(
        ComplianceEvidenceMapping(
            evidence_type="security.scan.completed",
            control_id=control.id,
        )
    )
    rotation = _with_id(
        SecretRotationSchedule(
            secret_name="jwt",
            secret_type="jwt",
            rotation_interval_days=90,
            overlap_window_hours=24,
            vault_path="secret/jwt",
            next_rotation_at=now,
            rotation_state="idle",
        )
    )
    grant = _with_id(
        JitCredentialGrant(
            user_id=user_id,
            operation="deploy:prod",
            purpose="Investigate incident SEC-1234",
            usage_audit=[],
        )
    )
    policy = _with_id(
        JitApproverPolicy(
            operation_pattern="deploy:*",
            required_roles=["platform_admin"],
            min_approvers=1,
            max_expiry_minutes=60,
        )
    )
    today = now.date()
    pentest = _with_id(PenetrationTest(scheduled_for=today, created_at=now))
    finding = _with_id(
        PentestFinding(
            pentest_id=pentest.id,
            severity="critical",
            title="Finding",
            remediation_status="open",
            remediation_due_date=today,
        )
    )
    sla = _with_id(PentestSlaPolicy(severity="critical", max_days=7, ceiling_days=14))
    sbom = _with_id(
        SoftwareBillOfMaterials(
            release_version="1.0.0",
            format="spdx",
            content="{}",
            content_sha256="a" * 64,
        )
    )
    scan = _with_id(
        VulnerabilityScanResult(
            scanner="trivy",
            release_version="1.0.0",
            findings=[],
            max_severity=None,
            gating_result="passed",
        )
    )
    exception = _with_id(
        VulnerabilityException(
            scanner="trivy",
            vulnerability_id="CVE-1",
            component_pattern="openssl*",
            justification="Temporary exception SEC-1234",
            approved_by=user_id,
            expires_at=now + timedelta(days=1),
        )
    )
    session = SessionStub(
        [
            ExecuteResultStub(scalar=sbom),
            ExecuteResultStub(items=[scan]),
            ExecuteResultStub(items=[exception]),
            ExecuteResultStub(items=[exception]),
            ExecuteResultStub(items=[rotation]),
            ExecuteResultStub(items=[rotation]),
            ExecuteResultStub(items=[rotation]),
            ExecuteResultStub(items=[grant]),
            ExecuteResultStub(items=[grant]),
            ExecuteResultStub(items=[policy]),
            ExecuteResultStub(items=[pentest]),
            ExecuteResultStub(items=[finding]),
            ExecuteResultStub(scalar=sla),
            ExecuteResultStub(items=[finding]),
            ExecuteResultStub(items=[control]),
            ExecuteResultStub(items=[control]),
            ExecuteResultStub(items=[mapping]),
            ExecuteResultStub(items=[evidence]),
            ExecuteResultStub(items=[evidence]),
            ExecuteResultStub(items=[evidence]),
            ExecuteResultStub(items=[evidence]),
        ]
    )
    session.get_results.update(
        {
            (SecretRotationSchedule, rotation.id): rotation,
            (JitCredentialGrant, grant.id): grant,
            (PenetrationTest, pentest.id): pentest,
            (PentestFinding, finding.id): finding,
            (ComplianceControl, control.id): control,
        }
    )
    repo = SecurityComplianceRepository(session)  # type: ignore[arg-type]

    added = await repo.add(sbom)
    assert added is sbom
    assert await repo.get_sbom("1.0.0", "spdx") is sbom
    assert await repo.list_scans("1.0.0") == [scan]
    assert await repo.list_active_exceptions(scanner="trivy") == [exception]
    assert await repo.list_active_exceptions() == [exception]
    assert await repo.list_rotations() == [rotation]
    assert await repo.get_rotation(rotation.id) is rotation
    assert await repo.list_due_rotations(now) == [rotation]
    assert await repo.list_expired_overlaps(now) == [rotation]
    assert await repo.get_jit_grant(grant.id) is grant
    assert await repo.list_jit_grants(user_id) == [grant]
    assert await repo.list_jit_grants() == [grant]
    assert await repo.list_jit_policies() == [policy]
    assert await repo.get_pentest(pentest.id) is pentest
    assert await repo.list_pentests() == [pentest]
    assert await repo.get_finding(finding.id) is finding
    assert await repo.list_findings(pentest.id) == [finding]
    assert await repo.get_sla_policy("critical") is sla
    assert await repo.list_overdue_findings(today) == [finding]
    assert await repo.list_controls("soc2") == [control]
    assert await repo.list_controls() == [control]
    assert await repo.get_control(control.id) is control
    assert await repo.list_mappings_by_evidence_type("security.scan.completed") == [mapping]
    assert await repo.list_evidence(control.id) == [evidence]
    assert await repo.list_evidence() == [evidence]
    assert await repo.list_evidence_for_controls([]) == []
    assert await repo.list_evidence_for_controls([control.id]) == [evidence]
    assert await repo.list_evidence_window([], window_start=now, window_end=now) == []
    assert await repo.list_evidence_window([control.id], window_start=now, window_end=now) == [
        evidence
    ]
    assert session.flush_calls == 1


@pytest.mark.asyncio
async def test_security_compliance_workers_and_scheduler_builders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_scheduler(monkeypatch)
    rotation_service = SimpleNamespace(
        trigger_due=lambda: _async_value([1, 2]),
        expire_overlaps=lambda: _async_value([1]),
    )
    finding = SimpleNamespace(id=uuid4())
    pentest_service = SimpleNamespace(
        emitted=[],
        list_overdue=lambda: _async_value([finding]),
    )

    async def _emit_finding(item: Any, *, overdue: bool = False) -> None:
        pentest_service.emitted.append((item, overdue))

    pentest_service._emit_finding = _emit_finding

    assert await run_due_rotations(rotation_service) == 2  # type: ignore[arg-type]
    assert await run_overlap_expiry(rotation_service) == 1  # type: ignore[arg-type]
    assert await run_pentest_overdue_scan(pentest_service) == 1  # type: ignore[arg-type]
    assert pentest_service.emitted == [(finding, True)]

    async def rotation_factory() -> Any:
        return rotation_service

    async def pentest_factory() -> Any:
        return pentest_service

    schedulers = [
        build_rotation_scheduler(rotation_factory, interval_seconds=60),
        build_overlap_expirer(rotation_factory),
        build_pentest_overdue_scanner(pentest_factory),
    ]
    assert [scheduler.jobs[0]["id"] for scheduler in schedulers] == [
        "security-compliance-rotation-scheduler",
        "security-compliance-overlap-expirer",
        "security-compliance-pentest-overdue",
    ]

    for scheduler in schedulers:
        await scheduler.jobs[0]["func"]()


async def _async_value(value: Any) -> Any:
    return value


@pytest.mark.asyncio
async def test_compliance_evidence_consumer_registers_topics_and_handles_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = PlatformSettings(kafka={"consumer_group": "tests"})
    consumer = ComplianceEvidenceConsumer(settings, object_storage=object())
    manager = SimpleNamespace(subscriptions=[])

    def _subscribe(topic: str, group_id: str, handler: Any) -> None:
        manager.subscriptions.append((topic, group_id, handler))

    manager.subscribe = _subscribe
    consumer.register(manager)
    assert [item[0] for item in manager.subscriptions] == list(SECURITY_TOPICS)

    session = SimpleNamespace(commits=0, rollbacks=0)

    async def _commit() -> None:
        session.commits += 1

    async def _rollback() -> None:
        session.rollbacks += 1

    session.commit = _commit
    session.rollback = _rollback

    class SessionContext:
        async def __aenter__(self) -> Any:
            return session

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            return None

    class ServiceStub:
        calls: ClassVar[list[dict[str, Any]]] = []

        def __init__(self, repository: Any, settings: Any, *, object_storage: Any) -> None:
            del repository, settings, object_storage

        async def on_security_event(self, **kwargs: Any) -> None:
            self.calls.append(kwargs)
            if kwargs["payload"].get("fail"):
                raise RuntimeError("boom")

    monkeypatch.setattr(
        "platform.security_compliance.consumers.database.AsyncSessionLocal",
        lambda: SessionContext(),
    )
    monkeypatch.setattr("platform.security_compliance.consumers.ComplianceService", ServiceStub)

    envelope = SimpleNamespace(
        event_type="security.scan.completed",
        source="security",
        payload={"scan_id": "scan-1"},
        correlation_context=CorrelationContext(correlation_id=uuid4()),
    )
    await consumer.handle_event(envelope)  # type: ignore[arg-type]
    assert session.commits == 1
    assert ServiceStub.calls[-1]["entity_id"] == "scan-1"

    envelope.payload = {"fail": True}
    await consumer.handle_event(envelope)  # type: ignore[arg-type]
    assert session.rollbacks == 1
