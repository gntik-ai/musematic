from __future__ import annotations

from datetime import UTC, datetime
from platform.privacy_compliance.cascade_adapters.base import empty_result
from platform.privacy_compliance.cascade_adapters.clickhouse_adapter import (
    ClickHouseCascadeAdapter,
)
from platform.privacy_compliance.cascade_adapters.neo4j_adapter import Neo4jCascadeAdapter
from platform.privacy_compliance.cascade_adapters.opensearch_adapter import (
    OpenSearchCascadeAdapter,
)
from platform.privacy_compliance.cascade_adapters.postgresql_adapter import (
    USER_IDENTITY_COLUMNS,
    PostgreSQLCascadeAdapter,
)
from platform.privacy_compliance.cascade_adapters.qdrant_adapter import QdrantCascadeAdapter
from platform.privacy_compliance.cascade_adapters.s3_adapter import S3CascadeAdapter
from platform.privacy_compliance.models import (
    ConsentType,
    DSRStatus,
    PIAStatus,
    PrivacyConsentRecord,
    PrivacyDLPEvent,
    PrivacyDLPRule,
    PrivacyDSRRequest,
    PrivacyImpactAssessment,
    PrivacyResidencyConfig,
)
from platform.privacy_compliance.repository import PrivacyComplianceRepository, utcnow
from types import SimpleNamespace
from uuid import uuid4

import pytest


class ScalarResult:
    def __init__(self, items: list[object]) -> None:
        self.items = items

    def all(self) -> list[object]:
        return self.items

    def first(self) -> object | None:
        return self.items[0] if self.items else None


class QueryResult:
    def __init__(
        self,
        items: list[object] | None = None,
        *,
        scalar: object | None = None,
        rowcount: int = 1,
    ) -> None:
        self.items = items or []
        self.scalar = scalar
        self.rowcount = rowcount

    def scalars(self) -> ScalarResult:
        return ScalarResult(self.items)

    def scalar_one_or_none(self) -> object | None:
        return self.scalar

    def scalar_one(self) -> object:
        return 1 if self.scalar is None else self.scalar


class SessionStub:
    def __init__(self, results: list[QueryResult] | None = None) -> None:
        self.results = results or []
        self.added: list[object] = []
        self.deleted: list[object] = []
        self.flushed = 0
        self.executed = 0
        self.get_value: object | None = None

    def add(self, item: object) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        self.flushed += 1

    async def get(self, model: object, item_id: object) -> object | None:
        del model, item_id
        return self.get_value

    async def delete(self, item: object) -> None:
        self.deleted.append(item)

    async def execute(self, query: object, params: object | None = None) -> QueryResult:
        del query, params
        self.executed += 1
        if self.results:
            return self.results.pop(0)
        return QueryResult(rowcount=1)


@pytest.mark.asyncio
async def test_repository_crud_and_state_helpers_cover_all_entities() -> None:
    user_id = uuid4()
    workspace_id = uuid4()
    now = datetime.now(UTC)
    consent = PrivacyConsentRecord(
        id=uuid4(),
        user_id=user_id,
        consent_type=ConsentType.training_use.value,
        granted=True,
        granted_at=now,
    )
    rule = PrivacyDLPRule(
        id=uuid4(),
        name="rule",
        classification="pii",
        pattern="secret",
        action="redact",
        enabled=True,
        seeded=False,
    )
    pia = PrivacyImpactAssessment(
        id=uuid4(),
        subject_type="agent",
        subject_id=uuid4(),
        data_categories=["pii"],
        legal_basis="legitimate interest",
        status=PIAStatus.approved.value,
        submitted_by=user_id,
        approved_at=now,
    )
    config = PrivacyResidencyConfig(
        id=uuid4(),
        workspace_id=workspace_id,
        region_code="eu-central-1",
        allowed_transfer_regions=[],
    )
    session = SessionStub(
        [
            QueryResult([SimpleNamespace(id=uuid4())]),
            QueryResult([SimpleNamespace(id=uuid4())]),
            QueryResult(scalar=None),
            QueryResult(scalar=config),
            QueryResult(rowcount=1),
            QueryResult([rule]),
            QueryResult([SimpleNamespace(id=uuid4())]),
            QueryResult([pia]),
            QueryResult([pia]),
            QueryResult(scalar=None),
            QueryResult([consent]),
            QueryResult([consent]),
            QueryResult([consent]),
            QueryResult([consent]),
        ]
    )
    repo = PrivacyComplianceRepository(session)  # type: ignore[arg-type]
    dsr = PrivacyDSRRequest(
        id=uuid4(),
        subject_user_id=user_id,
        request_type="erasure",
        requested_by=user_id,
        status=DSRStatus.received.value,
        requested_at=now,
    )

    assert await repo.create_dsr(dsr) is dsr
    assert await repo.list_dsrs(subject_user_id=user_id)
    assert await repo.list_due_scheduled_dsrs(now)
    assert (await repo.upsert_residency_config(
        workspace_id=workspace_id,
        region_code="eu-central-1",
        allowed_transfer_regions=[],
    )).workspace_id == workspace_id
    assert (await repo.upsert_residency_config(
        workspace_id=workspace_id,
        region_code="eu-west-1",
        allowed_transfer_regions=["eu-central-1"],
    )).region_code == "eu-west-1"
    assert await repo.delete_residency_config(workspace_id) is True
    assert await repo.create_dlp_rule(rule) is rule
    assert await repo.list_dlp_rules(workspace_id)
    assert (await repo.update_dlp_rule(rule, enabled=False, action=None)).enabled is False
    await repo.delete_dlp_rule(rule)
    assert session.deleted == [rule]
    event = PrivacyDLPEvent(
        id=uuid4(),
        rule_id=rule.id,
        match_summary="pii:rule",
        action_taken="redact",
        created_at=now,
    )
    assert await repo.create_dlp_event(event) is event
    assert await repo.list_dlp_events(workspace_id)
    assert await repo.create_pia(pia) is pia
    assert await repo.list_pias(subject_type="agent", subject_id=pia.subject_id, status="approved")
    assert await repo.get_approved_pia("agent", pia.subject_id) is pia
    assert (await repo.upsert_consent(
        user_id=user_id,
        consent_type=ConsentType.ai_interaction.value,
        granted=True,
        workspace_id=workspace_id,
        now=now,
    )).granted is True
    assert (await repo.revoke_consent(
        user_id=user_id,
        consent_type=ConsentType.training_use.value,
        now=now,
    )).granted is False
    assert await repo.list_recent_revocations(now)
    state = await repo.current_consent_state(user_id)
    assert state[ConsentType.training_use] is consent


@pytest.mark.asyncio
async def test_repository_remaining_branches_and_getters() -> None:
    user_id = uuid4()
    workspace_id = uuid4()
    now = utcnow()
    dsr = PrivacyDSRRequest(
        id=uuid4(),
        subject_user_id=user_id,
        request_type="erasure",
        requested_by=user_id,
        status=DSRStatus.received.value,
        requested_at=now,
    )
    config = PrivacyResidencyConfig(
        id=uuid4(),
        workspace_id=workspace_id,
        region_code="eu-central-1",
        allowed_transfer_regions=[],
    )
    rule = PrivacyDLPRule(
        id=uuid4(),
        name="rule",
        classification="pii",
        pattern="secret",
        action="redact",
        enabled=True,
        seeded=False,
    )
    event = PrivacyDLPEvent(
        id=uuid4(),
        rule_id=rule.id,
        match_summary="pii:rule",
        action_taken="redact",
        created_at=now,
    )
    pia = PrivacyImpactAssessment(
        id=uuid4(),
        subject_type="agent",
        subject_id=uuid4(),
        data_categories=["pii"],
        legal_basis="legitimate interest",
        status=PIAStatus.draft.value,
        submitted_by=user_id,
    )
    consent = PrivacyConsentRecord(
        id=uuid4(),
        user_id=user_id,
        consent_type=ConsentType.ai_interaction.value,
        granted=True,
        granted_at=now,
    )
    session = SessionStub(
        [
            QueryResult([dsr]),
            QueryResult(scalar=config),
            QueryResult([rule]),
            QueryResult([event]),
            QueryResult([pia]),
            QueryResult(scalar=consent),
        ]
    )
    repo = PrivacyComplianceRepository(session)  # type: ignore[arg-type]
    session.get_value = dsr

    assert await repo.get_dsr(dsr.id) is dsr
    assert await repo.list_dsrs(request_type="erasure", status=DSRStatus.received.value) == [dsr]
    assert (await repo.update_dsr(dsr, status=DSRStatus.scheduled.value)).status == "scheduled"
    tombstone = await repo.insert_tombstone(
        subject_user_id_hash="hash",
        salt_version=1,
        entities_deleted={},
        cascade_log=[],
        proof_hash="proof",
    )
    session.get_value = tombstone
    assert await repo.get_tombstone(tombstone.id) is tombstone
    session.get_value = rule
    assert await repo.get_dlp_rule(rule.id) is rule
    session.get_value = pia
    assert await repo.get_pia(pia.id) is pia
    assert await repo.get_residency_config(workspace_id) is config
    assert await repo.list_dlp_rules() == [rule]
    assert await repo.list_dlp_events() == [event]
    assert await repo.list_pias() == [pia]
    updated = await repo.upsert_consent(
        user_id=user_id,
        consent_type=ConsentType.ai_interaction.value,
        granted=False,
        workspace_id=workspace_id,
        now=now,
    )
    assert updated.granted is False

    fallback_session = SessionStub([QueryResult([]), QueryResult(scalar=None)])
    fallback_repo = PrivacyComplianceRepository(fallback_session)  # type: ignore[arg-type]
    revoked = await fallback_repo.revoke_consent(
        user_id=user_id,
        consent_type=ConsentType.training_use.value,
        now=now,
    )
    assert revoked.granted is False


class CommandClient:
    async def execute_command(self, sql: str, params: dict[str, str]) -> None:
        self.last = (sql, params)

    async def delete(self, **kwargs: object) -> None:
        self.last = kwargs

    async def delete_by_query(self, **kwargs: object) -> dict[str, int]:
        self.last = kwargs
        return {"deleted": 3}

    async def delete_objects_matching_prefix(self, bucket: str, prefix: str) -> int:
        self.last = (bucket, prefix)
        return 2


class FailingClient(CommandClient):
    async def execute_command(self, sql: str, params: dict[str, str]) -> None:
        del sql, params
        raise RuntimeError("clickhouse down")

    async def delete(self, **kwargs: object) -> None:
        del kwargs
        raise RuntimeError("qdrant down")

    async def delete_by_query(self, **kwargs: object) -> dict[str, int]:
        del kwargs
        raise RuntimeError("opensearch down")

    async def delete_objects_matching_prefix(self, bucket: str, prefix: str) -> int:
        del bucket, prefix
        raise RuntimeError("s3 down")


@pytest.mark.asyncio
async def test_cascade_adapters_execute_success_and_error_paths() -> None:
    user_id = uuid4()
    assert empty_result("x").affected_count == 0

    clickhouse = ClickHouseCascadeAdapter(CommandClient(), ["events"])
    assert (await clickhouse.dry_run(user_id)).per_target_estimates == {"events": 0}
    assert (await clickhouse.execute(user_id)).errors == []
    assert (await ClickHouseCascadeAdapter(FailingClient(), ["events"]).execute(user_id)).errors

    qdrant = QdrantCascadeAdapter(CommandClient(), ["memories"])
    assert (await qdrant.dry_run(user_id)).estimated_count == 0
    assert (await qdrant.execute(user_id)).errors == []
    assert (await QdrantCascadeAdapter(FailingClient(), ["memories"]).execute(user_id)).errors

    s3 = S3CascadeAdapter(CommandClient(), ["bucket"])
    assert (await s3.dry_run(user_id)).per_target_estimates == {"bucket": 0}
    assert (await s3.execute(user_id)).errors == []
    assert (await S3CascadeAdapter(FailingClient(), ["bucket"]).execute(user_id)).errors

    opensearch = OpenSearchCascadeAdapter(CommandClient(), index="idx")
    assert (await opensearch.dry_run(user_id)).per_target_estimates == {"idx": 0}
    assert (await opensearch.execute(user_id)).affected_count == 3
    assert (await OpenSearchCascadeAdapter(FailingClient()).execute(user_id)).errors

    neo_session = SessionStub(
        [
            QueryResult(scalar="graph_nodes"),
            QueryResult(scalar=2),
            QueryResult(scalar="graph_edges"),
            QueryResult(rowcount=4),
            QueryResult(rowcount=2),
        ]
    )
    neo4j = Neo4jCascadeAdapter(neo_session)  # type: ignore[arg-type]
    assert (await neo4j.dry_run(user_id)).estimated_count == 2
    assert (await neo4j.execute(user_id)).affected_count == 6

    pg_results: list[QueryResult] = []
    for columns in USER_IDENTITY_COLUMNS.values():
        pg_results.append(QueryResult(items=list(columns)))
        pg_results.append(QueryResult(scalar=1))
    pg_results.append(QueryResult(rowcount=0))
    pg_results.extend(QueryResult(rowcount=1) for _ in USER_IDENTITY_COLUMNS)
    pg_session = SessionStub(pg_results)
    postgresql = PostgreSQLCascadeAdapter(pg_session)  # type: ignore[arg-type]
    assert (await postgresql.dry_run(user_id)).estimated_count == len(USER_IDENTITY_COLUMNS)
    result = await postgresql.execute(user_id)
    assert result.errors == []
    assert result.affected_count == len(USER_IDENTITY_COLUMNS)
