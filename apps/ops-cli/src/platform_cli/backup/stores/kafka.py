"""Kafka backup implementation."""

from __future__ import annotations

import json
from pathlib import Path
from time import monotonic
from typing import Protocol, cast

from platform_cli.backup.stores.common import build_artifact
from platform_cli.models import BackupArtifact, utc_now_iso


class _ItemsView(Protocol):
    def items(self) -> list[tuple[object, object]]: ...


def _extract_group_id(item: object) -> str | None:
    if isinstance(item, str):
        return item
    if isinstance(item, tuple) and item:
        candidate = item[0]
        if isinstance(candidate, str):
            return candidate
    candidate = getattr(item, "group_id", None)
    if isinstance(candidate, str):
        return candidate
    return None


def _offset_value(value: object) -> tuple[int, str]:
    offset_candidate = getattr(value, "offset", None)
    metadata_candidate = getattr(value, "metadata", None)
    if offset_candidate is not None:
        if isinstance(offset_candidate, int):
            metadata = metadata_candidate if isinstance(metadata_candidate, str) else ""
            return offset_candidate, metadata
        return 0, ""
    if isinstance(value, tuple) and value:
        offset_source = value[0]
        metadata = value[1] if len(value) > 1 else ""
        if isinstance(offset_source, int):
            return offset_source, metadata if isinstance(metadata, str) else str(metadata)
        return 0, metadata if isinstance(metadata, str) else str(metadata)
    if isinstance(value, int):
        return value, ""
    return 0, ""


def _serialize_offsets(offsets: object) -> list[dict[str, object]]:
    if isinstance(offsets, dict):
        items = list(offsets.items())
    elif hasattr(offsets, "items"):
        items = list((_cast_items(offsets)).items())
    else:
        items = []

    serialized: list[dict[str, object]] = []
    for partition, value in items:
        topic = getattr(partition, "topic", None)
        partition_id = getattr(partition, "partition", None)
        if not isinstance(topic, str) or not isinstance(partition_id, int):
            continue
        offset, metadata = _offset_value(value)
        serialized.append(
            {
                "topic": topic,
                "partition": partition_id,
                "offset": offset,
                "metadata": metadata,
            }
        )
    serialized.sort(
        key=lambda item: (
            str(item["topic"]),
            item["partition"] if isinstance(item["partition"], int) else 0,
        )
    )
    return serialized


def _cast_items(value: object) -> _ItemsView:
    return cast(_ItemsView, value)


class KafkaBackup:
    """Capture and restore Kafka consumer group offsets."""

    def __init__(self, bootstrap_servers: str) -> None:
        self.bootstrap_servers = bootstrap_servers

    async def backup(self, output_dir: Path) -> BackupArtifact:
        from aiokafka.admin import AIOKafkaAdminClient

        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "kafka-offsets.json"
        started = monotonic()
        admin = AIOKafkaAdminClient(bootstrap_servers=self.bootstrap_servers)
        await admin.start()
        try:
            groups = await admin.list_consumer_groups()
            consumer_groups: list[dict[str, object]] = []
            payload = {
                "schema_version": 1,
                "captured_at": utc_now_iso(),
                "bootstrap_servers": self.bootstrap_servers,
                "consumer_groups": consumer_groups,
            }
            for item in groups:
                group_id = _extract_group_id(item)
                if group_id is None:
                    continue
                offsets = await admin.list_consumer_group_offsets(group_id)
                consumer_groups.append(
                    {
                        "group_id": group_id,
                        "offsets": _serialize_offsets(offsets),
                    }
                )
            path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        finally:
            await admin.close()
        return build_artifact(
            store="kafka",
            display_name="Kafka",
            path=path,
            format_name="json",
            duration_seconds=monotonic() - started,
        )

    async def restore(self, artifact_path: Path) -> bool:
        from aiokafka import TopicPartition
        from aiokafka.admin import AIOKafkaAdminClient
        from aiokafka.structs import OffsetAndMetadata

        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        groups = payload.get("consumer_groups", [])
        if not isinstance(groups, list) or not groups:
            return True

        admin = AIOKafkaAdminClient(bootstrap_servers=self.bootstrap_servers)
        await admin.start()
        try:
            for group in groups:
                if not isinstance(group, dict):
                    continue
                group_id = group.get("group_id")
                offsets = group.get("offsets", [])
                if not isinstance(group_id, str) or not isinstance(offsets, list):
                    continue
                commit_map: dict[object, object] = {}
                for entry in offsets:
                    if not isinstance(entry, dict):
                        continue
                    topic = entry.get("topic")
                    partition = entry.get("partition")
                    offset = entry.get("offset")
                    metadata = entry.get("metadata", "")
                    if not isinstance(topic, str) or not isinstance(partition, int):
                        continue
                    if not isinstance(offset, int):
                        continue
                    commit_map[TopicPartition(topic, partition)] = OffsetAndMetadata(
                        offset,
                        metadata if isinstance(metadata, str) else str(metadata),
                    )
                if commit_map:
                    await admin.alter_consumer_group_offsets(group_id, commit_map)
        finally:
            await admin.close()
        return True
