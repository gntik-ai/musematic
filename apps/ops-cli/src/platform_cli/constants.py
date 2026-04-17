"""Static platform component registry used across installers and diagnostics."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class ComponentCategory(StrEnum):
    """Classification of a deployable platform unit."""

    DATA_STORE = "data_store"
    SATELLITE_SERVICE = "satellite_service"
    CONTROL_PLANE = "control_plane"


class PlatformComponent(BaseModel):
    """A single deployable platform unit."""

    name: str
    display_name: str
    category: ComponentCategory
    helm_chart: str | None
    namespace: str
    depends_on: list[str]
    health_check_type: str
    health_check_target: str
    has_migration: bool
    backup_supported: bool


PLATFORM_COMPONENTS: list[PlatformComponent] = [
    PlatformComponent(
        name="postgresql",
        display_name="PostgreSQL",
        category=ComponentCategory.DATA_STORE,
        helm_chart="postgresql",
        namespace="platform-data",
        depends_on=[],
        health_check_type="sql",
        health_check_target="SELECT 1",
        has_migration=True,
        backup_supported=True,
    ),
    PlatformComponent(
        name="redis",
        display_name="Redis",
        category=ComponentCategory.DATA_STORE,
        helm_chart="redis",
        namespace="platform-data",
        depends_on=[],
        health_check_type="tcp",
        health_check_target="PING",
        has_migration=False,
        backup_supported=True,
    ),
    PlatformComponent(
        name="kafka",
        display_name="Kafka",
        category=ComponentCategory.DATA_STORE,
        helm_chart="kafka",
        namespace="platform-data",
        depends_on=[],
        health_check_type="http",
        health_check_target="broker-metadata",
        has_migration=True,
        backup_supported=False,
    ),
    PlatformComponent(
        name="qdrant",
        display_name="Qdrant",
        category=ComponentCategory.DATA_STORE,
        helm_chart="qdrant",
        namespace="platform-data",
        depends_on=[],
        health_check_type="http",
        health_check_target="/healthz",
        has_migration=True,
        backup_supported=True,
    ),
    PlatformComponent(
        name="neo4j",
        display_name="Neo4j",
        category=ComponentCategory.DATA_STORE,
        helm_chart="neo4j",
        namespace="platform-data",
        depends_on=[],
        health_check_type="sql",
        health_check_target="RETURN 1",
        has_migration=True,
        backup_supported=True,
    ),
    PlatformComponent(
        name="clickhouse",
        display_name="ClickHouse",
        category=ComponentCategory.DATA_STORE,
        helm_chart="clickhouse",
        namespace="platform-data",
        depends_on=[],
        health_check_type="sql",
        health_check_target="SELECT 1",
        has_migration=True,
        backup_supported=True,
    ),
    PlatformComponent(
        name="opensearch",
        display_name="OpenSearch",
        category=ComponentCategory.DATA_STORE,
        helm_chart="opensearch",
        namespace="platform-data",
        depends_on=[],
        health_check_type="http",
        health_check_target="/_cluster/health",
        has_migration=True,
        backup_supported=True,
    ),
    PlatformComponent(
        name="minio",
        display_name="MinIO",
        category=ComponentCategory.DATA_STORE,
        helm_chart="minio",
        namespace="platform-data",
        depends_on=[],
        health_check_type="http",
        health_check_target="HEAD bucket",
        has_migration=True,
        backup_supported=True,
    ),
    PlatformComponent(
        name="runtime-controller",
        display_name="Runtime Controller",
        category=ComponentCategory.SATELLITE_SERVICE,
        helm_chart="runtime-controller",
        namespace="platform-execution",
        depends_on=["postgresql", "redis", "kafka", "minio"],
        health_check_type="grpc",
        health_check_target="runtime-controller:50051",
        has_migration=False,
        backup_supported=False,
    ),
    PlatformComponent(
        name="reasoning-engine",
        display_name="Reasoning Engine",
        category=ComponentCategory.SATELLITE_SERVICE,
        helm_chart="reasoning-engine",
        namespace="platform-execution",
        depends_on=["postgresql", "redis", "kafka"],
        health_check_type="grpc",
        health_check_target="reasoning-engine:50052",
        has_migration=False,
        backup_supported=False,
    ),
    PlatformComponent(
        name="simulation-controller",
        display_name="Simulation Controller",
        category=ComponentCategory.SATELLITE_SERVICE,
        helm_chart="simulation-controller",
        namespace="platform-simulation",
        depends_on=["postgresql", "kafka", "minio"],
        health_check_type="grpc",
        health_check_target="simulation-controller:50055",
        has_migration=False,
        backup_supported=False,
    ),
    PlatformComponent(
        name="control-plane",
        display_name="Control Plane",
        category=ComponentCategory.CONTROL_PLANE,
        helm_chart="control-plane",
        namespace="platform-control",
        depends_on=[
            "postgresql",
            "redis",
            "kafka",
            "qdrant",
            "neo4j",
            "clickhouse",
            "opensearch",
            "minio",
            "runtime-controller",
            "reasoning-engine",
            "simulation-controller",
        ],
        health_check_type="http",
        health_check_target="/health",
        has_migration=False,
        backup_supported=False,
    ),
]
