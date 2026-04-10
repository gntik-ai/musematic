from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from importlib import import_module
from json import dumps, loads
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from platform.common.config import Settings, settings as default_settings
from platform.common.exceptions import (
    HopLimitExceededError,
    Neo4jClientError,
    Neo4jConnectionError,
    Neo4jConstraintViolationError,
    Neo4jNodeNotFoundError,
)


@dataclass(frozen=True, slots=True)
class PathResult:
    nodes: list[dict[str, Any]]
    relationships: list[dict[str, Any]]
    length: int


class AsyncLocalGraphClient:
    def __init__(self, settings: Settings, engine: AsyncEngine | None = None) -> None:
        self.settings = settings
        self._owns_engine = engine is None
        self._engine = engine
        self._schema_ready = False
        self._schema_lock = asyncio.Lock()

    async def traverse_path(
        self,
        start_id: str,
        rel_types: list[str],
        max_hops: int,
        workspace_id: str,
    ) -> list[PathResult]:
        if max_hops > 3:
            raise HopLimitExceededError("local mode supports max 3 hops")

        await self._ensure_schema()
        engine = self._ensure_engine()
        query = text(
            """
            WITH RECURSIVE traverse AS (
                SELECT
                    n.id,
                    ARRAY[n.id]::text[] AS visited_ids,
                    jsonb_build_array(n.properties) AS path_nodes,
                    '[]'::jsonb AS path_relationships,
                    0 AS depth
                FROM graph_nodes AS n
                WHERE n.id = :start_id
                  AND n.workspace_id = :workspace_id
                UNION ALL
                SELECT
                    next_node.id,
                    traverse.visited_ids || next_node.id,
                    traverse.path_nodes || jsonb_build_array(next_node.properties),
                    traverse.path_relationships || jsonb_build_array(edge.properties),
                    traverse.depth + 1
                FROM traverse
                JOIN graph_edges AS edge
                  ON edge.from_id = traverse.id
                JOIN graph_nodes AS next_node
                  ON next_node.id = edge.to_id
                WHERE traverse.depth < :max_hops
                  AND next_node.workspace_id = :workspace_id
                  AND (
                    cardinality(CAST(:rel_types AS text[])) = 0
                    OR edge.rel_type = ANY(CAST(:rel_types AS text[]))
                  )
                  AND NOT next_node.id = ANY(traverse.visited_ids)
            )
            SELECT path_nodes, path_relationships, depth
            FROM traverse
            WHERE depth > 0
            ORDER BY depth, id
            """
        )
        async with engine.connect() as connection:
            result = await connection.execute(
                query,
                {
                    "start_id": start_id,
                    "workspace_id": workspace_id,
                    "max_hops": max_hops,
                    "rel_types": rel_types,
                },
            )
            rows = result.mappings().all()

        return [
            PathResult(
                nodes=self._jsonb_array_to_dicts(row["path_nodes"]),
                relationships=self._jsonb_array_to_dicts(row["path_relationships"]),
                length=int(row["depth"]),
            )
            for row in rows
        ]

    async def create_node(self, label: str, properties: dict[str, Any]) -> str:
        await self._ensure_schema()
        engine = self._ensure_engine()
        node_id = str(properties["id"])
        workspace_id = str(properties["workspace_id"])
        payload = dict(properties)
        payload.setdefault("id", node_id)
        payload.setdefault("workspace_id", workspace_id)

        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        """
                        INSERT INTO graph_nodes (id, label, workspace_id, properties)
                        VALUES (:id, :label, :workspace_id, CAST(:properties AS jsonb))
                        """
                    ),
                    {
                        "id": node_id,
                        "label": label,
                        "workspace_id": workspace_id,
                        "properties": dumps(payload),
                    },
                )
        except IntegrityError as exc:
            raise Neo4jConstraintViolationError(str(exc)) from exc
        return node_id

    async def create_relationship(
        self,
        from_id: str,
        to_id: str,
        rel_type: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        await self._ensure_schema()
        engine = self._ensure_engine()
        payload = dict(properties or {})

        async with engine.begin() as connection:
            existing = await connection.execute(
                text("SELECT id FROM graph_nodes WHERE id IN (:from_id, :to_id)"),
                {"from_id": from_id, "to_id": to_id},
            )
            found_ids = {row[0] for row in existing.fetchall()}
            if {from_id, to_id} - found_ids:
                raise Neo4jNodeNotFoundError(
                    f"Cannot create relationship {rel_type!r}: one or more nodes are missing."
                )

            await connection.execute(
                text(
                    """
                    INSERT INTO graph_edges (from_id, to_id, rel_type, properties)
                    VALUES (:from_id, :to_id, :rel_type, CAST(:properties AS jsonb))
                    """
                ),
                {
                    "from_id": from_id,
                    "to_id": to_id,
                    "rel_type": rel_type,
                    "properties": dumps(payload),
                },
            )

    async def shortest_path(
        self,
        from_id: str,
        to_id: str,
        rel_types: list[str] | None = None,
    ) -> PathResult | None:
        raise NotImplementedError("shortest_path not available in local mode")

    async def health_check(self) -> dict[str, Any]:
        await self._ensure_schema()
        return {"status": "ok", "mode": "local"}

    async def close(self) -> None:
        if self._owns_engine and self._engine is not None:
            await self._engine.dispose()

    def _resolve_engine(self) -> AsyncEngine:
        try:
            database_module = import_module("platform.common.database")
        except Exception:
            database_url = os.environ.get("DATABASE_URL")
            if not database_url:
                raise Neo4jConnectionError(
                    "DATABASE_URL environment variable is required for local graph mode."
                ) from None
            return create_async_engine(database_url, pool_pre_ping=True)
        return cast(AsyncEngine, getattr(database_module, "engine"))

    async def _ensure_schema(self) -> None:
        if self._schema_ready:
            return

        async with self._schema_lock:
            if self._schema_ready:
                return

            engine = self._ensure_engine()
            ddl = (
                """
                CREATE TABLE IF NOT EXISTS graph_nodes (
                    id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    properties JSONB NOT NULL DEFAULT '{}'::jsonb
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS graph_edges (
                    id BIGSERIAL PRIMARY KEY,
                    from_id TEXT NOT NULL REFERENCES graph_nodes(id) ON DELETE CASCADE,
                    to_id TEXT NOT NULL REFERENCES graph_nodes(id) ON DELETE CASCADE,
                    rel_type TEXT NOT NULL,
                    properties JSONB NOT NULL DEFAULT '{}'::jsonb
                )
                """,
                "CREATE INDEX IF NOT EXISTS ix_graph_nodes_workspace_id ON graph_nodes (workspace_id)",
                "CREATE INDEX IF NOT EXISTS ix_graph_edges_from_rel_type ON graph_edges (from_id, rel_type)",
                "CREATE INDEX IF NOT EXISTS ix_graph_edges_to_rel_type ON graph_edges (to_id, rel_type)",
            )
            async with engine.begin() as connection:
                for statement in ddl:
                    await connection.execute(text(statement))
            self._schema_ready = True

    def _jsonb_array_to_dicts(self, value: Any) -> list[dict[str, Any]]:
        if value is None:
            return []
        if isinstance(value, str):
            parsed = loads(value)
            return cast(list[dict[str, Any]], parsed)
        return cast(list[dict[str, Any]], value)

    def _ensure_engine(self) -> AsyncEngine:
        if self._engine is None:
            self._engine = self._resolve_engine()
        return self._engine


class AsyncNeo4jClient:
    def __init__(self, settings: Settings | None = None, engine: AsyncEngine | None = None) -> None:
        self.settings = settings or default_settings
        self.mode = self._resolve_mode(self.settings)
        self._driver: Any | None = None
        self._driver_lock = asyncio.Lock()
        self._local = AsyncLocalGraphClient(self.settings, engine=engine) if self.mode == "local" else None

    async def run_query(
        self,
        cypher: str,
        params: dict[str, Any] | None = None,
        workspace_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if self.mode == "local":
            raise Neo4jClientError("run_query is only available in neo4j mode.")

        query_params = dict(params or {})
        if workspace_id is not None:
            query_params.setdefault("workspace_id", workspace_id)

        driver = await self._get_driver()
        try:
            async with driver.session() as session:
                result = await session.run(cypher, query_params)
                rows = [self._serialize_record(record.data()) async for record in result]
                return cast(list[dict[str, Any]], rows)
        except Exception as exc:
            raise self._translate_exception(exc) from exc

    async def create_node(self, label: str, properties: dict[str, Any]) -> str:
        if self.mode == "local":
            assert self._local is not None
            return await self._local.create_node(label, properties)

        if not properties.get("id"):
            raise Neo4jClientError("create_node requires properties['id'].")
        if not properties.get("workspace_id"):
            raise Neo4jClientError("create_node requires properties['workspace_id'].")
        if not self._is_safe_identifier(label):
            raise Neo4jClientError(f"Unsupported node label: {label!r}")

        cypher = f"CREATE (n:{label}) SET n = $properties RETURN n.id AS id"
        rows = await self.run_query(cypher, params={"properties": properties})
        return str(rows[0]["id"])

    async def create_relationship(
        self,
        from_id: str,
        to_id: str,
        rel_type: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        if self.mode == "local":
            assert self._local is not None
            await self._local.create_relationship(from_id, to_id, rel_type, properties)
            return

        if not self._is_safe_identifier(rel_type):
            raise Neo4jClientError(f"Unsupported relationship type: {rel_type!r}")

        cypher = f"""
        MATCH (source {{id: $from_id}}), (target {{id: $to_id}})
        CREATE (source)-[rel:{rel_type}]->(target)
        SET rel = $properties
        RETURN count(rel) AS created
        """
        rows = await self.run_query(
            cypher,
            params={
                "from_id": from_id,
                "to_id": to_id,
                "properties": properties or {},
            },
        )
        if not rows or int(rows[0]["created"]) != 1:
            raise Neo4jNodeNotFoundError(
                f"Cannot create relationship {rel_type!r}: one or more nodes are missing."
            )

    async def traverse_path(
        self,
        start_id: str,
        rel_types: list[str],
        max_hops: int,
        workspace_id: str,
    ) -> list[PathResult]:
        if self.mode == "local":
            assert self._local is not None
            return await self._local.traverse_path(start_id, rel_types, max_hops, workspace_id)

        rel_spec = self._relationship_pattern(rel_types)
        cypher = f"""
        MATCH path = (start {{id: $start_id}})-[{rel_spec}*1..{max_hops}]->(target)
        WHERE start.workspace_id = $workspace_id
          AND ALL(node IN nodes(path) WHERE node.workspace_id = $workspace_id)
        RETURN path
        """
        rows = await self.run_query(
            cypher,
            params={"start_id": start_id},
            workspace_id=workspace_id,
        )
        results: list[PathResult] = []
        for row in rows:
            path = row.get("path")
            if isinstance(path, PathResult):
                results.append(path)
        return results

    async def shortest_path(
        self,
        from_id: str,
        to_id: str,
        rel_types: list[str] | None = None,
    ) -> PathResult | None:
        if self.mode == "local":
            assert self._local is not None
            return await self._local.shortest_path(from_id, to_id, rel_types)

        rel_spec = self._relationship_pattern(rel_types or [])
        cypher = f"""
        MATCH (source {{id: $from_id}}), (target {{id: $to_id}})
        MATCH path = shortestPath((source)-[{rel_spec}*]-(target))
        RETURN path
        """
        rows = await self.run_query(cypher, params={"from_id": from_id, "to_id": to_id})
        if not rows:
            return None
        path = rows[0].get("path")
        return path if isinstance(path, PathResult) else None

    async def health_check(self) -> dict[str, Any]:
        if self.mode == "local":
            assert self._local is not None
            return await self._local.health_check()

        driver = await self._get_driver()
        try:
            async with driver.session() as session:
                result = await session.run(
                    "CALL dbms.components() YIELD name, versions, edition "
                    "RETURN name, versions, edition LIMIT 1"
                )
                record = await result.single()
                if record is None:
                    return {"status": "error", "mode": "neo4j", "error": "No dbms.components() result."}
                return {
                    "status": "ok",
                    "mode": "neo4j",
                    "version": cast(list[str], record["versions"])[0],
                    "edition": str(record["edition"]).lower(),
                }
        except Exception as exc:
            return {"status": "error", "mode": "neo4j", "error": str(exc)}

    async def close(self) -> None:
        if self.mode == "local":
            assert self._local is not None
            await self._local.close()
            return

        if self._driver is not None:
            await self._driver.close()
            self._driver = None

    async def __aenter__(self) -> "AsyncNeo4jClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    @staticmethod
    def _resolve_mode(settings: Settings) -> str:
        if settings.GRAPH_MODE not in {"auto", "neo4j", "local"}:
            raise Neo4jClientError(
                f"Unsupported GRAPH_MODE {settings.GRAPH_MODE!r}; expected 'auto', 'neo4j', or 'local'."
            )
        if settings.GRAPH_MODE == "auto":
            return "neo4j" if settings.NEO4J_URL else "local"
        return settings.GRAPH_MODE

    async def _get_driver(self) -> Any:
        if self.mode != "neo4j":
            raise Neo4jClientError("Neo4j driver is not available in local mode.")
        if self._driver is not None:
            return self._driver

        async with self._driver_lock:
            if self._driver is not None:
                return self._driver
            if not self.settings.NEO4J_URL:
                raise Neo4jConnectionError("NEO4J_URL is required when GRAPH_MODE resolves to neo4j.")
            neo4j_module = import_module("neo4j")
            async_graph_database = getattr(neo4j_module, "AsyncGraphDatabase")
            self._driver = async_graph_database.driver(
                self.settings.NEO4J_URL,
                max_connection_pool_size=self.settings.NEO4J_MAX_CONNECTION_POOL_SIZE,
            )
            return self._driver

    def _translate_exception(self, exc: Exception) -> Neo4jClientError:
        exc_module = import_module("neo4j.exceptions")
        constraint_error = getattr(exc_module, "ConstraintError", None)
        service_unavailable = getattr(exc_module, "ServiceUnavailable", None)
        auth_error = getattr(exc_module, "AuthError", None)
        client_error = getattr(exc_module, "ClientError", None)

        if constraint_error is not None and isinstance(exc, constraint_error):
            return Neo4jConstraintViolationError(str(exc))
        if service_unavailable is not None and isinstance(exc, service_unavailable):
            return Neo4jConnectionError(str(exc))
        if auth_error is not None and isinstance(exc, auth_error):
            return Neo4jConnectionError(str(exc))
        if client_error is not None and isinstance(exc, client_error):
            code = str(getattr(exc, "code", ""))
            if "ConstraintValidationFailed" in code:
                return Neo4jConstraintViolationError(str(exc))
            if "Security" in code:
                return Neo4jConnectionError(str(exc))
        return Neo4jClientError(str(exc))

    def _serialize_record(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: self._serialize_record(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._serialize_record(item) for item in value]

        value_type = type(value).__name__
        if value_type == "Node":
            return dict(value)
        if value_type == "Relationship":
            return dict(value)
        if value_type == "Path":
            return PathResult(
                nodes=[dict(node) for node in value.nodes],
                relationships=[dict(rel) for rel in value.relationships],
                length=len(value.relationships),
            )
        return value

    def _relationship_pattern(self, rel_types: list[str]) -> str:
        if not rel_types:
            return "rel"
        if not all(self._is_safe_identifier(rel_type) for rel_type in rel_types):
            raise Neo4jClientError(f"Unsupported relationship types: {rel_types!r}")
        return f"rel:{'|'.join(rel_types)}"

    @staticmethod
    def _is_safe_identifier(value: str) -> bool:
        if not value:
            return False
        head = value[0]
        if not (head.isalpha() or head == "_"):
            return False
        return all(char.isalnum() or char == "_" for char in value)
