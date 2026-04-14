from __future__ import annotations

from datetime import UTC, datetime
from platform.connectors.models import ConnectorCredentialRef, ConnectorInstanceStatus, DeadLetterResolution, DeliveryStatus
from platform.connectors.repository import ConnectorsRepository
from uuid import uuid4

from tests.connectors_support import (
    build_connector_instance,
    build_dead_letter,
    build_delivery,
    build_route,
)


class ScalarsStub:
    def __init__(self, items) -> None:
        self._items = list(items)

    def all(self):
        return list(self._items)


class ResultStub:
    def __init__(self, *, one=None, items=None) -> None:
        self._one = one
        self._items = [] if items is None else items

    def scalar_one_or_none(self):
        return self._one

    def scalars(self):
        return ScalarsStub(self._items)


class SessionStub:
    def __init__(self, *, execute_results: list[ResultStub], scalar_results: list[int]) -> None:
        self.execute_results = list(execute_results)
        self.scalar_results = list(scalar_results)
        self.added: list[object] = []
        self.flushed = 0
        self.executed: list[object] = []

    async def execute(self, statement):
        self.executed.append(statement)
        if self.execute_results:
            return self.execute_results.pop(0)
        return ResultStub()

    async def scalar(self, statement):
        self.executed.append(statement)
        return self.scalar_results.pop(0)

    def add(self, item) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        self.flushed += 1


async def test_connectors_repository_covers_crud_paths() -> None:
    workspace_id = uuid4()
    connector_type = build_connector_instance(workspace_id=workspace_id).connector_type
    instance = build_connector_instance(workspace_id=workspace_id, connector_type=connector_type)
    route = build_route(workspace_id=workspace_id, connector_instance_id=instance.id)
    delivery = build_delivery(workspace_id=workspace_id, connector_instance_id=instance.id)
    dead_letter = build_dead_letter(
        workspace_id=workspace_id,
        connector_instance_id=instance.id,
        delivery=delivery,
    )
    refs = [
        ConnectorCredentialRef(
            connector_instance_id=instance.id,
            workspace_id=workspace_id,
            credential_key="bot_token",
            vault_path="vault/bot_token",
        )
    ]

    session = SessionStub(
        execute_results=[
            ResultStub(items=[connector_type]),
            ResultStub(one=connector_type),
            ResultStub(one=instance),
            ResultStub(one=instance),
            ResultStub(items=[instance]),
            ResultStub(),  # delete credential refs
            ResultStub(items=refs),
            ResultStub(one=route),
            ResultStub(items=[route]),
            ResultStub(items=[route]),
            ResultStub(one=delivery),
            ResultStub(items=[delivery]),
            ResultStub(items=[delivery]),
            ResultStub(),  # increment metrics update
            ResultStub(items=[dead_letter]),
            ResultStub(one=dead_letter),
            ResultStub(items=[instance]),
        ],
        scalar_results=[1, 1, 1, 1],
    )
    repository = ConnectorsRepository(session)  # type: ignore[arg-type]

    assert await repository.list_connector_types() == [connector_type]
    assert await repository.get_connector_type(connector_type.slug) is connector_type

    created = await repository.create_connector_instance(
        workspace_id=workspace_id,
        connector_type_id=connector_type.id,
        name="Support",
        config={"enabled": True},
        status=ConnectorInstanceStatus.enabled,
    )
    assert created.name == "Support"
    assert created.config_json == {"enabled": True}

    assert await repository.get_connector_instance(instance.id, workspace_id) is instance
    assert await repository.get_connector_instance_public(instance.id) is instance
    listed_instances, total_instances = await repository.list_connector_instances(workspace_id)
    assert listed_instances == [instance]
    assert total_instances == 1

    updated = await repository.update_connector_instance(
        instance,
        name="Updated",
        config={"mode": "test"},
        status=ConnectorInstanceStatus.disabled,
        health_status=instance.health_status,
        health_check_error="bad",
        last_health_check_at=datetime.now(UTC),
    )
    assert updated.name == "Updated"
    assert updated.config_json == {"mode": "test"}
    assert updated.status is ConnectorInstanceStatus.disabled
    deleted = await repository.soft_delete_connector_instance(instance)
    assert deleted.deleted_at is not None

    upserted_refs = await repository.upsert_credential_refs(
        instance.id,
        workspace_id,
        {"signing_secret": "vault/signing_secret", "bot_token": "vault/bot_token"},
    )
    assert [ref.credential_key for ref in upserted_refs] == ["bot_token", "signing_secret"]
    listed_refs = await repository.list_credential_refs(instance.id, workspace_id)
    assert listed_refs == refs

    created_route = await repository.create_route(
        workspace_id=workspace_id,
        connector_instance_id=instance.id,
        name="Support",
        channel_pattern="#support*",
        sender_pattern="U*",
        conditions={"team": "ops"},
        target_agent_fqn="ops:triage",
        target_workflow_id=None,
        priority=10,
        is_enabled=True,
    )
    assert created_route.name == "Support"
    assert await repository.get_route(route.id, workspace_id) is route
    listed_routes, total_routes = await repository.list_routes(workspace_id, instance.id)
    assert listed_routes == [route]
    assert total_routes == 1
    assert await repository.get_routes_for_instance(instance.id, workspace_id) == [route]
    await repository.update_route(
        route,
        name="Updated route",
        channel_pattern="#ops*",
        sender_pattern="bot*",
        conditions={"severity": "high"},
        target_agent_fqn=None,
        target_workflow_id=uuid4(),
        priority=50,
        is_enabled=False,
    )
    assert route.name == "Updated route"
    assert route.channel_pattern == "#ops*"
    assert route.is_enabled is False
    await repository.delete_route(route)
    assert route.deleted_at is not None

    created_delivery = await repository.create_outbound_delivery(
        workspace_id=workspace_id,
        connector_instance_id=instance.id,
        destination="C123",
        content={"content_text": "hello"},
        priority=1,
        max_attempts=3,
        source_interaction_id=None,
        source_execution_id=None,
    )
    assert created_delivery.destination == "C123"
    assert await repository.get_outbound_delivery(delivery.id, workspace_id) is delivery
    listed_deliveries, total_deliveries = await repository.list_outbound_deliveries(workspace_id)
    assert listed_deliveries == [delivery]
    assert total_deliveries == 1
    await repository.update_delivery_status(
        delivery,
        status=DeliveryStatus.failed,
        attempt_count=2,
        next_retry_at=datetime.now(UTC),
        delivered_at=None,
    )
    assert delivery.status is DeliveryStatus.failed
    await repository.append_error_history(delivery, {"error": "boom"})
    assert delivery.error_history == [{"error": "boom"}]
    assert await repository.get_pending_retries(limit=10) == [delivery]

    created_dead_letter = await repository.create_dead_letter_entry(
        workspace_id=workspace_id,
        outbound_delivery_id=delivery.id,
        connector_instance_id=instance.id,
        dead_lettered_at=datetime.now(UTC),
    )
    assert created_dead_letter.connector_instance_id == instance.id
    await repository.increment_connector_metrics(
        instance.id,
        sent_delta=1,
        failed_delta=1,
        retried_delta=1,
        dead_lettered_delta=1,
    )

    listed_dead_letters, total_dead_letters = await repository.list_dead_letter_entries(
        workspace_id,
        connector_instance_id=instance.id,
        resolution_status=DeadLetterResolution.pending,
    )
    assert listed_dead_letters == [dead_letter]
    assert total_dead_letters == 1
    assert await repository.get_dead_letter_entry(dead_letter.id, workspace_id) is dead_letter
    await repository.update_dead_letter_resolution(
        dead_letter,
        resolution_status=DeadLetterResolution.discarded,
        resolved_at=datetime.now(UTC),
        resolution_note="archived",
        archive_path="dead/entry.json",
    )
    assert dead_letter.resolution_status is DeadLetterResolution.discarded
    assert dead_letter.archive_path == "dead/entry.json"

    assert await repository.list_enabled_connector_instances_by_type(connector_type.slug) == [instance]
    assert len(session.added) >= 6
    assert session.flushed >= 10
