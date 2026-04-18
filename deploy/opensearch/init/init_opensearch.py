import asyncio
import os
from dataclasses import dataclass
from importlib import import_module
from typing import Any

SYNONYM_RULES = [
    "summarizer, text summary agent, summarization",
    "translator, language translation, translation agent",
    "classifier, categorizer, classification agent",
]


@dataclass(frozen=True, slots=True)
class SnapshotRepositorySettings:
    name: str = "opensearch-backups"
    type: str = "s3"
    bucket: str = "backups"
    base_path: str = "backups/opensearch"
    endpoint: str = "http://musematic-minio:9000"
    region: str | None = "us-east-1"
    location: str | None = None


def build_snapshot_repository_settings() -> SnapshotRepositorySettings:
    return SnapshotRepositorySettings(
        name=os.environ.get("OPENSEARCH_SNAPSHOT_REPOSITORY", "opensearch-backups"),
        type=os.environ.get("OPENSEARCH_SNAPSHOT_TYPE", "s3"),
        bucket=os.environ.get("OPENSEARCH_SNAPSHOT_BUCKET", "backups"),
        base_path=os.environ.get("OPENSEARCH_SNAPSHOT_BASE_PATH", "backups/opensearch"),
        endpoint=os.environ.get("OPENSEARCH_SNAPSHOT_ENDPOINT", "http://musematic-minio:9000"),
        region=os.environ.get("OPENSEARCH_SNAPSHOT_REGION", "us-east-1"),
        location=os.environ.get("OPENSEARCH_SNAPSHOT_LOCATION"),
    )


def _async_opensearch_client_class() -> Any:
    opensearch_module = import_module("opensearchpy")
    client_cls = getattr(opensearch_module, "AsyncOpenSearch", None)
    if client_cls is not None:
        return client_cls
    return import_module("opensearchpy._async.client").AsyncOpenSearch


def _exception_status(exc: Exception) -> int | None:
    status = getattr(exc, "status_code", None)
    if status is not None:
        try:
            return int(status)
        except (TypeError, ValueError):
            return None
    status = getattr(exc, "status", None)
    if status is not None:
        try:
            return int(status)
        except (TypeError, ValueError):
            return None
    return None


async def create_ism_policies(client: Any) -> None:
    async def put_policy(policy_id: str, body: dict[str, Any]) -> None:
        try:
            await client.transport.perform_request(
                method="PUT",
                url=f"/_plugins/_ism/policies/{policy_id}",
                body=body,
            )
        except Exception as exc:
            if _exception_status(exc) == 409:
                return
            raise

    audit_policy = {
        "policy": {
            "description": "Audit events: rollover at 50GB or 30 days, delete after 90 days",
            "default_state": "hot",
            "states": [
                {
                    "name": "hot",
                    "actions": [{"rollover": {"min_size": "50gb", "min_index_age": "30d"}}],
                    "transitions": [{"state_name": "delete", "conditions": {"min_index_age": "90d"}}],
                },
                {
                    "name": "delete",
                    "actions": [{"delete": {}}],
                    "transitions": [],
                },
            ],
            "ism_template": [{"index_patterns": ["audit-events-*"], "priority": 100}],
        }
    }
    connector_policy = {
        "policy": {
            "description": "Connector payloads: delete after 30 days",
            "default_state": "hot",
            "states": [
                {
                    "name": "hot",
                    "actions": [],
                    "transitions": [{"state_name": "delete", "conditions": {"min_index_age": "30d"}}],
                },
                {
                    "name": "delete",
                    "actions": [{"delete": {}}],
                    "transitions": [],
                },
            ],
            "ism_template": [{"index_patterns": ["connector-payloads-*"], "priority": 100}],
        }
    }

    await put_policy("audit-events-policy", audit_policy)
    await put_policy("connector-payloads-policy", connector_policy)


async def create_index_templates(client: Any) -> None:
    marketplace_template = {
        "index_patterns": ["marketplace-agents-*"],
        "template": {
            "settings": {
                "number_of_shards": 2,
                "number_of_replicas": 1,
                "analysis": {
                    "filter": {
                        "synonym_filter": {
                            "type": "synonym",
                            "synonyms_path": "synonyms/agent-synonyms.txt",
                            "updateable": True,
                        },
                        "icu_folding": {"type": "icu_folding"},
                    },
                    "analyzer": {
                        "agent_index_analyzer": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": ["lowercase", "icu_folding"],
                        },
                        "agent_analyzer": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": ["lowercase", "icu_folding", "synonym_filter"],
                        }
                    },
                },
            },
            "mappings": {
                "properties": {
                    "agent_id": {"type": "keyword"},
                    "name": {
                        "type": "text",
                        "analyzer": "agent_index_analyzer",
                        "search_analyzer": "agent_analyzer",
                        "fields": {"keyword": {"type": "keyword"}},
                    },
                    "purpose": {
                        "type": "text",
                        "analyzer": "agent_index_analyzer",
                        "search_analyzer": "agent_analyzer",
                    },
                    "description": {
                        "type": "text",
                        "analyzer": "agent_index_analyzer",
                        "search_analyzer": "agent_analyzer",
                    },
                    "tags": {"type": "keyword"},
                    "capabilities": {"type": "keyword"},
                    "maturity_level": {"type": "integer"},
                    "trust_score": {"type": "float"},
                    "workspace_id": {"type": "keyword"},
                    "lifecycle_state": {"type": "keyword"},
                    "certification_status": {"type": "keyword"},
                    "publisher_id": {"type": "keyword"},
                    "fqn": {"type": "keyword"},
                    "indexed_at": {"type": "date"},
                    "updated_at": {"type": "date"},
                }
            },
        },
    }
    audit_template = {
        "index_patterns": ["audit-events-*"],
        "template": {
            "settings": {
                "number_of_shards": 2,
                "number_of_replicas": 1,
                "plugins.index_state_management.policy_id": "audit-events-policy",
            },
            "mappings": {
                "properties": {
                    "event_id": {"type": "keyword"},
                    "event_type": {"type": "keyword"},
                    "actor_id": {"type": "keyword"},
                    "actor_type": {"type": "keyword"},
                    "timestamp": {"type": "date"},
                    "workspace_id": {"type": "keyword"},
                    "goal_id": {"type": "keyword"},
                    "resource_type": {"type": "keyword"},
                    "action": {"type": "keyword"},
                    "details": {"type": "text", "analyzer": "standard"},
                    "indexed_at": {"type": "date"},
                }
            },
        },
    }
    connector_template = {
        "index_patterns": ["connector-payloads-*"],
        "template": {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 1,
                "plugins.index_state_management.policy_id": "connector-payloads-policy",
            },
            "mappings": {
                "properties": {
                    "payload_id": {"type": "keyword"},
                    "connector_type": {"type": "keyword"},
                    "workspace_id": {"type": "keyword"},
                    "goal_id": {"type": "keyword"},
                    "timestamp": {"type": "date"},
                    "payload_text": {"type": "text", "analyzer": "standard"},
                    "direction": {"type": "keyword"},
                    "indexed_at": {"type": "date"},
                }
            },
        },
    }

    await client.indices.put_index_template(name="marketplace-agents", body=marketplace_template)
    await client.indices.put_index_template(name="audit-events", body=audit_template)
    await client.indices.put_index_template(name="connector-payloads", body=connector_template)

    await _ensure_index(
        client,
        "marketplace-agents-000001",
        {"marketplace-agents": {"is_write_index": True}},
    )
    await _ensure_index(
        client,
        "audit-events-000001",
        {"audit-events": {"is_write_index": True}},
    )
    await _ensure_index(
        client,
        "connector-payloads-000001",
        {"connector-payloads": {"is_write_index": True}},
    )


async def setup_snapshot_management(
    client: Any,
    repository_settings: SnapshotRepositorySettings | None = None,
) -> None:
    repository = repository_settings or build_snapshot_repository_settings()
    repository_body: dict[str, Any]
    if repository.type == "fs":
        repository_body = {
            "type": "fs",
            "settings": {
                "location": repository.location or "/var/backups/opensearch",
                "compress": True,
            },
        }
    else:
        repository_body = {
            "type": "s3",
            "settings": {
                "bucket": repository.bucket,
                "base_path": repository.base_path,
                "endpoint": repository.endpoint,
                "region": repository.region,
                "protocol": "http" if repository.endpoint.startswith("http://") else "https",
                "path_style_access": True,
            },
        }

    await client.snapshot.create_repository(repository=repository.name, body=repository_body)

    policy = {
        "policy": {
            "description": "Daily snapshot at 05:00 UTC",
            "creation": {
                "schedule": {"cron": {"expression": "0 5 * * *", "timezone": "UTC"}},
                "time_limit": "1h",
            },
            "deletion": {
                "schedule": {"cron": {"expression": "0 6 * * *", "timezone": "UTC"}},
                "time_limit": "30m",
                "condition": {"max_count": 30, "max_age": "30d"},
            },
            "snapshot_config": {
                "repository": repository.name,
                "indices": "*",
                "ignore_unavailable": True,
                "include_global_state": False,
            },
        }
    }
    try:
        await client.transport.perform_request(
            method="GET",
            url="/_plugins/_sm/policies/daily-snapshot",
        )
    except Exception as exc:
        if _exception_status(exc) != 404:
            raise
    else:
        return

    await client.transport.perform_request(
        method="POST",
        url="/_plugins/_sm/policies/daily-snapshot",
        body=policy,
    )


async def initialize_opensearch(client: Any | None = None) -> None:
    owned_client = False
    async_client = client
    if async_client is None:
        client_cls = _async_opensearch_client_class()
        hosts = [host.strip() for host in os.environ.get("OPENSEARCH_HOSTS", "http://localhost:9200").split(",")]
        username = os.environ.get("OPENSEARCH_USERNAME", "")
        password = os.environ.get("OPENSEARCH_PASSWORD", "")
        async_client = client_cls(
            hosts=hosts,
            http_auth=(username, password) if username and password else None,
            use_ssl=os.environ.get("OPENSEARCH_USE_SSL", "false").lower() == "true",
            verify_certs=os.environ.get("OPENSEARCH_VERIFY_CERTS", "false").lower() == "true",
            timeout=int(os.environ.get("OPENSEARCH_TIMEOUT", "30")),
            ssl_show_warn=False,
        )
        owned_client = True

    try:
        await create_ism_policies(async_client)
        await create_index_templates(async_client)
        await setup_snapshot_management(async_client)
    finally:
        if owned_client:
            close = getattr(async_client, "close", None)
            if close is not None:
                result = close()
                if hasattr(result, "__await__"):
                    await result


async def _ensure_index(client: Any, index_name: str, aliases: dict[str, Any]) -> None:
    exists = await client.indices.exists(index=index_name)
    if exists:
        return
    await client.indices.create(index=index_name, body={"aliases": aliases})


def main() -> None:
    asyncio.run(initialize_opensearch())


if __name__ == "__main__":
    main()
