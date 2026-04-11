from __future__ import annotations

from platform.common.clients.opensearch import AsyncOpenSearchClient
from platform.common.config import PlatformSettings
from platform.common.config import settings as default_settings
from typing import Any

TEMPLATE_NAME = "marketplace-agents"


def _template_body() -> dict[str, Any]:
    return {
        "index_patterns": ["marketplace-agents-*"],
        "template": {
            "settings": {
                "number_of_shards": 2,
                "number_of_replicas": 1,
                "analysis": {
                    "analyzer": {
                        "purpose_analyzer": {
                            "type": "standard",
                            "stopwords": "_english_",
                        }
                    }
                },
            },
            "mappings": {
                "properties": {
                    "agent_profile_id": {"type": "keyword"},
                    "fqn": {"type": "keyword"},
                    "namespace": {"type": "keyword"},
                    "local_name": {"type": "keyword"},
                    "display_name": {
                        "type": "text",
                        "fields": {"keyword": {"type": "keyword"}},
                    },
                    "purpose": {"type": "text", "analyzer": "purpose_analyzer"},
                    "approach": {"type": "text", "analyzer": "purpose_analyzer"},
                    "tags": {"type": "keyword"},
                    "role_types": {"type": "keyword"},
                    "maturity_level": {"type": "integer"},
                    "status": {"type": "keyword"},
                    "workspace_id": {"type": "keyword"},
                    "created_at": {"type": "date"},
                }
            },
        },
    }


async def create_marketplace_agents_index(
    client: AsyncOpenSearchClient | None = None,
    settings: PlatformSettings | None = None,
) -> None:
    resolved_settings = settings or default_settings
    resolved_client = client or AsyncOpenSearchClient.from_settings(resolved_settings)
    should_close = client is None
    if should_close:
        await resolved_client.connect()
    try:
        raw_client = await resolved_client._ensure_client()
        await raw_client.indices.put_index_template(name=TEMPLATE_NAME, body=_template_body())
        exists = await raw_client.indices.exists(
            index=resolved_settings.registry.search_backing_index
        )
        if not exists:
            await raw_client.indices.create(
                index=resolved_settings.registry.search_backing_index,
                body={
                    "aliases": {
                        resolved_settings.registry.search_index: {"is_write_index": True},
                    }
                },
            )
            return
        aliases = await raw_client.indices.get_alias(
            index=resolved_settings.registry.search_backing_index
        )
        backing_index = aliases.get(resolved_settings.registry.search_backing_index, {})
        if resolved_settings.registry.search_index not in backing_index.get("aliases", {}):
            await raw_client.indices.put_alias(
                index=resolved_settings.registry.search_backing_index,
                name=resolved_settings.registry.search_index,
                body={"is_write_index": True},
            )
    finally:
        if should_close:
            await resolved_client.close()
