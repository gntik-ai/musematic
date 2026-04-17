"""Schema migration and store initialisation helpers."""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

import httpx

from platform_cli.config import DeploymentMode, InstallerConfig
from platform_cli.paths import CONTROL_PLANE_ROOT, CONTROL_PLANE_SRC
from platform_cli.runtime import inferred_api_base_url
from platform_cli.secrets.generator import GeneratedSecrets


def _run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "command failed")


class MigrationRunner:
    """Run schema migrations and per-store bootstrap tasks."""

    def __init__(self, control_plane_root: Path | None = None) -> None:
        self.control_plane_root = control_plane_root or CONTROL_PLANE_ROOT

    def run_alembic(self, database_url: str) -> None:
        """Run Alembic migrations for the control plane."""

        env = os.environ.copy()
        env["DATABASE_URL"] = database_url
        existing_pythonpath = env.get("PYTHONPATH", "")
        segments = [str(CONTROL_PLANE_SRC)]
        if existing_pythonpath:
            segments.append(existing_pythonpath)
        env["PYTHONPATH"] = os.pathsep.join(segments)
        _run(
            ["alembic", "-c", "migrations/alembic.ini", "upgrade", "head"],
            cwd=self.control_plane_root,
            env=env,
        )

    async def init_qdrant(self, url: str, collection_name: str = "platform_documents") -> None:
        """Create the default Qdrant collection."""

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.put(
                f"{url.rstrip('/')}/collections/{collection_name}",
                json={"vectors": {"size": 1536, "distance": "Cosine"}},
            )
            if response.status_code not in {200, 201}:
                raise RuntimeError(f"qdrant init failed: {response.text}")

    async def init_neo4j(self, uri: str, password: str) -> None:
        """Create basic Neo4j constraints."""

        from neo4j import AsyncGraphDatabase

        driver = AsyncGraphDatabase.driver(uri, auth=("neo4j", password))
        try:
            async with driver.session() as session:
                await session.run(
                    "CREATE CONSTRAINT platform_node_id IF NOT EXISTS FOR (n:PlatformNode) "
                    "REQUIRE n.id IS UNIQUE"
                )
        finally:
            await driver.close()

    async def init_clickhouse(self, url: str) -> None:
        """Create a default ClickHouse table used by analytics."""

        import clickhouse_connect

        def _query() -> None:
            client = clickhouse_connect.get_client(host=url)
            client.command(
                "CREATE TABLE IF NOT EXISTS platform_events "
                "(ts DateTime, category String, payload String) "
                "ENGINE = MergeTree ORDER BY ts"
            )
            client.close()

        await asyncio.to_thread(_query)

    async def init_opensearch(self, url: str) -> None:
        """Create an index template for platform content."""

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.put(
                f"{url.rstrip('/')}/_index_template/platform-documents",
                json={
                    "index_patterns": ["platform-documents-*"],
                    "template": {"settings": {"number_of_shards": 1, "number_of_replicas": 0}},
                },
            )
            if response.status_code not in {200, 201}:
                raise RuntimeError(f"opensearch init failed: {response.text}")

    async def init_kafka(self, bootstrap: str, topics: list[str] | None = None) -> None:
        """Create required Kafka topics."""

        from aiokafka.admin import AIOKafkaAdminClient, NewTopic

        admin = AIOKafkaAdminClient(bootstrap_servers=bootstrap)
        await admin.start()
        try:
            topic_names = topics or ["platform.events", "execution.events", "trust.events"]
            new_topics = [
                NewTopic(name, num_partitions=1, replication_factor=1) for name in topic_names
            ]
            await admin.create_topics(new_topics, validate_only=False)
        except Exception as exc:
            if "TopicAlreadyExistsError" not in repr(exc):
                raise
        finally:
            await admin.close()

    async def init_minio(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        buckets: list[str] | None = None,
    ) -> None:
        """Create default buckets in MinIO/S3."""

        import aioboto3

        session = aioboto3.Session()
        bucket_names = buckets or ["platform-backups", "platform-assets"]
        async with session.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        ) as client:
            for bucket in bucket_names:
                try:
                    await client.create_bucket(Bucket=bucket)
                except Exception as exc:
                    if "BucketAlreadyOwnedByYou" not in repr(exc):
                        raise

    async def create_admin_user(self, api_url: str, email: str, password: str) -> None:
        """Create the initial admin account via the control plane API."""

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{api_url.rstrip('/')}/api/v1/accounts/register",
                json={
                    "email": email,
                    "display_name": "Platform Administrator",
                    "password": password,
                },
            )
            if response.status_code not in {200, 201, 202, 409}:
                raise RuntimeError(f"admin creation failed: {response.text}")

    async def run_all(self, config: InstallerConfig, secrets: GeneratedSecrets) -> None:
        """Run the supported migrations and bootstrap tasks for one deployment."""

        namespace_prefix = config.namespace
        if config.deployment_mode == DeploymentMode.LOCAL:
            database_url = f"sqlite+aiosqlite:///{config.data_dir / 'db' / 'platform.db'}"
            qdrant_url = "http://127.0.0.1:6333"
            neo4j_uri = "bolt://127.0.0.1:7687"
            clickhouse_host = "127.0.0.1"
            opensearch_url = "http://127.0.0.1:9200"
            kafka_bootstrap = "127.0.0.1:9092"
            minio_endpoint = "http://127.0.0.1:9000"
        else:
            database_url = (
                f"postgresql+asyncpg://postgres:{secrets.postgresql_password}"
                f"@postgresql.{namespace_prefix}-data.svc.cluster.local:5432/platform"
            )
            qdrant_url = f"http://qdrant.{namespace_prefix}-data.svc.cluster.local:6333"
            neo4j_uri = f"bolt://neo4j.{namespace_prefix}-data.svc.cluster.local:7687"
            clickhouse_host = f"clickhouse.{namespace_prefix}-data.svc.cluster.local"
            opensearch_url = f"http://opensearch.{namespace_prefix}-data.svc.cluster.local:9200"
            kafka_bootstrap = f"kafka.{namespace_prefix}-data.svc.cluster.local:9092"
            minio_endpoint = f"http://minio.{namespace_prefix}-data.svc.cluster.local:9000"

        self.run_alembic(database_url)
        await self.init_qdrant(qdrant_url)
        await self.init_neo4j(neo4j_uri, secrets.neo4j_password)
        await self.init_clickhouse(clickhouse_host)
        await self.init_opensearch(opensearch_url)
        await self.init_kafka(kafka_bootstrap)
        await self.init_minio(minio_endpoint, secrets.minio_access_key, secrets.minio_secret_key)
        await self.create_admin_user(
            inferred_api_base_url(config), config.admin.email, secrets.admin_password
        )
