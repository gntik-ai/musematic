from __future__ import annotations

import json
from datetime import UTC, datetime
from platform.privacy_compliance.events import PrivacyEventPublisher
from platform.privacy_compliance.exceptions import CascadePartialFailure, SeededRuleDeletionError
from platform.privacy_compliance.models import ConsentType, PrivacyConsentRecord, PrivacyDLPRule
from platform.privacy_compliance.schemas import DSRCreateRequest
from platform.privacy_compliance.services.dlp_service import DLPService
from platform.privacy_compliance.services.dsr_service import DSRService
from platform.privacy_compliance.services.salt_history import SaltHistoryProvider
from platform.privacy_compliance.services.tombstone_signer import TombstoneSigner
from platform.privacy_compliance.workers.consent_propagator import ConsentPropagator
from platform.privacy_compliance.workers.dlp_event_aggregator import DLPEventAggregator
from platform.privacy_compliance.workers.hold_window_releaser import HoldWindowReleaser
from types import SimpleNamespace
from uuid import uuid4

import pytest


class RecordingPublisher(PrivacyEventPublisher):
    def __init__(self) -> None:
        super().__init__(None)
        self.published: list[tuple[object, object, str]] = []

    async def publish(self, event_type, payload, *, key, correlation_ctx=None):
        del correlation_ctx
        self.published.append((event_type, payload, key))


class SecretProvider:
    async def get_secret(self, path: str) -> str:
        assert path == "secret/path"
        return json.dumps(
            {
                "current_salt": "73616c74",
                "salt_version": 2,
                "history": [{"salt": "old", "salt_version": 1}],
            }
        )


class AsyncSigner:
    async def sign(self, payload: bytes) -> bytes:
        return b"signed:" + payload

    async def current_key_version(self) -> str:
        return "v1"

    async def public_key_pem(self) -> bytes:
        return b"async-public-key"


class SyncSigner:
    def sign(self, payload: bytes) -> bytes:
        return b"sync:" + payload

    def current_key_version(self) -> str:
        return "sync-v1"

    def public_key_pem(self) -> str:
        return "sync-public-key"


class DictSecretProvider:
    async def read_secret(self, path: str) -> dict[str, object]:
        assert path == "dict/path"
        return {
            "current_salt": "dict-salt",
            "salt_version": 3,
            "history": ["ignored", {"salt_version": 2}],
        }


class DLPRepo:
    def __init__(self) -> None:
        self.rule = PrivacyDLPRule(
            id=uuid4(),
            name="secret",
            classification="confidential",
            pattern="secret",
            action="redact",
            enabled=True,
            seeded=False,
        )
        self.created_events = []

    async def list_dlp_rules(self, workspace_id):
        del workspace_id
        return [self.rule]

    async def create_dlp_event(self, event):
        self.created_events.append(event)
        return event

    async def create_dlp_rule(self, rule):
        return rule

    async def get_dlp_rule(self, rule_id):
        del rule_id
        return self.rule

    async def update_dlp_rule(self, rule, **fields):
        for key, value in fields.items():
            if value is not None:
                setattr(rule, key, value)
        return rule

    async def delete_dlp_rule(self, rule):
        self.deleted = rule


class ConsentRepo:
    def __init__(self, record: PrivacyConsentRecord) -> None:
        self.record = record

    async def current_consent_state(self, user_id):
        del user_id
        return dict.fromkeys(ConsentType, self.record)

    async def upsert_consent(self, **kwargs):
        del kwargs
        return self.record

    async def revoke_consent(self, **kwargs):
        del kwargs
        self.record.granted = False
        return self.record

    async def get_consent_records(self, user_id):
        del user_id
        return [self.record]


class MissingRuleRepo(DLPRepo):
    async def get_dlp_rule(self, rule_id):
        del rule_id
        return None


@pytest.mark.asyncio
async def test_salt_provider_signer_dlp_service_and_workers() -> None:
    provider = SaltHistoryProvider(secret_provider=SecretProvider(), vault_path="secret/path")
    assert await provider.get_current_version() == 2
    assert await provider.get_current_salt() == b"salt"
    assert await provider.get_salt(1) == b"old"
    dict_provider = SaltHistoryProvider(
        secret_provider=DictSecretProvider(),
        vault_path="dict/path",
    )
    assert await dict_provider.get_current_version() == 3
    assert await dict_provider.get_current_salt() == b"dict-salt"

    signer = TombstoneSigner(AsyncSigner())
    assert await signer.sign(b"payload") == b"signed:payload"
    assert await signer.current_key_version() == "v1"
    assert await signer.public_key_pem() == "async-public-key"
    sync_signer = TombstoneSigner(SyncSigner())
    assert await sync_signer.sign(b"payload") == b"sync:payload"
    assert await sync_signer.current_key_version() == "sync-v1"
    assert await sync_signer.public_key_pem() == "sync-public-key"
    fallback = TombstoneSigner()
    assert await fallback.current_key_version() == "ephemeral-local"
    assert "BEGIN PUBLIC KEY" in await fallback.public_key_pem()
    assert await fallback.sign(b"payload")

    repo = DLPRepo()
    publisher = RecordingPublisher()
    service = DLPService(repository=repo, event_publisher=publisher)  # type: ignore[arg-type]
    workspace_id = uuid4()
    execution_id = uuid4()
    scan = await service.scan_and_apply("contains secret", workspace_id)
    assert scan.output_text == "contains [REDACTED:confidential]"
    emitted = await service.emit_events(scan.events, execution_id=execution_id)
    assert emitted == repo.created_events
    assert publisher.published
    assert (await service.create_rule(
        name="custom",
        classification="pii",
        pattern="x",
        action="flag",
    )).seeded is False
    assert (await service.update_rule(repo.rule.id, enabled=False)).enabled is False
    await service.delete_rule(repo.rule.id)
    repo.rule.seeded = True
    assert SeededRuleDeletionError.status_code == 403
    with pytest.raises(SeededRuleDeletionError):
        await service.delete_rule(repo.rule.id)
    missing_rule_service = DLPService(
        repository=MissingRuleRepo(),
        event_publisher=RecordingPublisher(),
    )
    with pytest.raises(ValueError, match="DLP rule not found"):
        await missing_rule_service.update_rule(uuid4(), enabled=True)
    await missing_rule_service.delete_rule(uuid4())

    record = PrivacyConsentRecord(
        id=uuid4(),
        user_id=uuid4(),
        consent_type=ConsentType.training_use.value,
        granted=False,
        granted_at=datetime.now(UTC),
        revoked_at=datetime.now(UTC),
    )
    data_collection_record = PrivacyConsentRecord(
        id=uuid4(),
        user_id=uuid4(),
        consent_type=ConsentType.data_collection.value,
        granted=False,
        granted_at=datetime.now(UTC),
        revoked_at=datetime.now(UTC),
    )
    repository = SimpleNamespace(
        list_recent_revocations=lambda since: _async([record, data_collection_record])
    )
    redis_calls: list[tuple[str, str]] = []
    redis = SimpleNamespace(
        sadd=lambda key, value: _async(redis_calls.append((key, value)))
    )
    assert await ConsentPropagator(repository, redis).run_once() == 2
    assert redis_calls == [
        ("privacy:revoked_training_users", str(record.user_id)),
        ("privacy:data_collection_disabled_users", str(data_collection_record.user_id)),
    ]
    non_training = PrivacyConsentRecord(
        id=uuid4(),
        user_id=uuid4(),
        consent_type=ConsentType.ai_interaction.value,
        granted=False,
        granted_at=datetime.now(UTC),
        revoked_at=datetime.now(UTC),
    )
    repository = SimpleNamespace(list_recent_revocations=lambda since: _async([non_training]))
    assert await ConsentPropagator(repository, None).run_once() == 0
    assert (await DLPEventAggregator(repository, None, retention_days=1).run_once())[
        "purge_before_epoch"
    ] > 0
    releaser = HoldWindowReleaser(
        SimpleNamespace(release_due_holds=lambda: _async([1, 2]))
    )
    assert await releaser.run_once() == 2


@pytest.mark.asyncio
async def test_consent_and_residency_service_remaining_paths() -> None:
    from platform.privacy_compliance.services.consent_service import ConsentService
    from platform.privacy_compliance.services.residency_service import ResidencyService

    user_id = uuid4()
    workspace_id = uuid4()
    record = PrivacyConsentRecord(
        id=uuid4(),
        user_id=user_id,
        consent_type=ConsentType.training_use.value,
        granted=True,
        granted_at=datetime.now(UTC),
    )
    consent = ConsentService(
        repository=ConsentRepo(record),  # type: ignore[arg-type]
        event_publisher=RecordingPublisher(),
    )
    assert (await consent.get_state(user_id))[ConsentType.ai_interaction] == "granted"
    assert await consent.revoke(user_id, ConsentType.training_use.value) is record
    assert await consent.history(user_id) == [record]

    class ResidencyRepo:
        def __init__(self) -> None:
            self.config = None

        async def get_residency_config(self, workspace_id):
            del workspace_id
            return self.config

        async def upsert_residency_config(self, **kwargs):
            self.config = SimpleNamespace(id=uuid4(), **kwargs)
            return self.config

        async def delete_residency_config(self, workspace_id):
            del workspace_id
            self.config = None
            return True

    residency = ResidencyService(
        repository=ResidencyRepo(),  # type: ignore[arg-type]
        event_publisher=RecordingPublisher(),
    )
    assert await residency.get_cached(workspace_id) is None
    config = await residency.set_config(workspace_id, "eu-central-1", [], actor=user_id)
    assert await residency.get_config(workspace_id) is config
    assert await residency.get_cached(workspace_id) is config
    await residency.delete_config(workspace_id, actor=user_id)
    assert ResidencyService._cache_payload(None) == "null"
    assert "eu-central-1" in ResidencyService._cache_payload(config)


class DSRRepo:
    def __init__(self) -> None:
        self.dsr = None

    async def create_dsr(self, dsr):
        if dsr.id is None:
            dsr.id = uuid4()
        self.dsr = dsr
        return dsr

    async def list_dsrs(self, **kwargs):
        del kwargs
        return [self.dsr]

    async def get_dsr(self, dsr_id):
        del dsr_id
        return self.dsr

    async def update_dsr(self, dsr, **fields):
        for key, value in fields.items():
            setattr(dsr, key, value)
        return dsr

    async def list_due_scheduled_dsrs(self, now):
        del now
        return [self.dsr]


class Tombstone:
    id = uuid4()
    proof_hash = "proof"


class Orchestrator:
    async def run(self, dsr_id, subject_user_id):
        del dsr_id, subject_user_id
        return Tombstone()


class PartialOrchestrator:
    async def run(self, dsr_id, subject_user_id):
        del dsr_id, subject_user_id
        raise CascadePartialFailure(Tombstone(), ["store failed"])


@pytest.mark.asyncio
async def test_dsr_service_scheduled_cancel_process_retry_and_release_paths() -> None:
    repo = DSRRepo()
    service = DSRService(
        repository=repo,  # type: ignore[arg-type]
        event_publisher=RecordingPublisher(),
        orchestrator=Orchestrator(),
    )
    user_id = uuid4()
    response = await service.create_request(
        DSRCreateRequest(
            subject_user_id=user_id,
            request_type="erasure",
            hold_hours=1,
        ),
        requested_by=user_id,
    )
    assert response.status == "scheduled"
    assert await service.list_requests()
    await service.cancel(response.id, reason="duplicate")
    repo.dsr.status = "failed"
    assert (await service.retry(response.id)).status == "completed"
    repo.dsr.status = "scheduled"
    assert await service.release_due_holds()
    repo.dsr.status = "received"
    with pytest.raises(ValueError, match="only scheduled"):
        await service.cancel(response.id, reason="late")


@pytest.mark.asyncio
async def test_dsr_service_non_erasure_missing_and_partial_failure_paths() -> None:
    repo = DSRRepo()
    user_id = uuid4()
    service = DSRService(
        repository=repo,  # type: ignore[arg-type]
        event_publisher=RecordingPublisher(),
    )
    response = await service.create_request(
        DSRCreateRequest(subject_user_id=user_id, request_type="access"),
        requested_by=user_id,
    )
    assert (await service.process(response.id)).completion_proof_hash
    with pytest.raises(ValueError, match="only failed"):
        await service.retry(response.id)
    repo.dsr = None
    with pytest.raises(Exception, match="DSR request not found"):
        await service.get_request(uuid4())

    failing_repo = DSRRepo()
    failing = DSRService(
        repository=failing_repo,  # type: ignore[arg-type]
        event_publisher=RecordingPublisher(),
        orchestrator=PartialOrchestrator(),
    )
    erasure = await failing.create_request(
        DSRCreateRequest(subject_user_id=user_id, request_type="erasure"),
        requested_by=user_id,
    )
    failed = await failing.process(erasure.id)
    assert failed.status == "failed"


async def _async(value):
    return value
