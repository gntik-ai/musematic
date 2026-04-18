from __future__ import annotations

import asyncio
import inspect
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from platform.accounts.models import SignupSource, UserStatus
from platform.accounts.repository import AccountsRepository
from platform.auth.events import IBORSyncCompletedPayload, publish_ibor_sync_completed
from platform.auth.exceptions import (
    IBORConnectorNotFoundError,
    IBORCredentialResolutionError,
    IBORSyncInProgressError,
)
from platform.auth.models import IBORConnector, IBORSyncMode, IBORSyncRun, IBORSyncRunStatus
from platform.auth.rbac import rbac_engine
from platform.auth.repository import AuthRepository
from platform.auth.schemas import IBORSyncRunResponse, IBORSyncTriggerResponse
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.events.producer import EventProducer
from platform.registry.models import AgentProfile, LifecycleStatus
from typing import Any
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@dataclass(slots=True)
class _LocalLock:
    success: bool
    token: str | None = None


class IBORSyncService:
    def __init__(
        self,
        *,
        repository: AuthRepository,
        accounts_repository: AccountsRepository | None,
        redis_client: AsyncRedisClient,
        settings: PlatformSettings,
        producer: EventProducer | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        credential_resolver: Any | None = None,
    ) -> None:
        self.repository = repository
        self.accounts_repository = accounts_repository
        self.redis_client = redis_client
        self.settings = settings
        self.producer = producer
        self.session_factory = session_factory
        self.credential_resolver = credential_resolver
        self._background_tasks: set[asyncio.Task[Any]] = set()

    async def trigger_sync(
        self,
        connector_id: UUID,
        *,
        triggered_by: UUID | None,
    ) -> IBORSyncTriggerResponse:
        connector = await self._get_connector_or_raise(connector_id)
        lock = await self._acquire_lock(connector.id, connector.cadence_seconds + 60)
        if not lock.success or lock.token is None:
            raise IBORSyncInProgressError(str(connector.id))

        run = await self.repository.create_sync_run(
            connector_id=connector.id,
            mode=connector.sync_mode,
            status=IBORSyncRunStatus.running,
            triggered_by=triggered_by,
        )
        await self.repository.touch_connector_run(
            connector,
            status=IBORSyncRunStatus.running.value,
            last_run_at=run.started_at,
        )

        task: asyncio.Task[Any]
        if self.session_factory is None:
            task = asyncio.create_task(
                self._continue_sync(
                    connector.id,
                    run.id,
                    triggered_by=triggered_by,
                    lock_token=lock.token,
                )
            )
        else:
            task = asyncio.create_task(
                self._run_background(
                    connector.id,
                    run.id,
                    triggered_by=triggered_by,
                    lock_token=lock.token,
                )
            )
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

        return IBORSyncTriggerResponse(
            run_id=run.id,
            connector_id=connector.id,
            status=IBORSyncRunStatus.running,
            started_at=run.started_at,
        )

    async def run_sync(
        self,
        connector_id: UUID,
        *,
        triggered_by: UUID | None,
    ) -> IBORSyncRunResponse:
        connector = await self._get_connector_or_raise(connector_id)
        lock = await self._acquire_lock(connector.id, connector.cadence_seconds + 60)
        if not lock.success or lock.token is None:
            raise IBORSyncInProgressError(str(connector.id))

        run = await self.repository.create_sync_run(
            connector_id=connector.id,
            mode=connector.sync_mode,
            status=IBORSyncRunStatus.running,
            triggered_by=triggered_by,
        )
        await self.repository.touch_connector_run(
            connector,
            status=IBORSyncRunStatus.running.value,
            last_run_at=run.started_at,
        )
        return await self._continue_sync(
            connector.id,
            run.id,
            triggered_by=triggered_by,
            lock_token=lock.token,
        )

    async def _run_background(
        self,
        connector_id: UUID,
        run_id: UUID,
        *,
        triggered_by: UUID | None,
        lock_token: str,
    ) -> None:
        assert self.session_factory is not None
        async with self.session_factory() as session:
            service = IBORSyncService(
                repository=AuthRepository(session),
                accounts_repository=AccountsRepository(session),
                redis_client=self.redis_client,
                settings=self.settings,
                producer=self.producer,
                session_factory=self.session_factory,
                credential_resolver=self.credential_resolver,
            )
            try:
                await service._continue_sync(
                    connector_id,
                    run_id,
                    triggered_by=triggered_by,
                    lock_token=lock_token,
                )
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def _continue_sync(
        self,
        connector_id: UUID,
        run_id: UUID,
        *,
        triggered_by: UUID | None,
        lock_token: str,
    ) -> IBORSyncRunResponse:
        connector = await self._get_connector_or_raise(connector_id)
        run = await self.repository.get_sync_run(run_id)
        if run is None:
            raise IBORConnectorNotFoundError(str(run_id))

        counts = self._empty_counts()
        error_details: list[dict[str, Any]] = []
        started_at = run.started_at
        status = IBORSyncRunStatus.failed
        try:
            if connector.sync_mode is IBORSyncMode.pull:
                counts, error_details = await self._run_pull(connector)
            else:
                counts, error_details = await self._push_scim(connector)
            status = (
                IBORSyncRunStatus.partial_success if error_details else IBORSyncRunStatus.succeeded
            )
        except Exception as exc:
            error_details.append({"error": str(exc)})
            counts["errors"] += 1
            status = IBORSyncRunStatus.failed
        finally:
            finished_at = datetime.now(UTC)
            updated_run = await self.repository.update_sync_run(
                run,
                status=status,
                counts=counts,
                error_details=error_details,
                finished_at=finished_at,
            )
            await self.repository.touch_connector_run(
                connector,
                status=status.value,
                last_run_at=finished_at,
            )
            duration_ms = max(int((finished_at - started_at).total_seconds() * 1000), 0)
            await publish_ibor_sync_completed(
                IBORSyncCompletedPayload(
                    run_id=updated_run.id,
                    connector_id=connector.id,
                    connector_name=connector.name,
                    mode=connector.sync_mode,
                    status=status,
                    duration_ms=duration_ms,
                    counts=counts,
                ),
                uuid4(),
                self.producer,
            )
            await self._release_lock(connector.id, lock_token)

        return self._run_response(updated_run)

    async def _run_pull(
        self,
        connector: IBORConnector,
    ) -> tuple[dict[str, int], list[dict[str, Any]]]:
        if connector.source_type.value == "ldap":
            entries = await self._pull_ldap(connector)
        elif connector.source_type.value == "oidc":
            entries = await self._pull_oidc(connector)
        else:
            entries = await self._pull_scim(connector, mode="pull")

        counts = self._empty_counts()
        errors: list[dict[str, Any]] = []
        processed_user_ids: set[UUID] = set()

        for entry in entries:
            try:
                (
                    user_id,
                    created_count,
                    updated_count,
                    roles_added,
                    roles_revoked,
                ) = await self._reconcile_user_roles(
                    connector,
                    entry,
                )
                processed_user_ids.add(user_id)
                counts["users_created"] += created_count
                counts["users_updated"] += updated_count
                counts["roles_added"] += roles_added
                counts["roles_revoked"] += roles_revoked
            except Exception as exc:
                counts["errors"] += 1
                errors.append(
                    {
                        "email": str(entry.get("email") or entry.get("userName") or "unknown"),
                        "error": str(exc),
                    }
                )

        existing_roles = await self.repository.list_user_roles_by_connector(connector.id)
        missing_user_ids = {
            assignment.user_id for assignment in existing_roles
        } - processed_user_ids
        for user_id in missing_user_ids:
            counts["roles_revoked"] += await rbac_engine.revoke_connector_sourced_roles(
                self.repository,
                user_id=user_id,
                connector_id=connector.id,
                keep_assignments=set(),
            )

        return counts, errors

    async def _reconcile_user_roles(
        self,
        connector: IBORConnector,
        directory_user: dict[str, Any],
    ) -> tuple[UUID, int, int, int, int]:
        email = (
            str(directory_user.get("email") or directory_user.get("userName") or "").strip().lower()
        )
        if not email:
            raise ValueError("directory user is missing email")
        display_name = str(
            directory_user.get("display_name")
            or directory_user.get("displayName")
            or email.split("@", 1)[0]
        )
        groups = self._normalize_groups(directory_user.get("groups", []))
        desired_assignments: set[tuple[str, UUID | None]] = set()
        for rule in connector.role_mapping_policy:
            if str(rule.get("directory_group")) not in groups:
                continue
            desired_assignments.add(
                (
                    str(rule["platform_role"]),
                    UUID(str(rule["workspace_scope"])) if rule.get("workspace_scope") else None,
                )
            )
            break

        user_id, created_count, updated_count = await self._ensure_user(email, display_name)
        current_roles = await self.repository.list_user_roles(user_id=user_id)
        current_pairs = {(role.role, role.workspace_id): role for role in current_roles}
        roles_added = 0
        for role_name, workspace_scope in desired_assignments:
            existing = current_pairs.get((role_name, workspace_scope))
            if existing is not None:
                continue
            await self.repository.assign_user_role(
                user_id,
                role_name,
                workspace_scope,
                source_connector_id=connector.id,
            )
            roles_added += 1

        roles_revoked = await rbac_engine.revoke_connector_sourced_roles(
            self.repository,
            user_id=user_id,
            connector_id=connector.id,
            keep_assignments=desired_assignments,
        )
        return user_id, created_count, updated_count, roles_added, roles_revoked

    async def _ensure_user(self, email: str, display_name: str) -> tuple[UUID, int, int]:
        if self.accounts_repository is not None:
            existing = await self.accounts_repository.get_user_by_email(email)
            if existing is not None:
                return existing.id, 0, 0
            created = await self.accounts_repository.create_user(
                email=email,
                display_name=display_name,
                status=UserStatus.active,
                signup_source=SignupSource.self_registration,
            )
            return created.id, 1, 0

        existing_platform_user = await self.repository.get_platform_user_by_email(email)
        if existing_platform_user is not None:
            return existing_platform_user.id, 0, 0
        created_id = uuid4()
        await self.repository.create_platform_user(created_id, email, display_name)
        return created_id, 1, 0

    async def _push_scim(
        self,
        connector: IBORConnector,
        *,
        mode: str = "push",
    ) -> tuple[dict[str, int], list[dict[str, Any]]]:
        credentials = await self._resolve_credential(connector)
        counts = self._empty_counts()
        errors: list[dict[str, Any]] = []
        result = await self.repository.db.execute(
            select(AgentProfile).where(
                AgentProfile.status.in_(
                    [
                        LifecycleStatus.published,
                        LifecycleStatus.disabled,
                        LifecycleStatus.deprecated,
                        LifecycleStatus.decommissioned,
                    ]
                )
            )
        )
        agents = list(result.scalars().all())
        collector = credentials.get("collector")
        for agent in agents:
            payload = {
                "userName": agent.fqn,
                "displayName": agent.display_name or agent.fqn,
                "externalId": str(agent.id),
                "active": agent.status is not LifecycleStatus.decommissioned,
            }
            try:
                if collector is not None and hasattr(collector, "post_user"):
                    result = collector.post_user(payload)
                    if inspect.isawaitable(result):
                        await result
                else:
                    endpoint = str(
                        credentials.get("scim_endpoint") or credentials.get("base_url") or ""
                    ).rstrip("/")
                    if not endpoint:
                        raise IBORCredentialResolutionError(connector.name)
                    headers = self._credential_headers(credentials)
                    async with httpx.AsyncClient(timeout=30) as client:
                        response = await client.post(
                            f"{endpoint}/Users",
                            json=payload,
                            headers=headers,
                        )
                        response.raise_for_status()
                counts["users_updated"] += 1
            except Exception as exc:
                counts["errors"] += 1
                errors.append({"agent_fqn": agent.fqn, "error": str(exc), "mode": mode})
        return counts, errors

    async def _pull_oidc(self, connector: IBORConnector) -> list[dict[str, Any]]:
        credentials = await self._resolve_credential(connector)
        if isinstance(credentials.get("users"), list):
            return self._normalize_directory_users(credentials["users"])
        endpoint = str(credentials.get("users_url") or credentials.get("groups_url") or "")
        if not endpoint:
            raise IBORCredentialResolutionError(connector.name)
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(endpoint, headers=self._credential_headers(credentials))
            response.raise_for_status()
            payload = response.json()
        return self._normalize_directory_payload(payload)

    async def _pull_scim(
        self,
        connector: IBORConnector,
        *,
        mode: str = "pull",
    ) -> list[dict[str, Any]]:
        del mode
        credentials = await self._resolve_credential(connector)
        if isinstance(credentials.get("users"), list):
            return self._normalize_directory_users(credentials["users"])
        endpoint = str(
            credentials.get("scim_endpoint") or credentials.get("base_url") or ""
        ).rstrip("/")
        if not endpoint:
            raise IBORCredentialResolutionError(connector.name)
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{endpoint}/Users",
                headers=self._credential_headers(credentials),
            )
            response.raise_for_status()
            payload = response.json()
        return self._normalize_directory_payload(payload)

    async def _pull_ldap(self, connector: IBORConnector) -> list[dict[str, Any]]:
        credentials = await self._resolve_credential(connector)
        if isinstance(credentials.get("users"), list):
            return self._normalize_directory_users(credentials["users"])
        try:
            from ldap3 import ALL, Connection, Server
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise IBORCredentialResolutionError(connector.name) from exc

        server = Server(str(credentials.get("server")), get_info=ALL)
        connection = Connection(
            server,
            user=str(credentials.get("bind_dn") or ""),
            password=str(credentials.get("password") or ""),
            auto_bind=True,
        )
        base_dn = str(credentials.get("base_dn") or "")
        search_filter = str(credentials.get("search_filter") or "(objectClass=person)")
        attributes = list(credentials.get("attributes") or ["mail", "displayName", "memberOf"])
        connection.search(base_dn, search_filter, attributes=attributes)
        normalized = []
        for entry in connection.entries:
            data = entry.entry_attributes_as_dict
            normalized.append(
                {
                    "email": data.get("mail"),
                    "display_name": data.get("displayName"),
                    "groups": data.get("memberOf", []),
                }
            )
        return self._normalize_directory_users(normalized)

    async def _resolve_credential(self, connector: IBORConnector) -> dict[str, Any]:
        if self.credential_resolver is not None:
            result = self.credential_resolver(connector.credential_ref)
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, dict):
                return result

        inline = connector.credential_ref.strip()
        if inline.startswith("{"):
            return dict(json.loads(inline))

        env_key = self._credential_env_key(inline)
        env_value = os.getenv(env_key)
        if env_value:
            return dict(json.loads(env_value))
        raise IBORCredentialResolutionError(connector.name)

    @staticmethod
    def _credential_env_key(reference: str) -> str:
        normalized = reference.upper().replace("-", "_").replace("/", "_")
        return f"IBOR_CREDENTIAL_{normalized}"

    @staticmethod
    def _credential_headers(credentials: dict[str, Any]) -> dict[str, str]:
        headers = {
            str(key): str(value) for key, value in dict(credentials.get("headers") or {}).items()
        }
        token = credentials.get("token") or credentials.get("access_token")
        if token and "Authorization" not in headers:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    @staticmethod
    def _normalize_directory_payload(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return IBORSyncService._normalize_directory_users(payload)
        if isinstance(payload, dict):
            for key in ("items", "users", "Resources"):
                value = payload.get(key)
                if isinstance(value, list):
                    return IBORSyncService._normalize_directory_users(value)
        return []

    @staticmethod
    def _normalize_directory_users(items: list[Any]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for item in items:
            if isinstance(item, str):
                normalized.append(
                    {
                        "email": item,
                        "display_name": item.split("@", 1)[0],
                        "groups": [],
                    }
                )
                continue
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    "email": item.get("email") or item.get("userName") or item.get("mail"),
                    "display_name": (
                        item.get("display_name") or item.get("displayName") or item.get("name")
                    ),
                    "groups": item.get("groups") or item.get("memberOf") or [],
                }
            )
        return normalized

    @staticmethod
    def _normalize_groups(groups: Any) -> set[str]:
        if not isinstance(groups, list):
            return set()
        normalized = set()
        for group in groups:
            if isinstance(group, str):
                normalized.add(group)
                continue
            if isinstance(group, dict):
                for key in ("value", "display", "name", "directory_group"):
                    value = group.get(key)
                    if isinstance(value, str) and value:
                        normalized.add(value)
                        break
        return normalized

    async def _get_connector_or_raise(self, connector_id: UUID) -> IBORConnector:
        connector = await self.repository.get_connector(connector_id)
        if connector is None:
            raise IBORConnectorNotFoundError(str(connector_id))
        return connector

    async def _acquire_lock(self, connector_id: UUID, ttl_seconds: int) -> _LocalLock:
        acquire = getattr(self.redis_client, "acquire_lock", None)
        if callable(acquire):
            result = await acquire("ibor:sync", str(connector_id), ttl_seconds)
            return _LocalLock(
                success=bool(getattr(result, "success", False)),
                token=getattr(result, "token", None),
            )
        client = await self.redis_client._get_client()
        key = f"lock:ibor:sync:{connector_id}"
        if await client.get(key) is not None:
            return _LocalLock(success=False, token=None)
        token = str(uuid4())
        await client.set(key, token, ex=ttl_seconds)
        return _LocalLock(success=True, token=token)

    async def _release_lock(self, connector_id: UUID, token: str) -> None:
        release = getattr(self.redis_client, "release_lock", None)
        if callable(release):
            await release("ibor:sync", str(connector_id), token)
            return
        client = await self.redis_client._get_client()
        key = f"lock:ibor:sync:{connector_id}"
        current = await client.get(key)
        if current == token:
            await client.delete(key)

    @staticmethod
    def _empty_counts() -> dict[str, int]:
        return {
            "users_created": 0,
            "users_updated": 0,
            "roles_added": 0,
            "roles_revoked": 0,
            "errors": 0,
        }

    @staticmethod
    def _run_response(run: IBORSyncRun) -> IBORSyncRunResponse:
        return IBORSyncRunResponse(
            id=run.id,
            connector_id=run.connector_id,
            mode=run.mode,
            started_at=run.started_at,
            finished_at=run.finished_at,
            status=run.status,
            counts={str(key): int(value) for key, value in run.counts.items()},
            error_details=[dict(item) for item in run.error_details],
            triggered_by=run.triggered_by,
        )
