"""Cascade deletion and tombstone canonicalisation.

Tombstone proof hashes are SHA-256 of JSON encoded with
``json.dumps(payload, sort_keys=True, separators=(",", ":"))``. The canonical
field list is ``subject_user_id_hash``, ``salt_version``, ``entities_deleted``,
``cascade_log`` and ``created_at_iso``. ``subject_user_id_hash`` is calculated as
``sha256(subject_user_id.bytes + salt).hexdigest()`` using the salt version
recorded on the tombstone. Any future canonicalisation change must introduce a
new ``tombstone_version`` and keep backward-compatible verification.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from platform.privacy_compliance.cascade_adapters.base import (
    STORE_ORDER,
    CascadeAdapter,
    CascadePlan,
)
from platform.privacy_compliance.exceptions import CascadePartialFailure, TombstoneNotFoundError
from platform.privacy_compliance.models import PrivacyDeletionTombstone
from platform.privacy_compliance.repository import PrivacyComplianceRepository
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class SignedTombstone:
    tombstone: str
    key_version: str
    signature: str
    proof_hash: str


class CascadeOrchestrator:
    def __init__(
        self,
        *,
        repository: PrivacyComplianceRepository,
        adapters: list[CascadeAdapter],
        signer: Any,
        salt_provider: Any,
        audit_chain: Any | None = None,
    ) -> None:
        self.repository = repository
        self.adapters = sorted(adapters, key=lambda adapter: STORE_ORDER.index(adapter.store_name))
        self.signer = signer
        self.salt_provider = salt_provider
        self.audit_chain = audit_chain

    async def dry_run(self, subject_user_id: UUID) -> CascadePlan:
        plans = [await adapter.dry_run(subject_user_id) for adapter in self.adapters]
        return CascadePlan(
            store_name="all",
            estimated_count=sum(plan.estimated_count for plan in plans),
            per_target_estimates={
                plan.store_name: plan.estimated_count
                for plan in plans
            },
        )

    async def run(
        self,
        dsr_id: UUID,
        subject_user_id: UUID,
        *,
        dry_run: bool = False,
    ) -> PrivacyDeletionTombstone | CascadePlan:
        if dry_run:
            plan = await self.dry_run(subject_user_id)
            return CascadePlan(
                store_name=str(dsr_id),
                estimated_count=plan.estimated_count,
                per_target_estimates=plan.per_target_estimates,
            )

        cascade_log: list[dict[str, Any]] = []
        entities_deleted: dict[str, int] = {}
        errors: list[str] = []
        for adapter in self.adapters:
            try:
                result = await adapter.execute(subject_user_id)
                cascade_log.append(
                    {
                        "store_name": adapter.store_name,
                        "status": "success" if not result.errors else "partial",
                        "started_at_iso": result.started_at.isoformat(),
                        "completed_at_iso": result.completed_at.isoformat(),
                        "affected_count": result.affected_count,
                        "per_target_counts": result.per_target_counts,
                        "errors": result.errors,
                    }
                )
                entities_deleted[adapter.store_name] = result.affected_count
                errors.extend(result.errors)
            except Exception as exc:
                cascade_log.append(
                    {
                        "store_name": adapter.store_name,
                        "status": "failed",
                        "error": str(exc),
                    }
                )
                errors.append(f"{adapter.store_name}: {exc}")

        tombstone = await self._produce_tombstone(
            subject_user_id=subject_user_id,
            entities_deleted=entities_deleted,
            cascade_log=cascade_log,
        )
        if errors:
            raise CascadePartialFailure(tombstone, errors)
        return tombstone

    # ----- UPD-051 scope-level cascades -----------------------------------
    #
    # ``execute_workspace_cascade`` and ``execute_tenant_cascade`` are the
    # entrypoints used by the data_lifecycle BC's deletion path. They walk
    # the same ordered adapter list as the user-DSR cascade, but call the
    # scope-specific ``execute_for_workspace`` / ``execute_for_tenant``
    # methods on each adapter (CascadeAdapter base class).
    #
    # Adapters that have not yet implemented the scope-level method raise
    # ``NotImplementedError``; the orchestrator captures that as a
    # per-store error so the operator can see the gap, while letting the
    # remaining adapters complete.

    async def execute_workspace_cascade(
        self,
        workspace_id: UUID,
        *,
        requested_by_user_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Execute a workspace-scoped cascade across all adapters.

        Returns a structured dict of per-store results. Does NOT raise on
        per-adapter failures (the caller's deletion job records the
        partial state); raises only on orchestration-level failure.
        """

        return await self._execute_scope_cascade(
            scope_label=f"workspace:{workspace_id}",
            adapter_method_name="execute_for_workspace",
            scope_arg=workspace_id,
            requested_by_user_id=requested_by_user_id,
        )

    async def execute_tenant_cascade(
        self,
        tenant_id: UUID,
        *,
        requested_by_user_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Execute a tenant-scoped cascade across all adapters."""

        return await self._execute_scope_cascade(
            scope_label=f"tenant:{tenant_id}",
            adapter_method_name="execute_for_tenant",
            scope_arg=tenant_id,
            requested_by_user_id=requested_by_user_id,
        )

    async def _execute_scope_cascade(
        self,
        *,
        scope_label: str,
        adapter_method_name: str,
        scope_arg: UUID,
        requested_by_user_id: UUID | None,
    ) -> dict[str, Any]:
        cascade_started_at = datetime.now(UTC)
        cascade_log: list[dict[str, Any]] = []
        store_results: list[dict[str, Any]] = []
        errors: list[str] = []
        for adapter in self.adapters:
            method = getattr(adapter, adapter_method_name, None)
            if method is None:
                errors.append(
                    f"{adapter.store_name}: missing {adapter_method_name}"
                )
                store_results.append(
                    {"store": adapter.store_name, "status": "skipped", "rows_affected": 0}
                )
                continue
            try:
                result = await method(scope_arg)
                cascade_log.append(
                    {
                        "store_name": adapter.store_name,
                        "status": "success" if not result.errors else "partial",
                        "started_at_iso": result.started_at.isoformat(),
                        "completed_at_iso": result.completed_at.isoformat(),
                        "affected_count": result.affected_count,
                        "per_target_counts": result.per_target_counts,
                        "errors": result.errors,
                    }
                )
                store_results.append(
                    {
                        "store": adapter.store_name,
                        "status": "completed" if not result.errors else "partial",
                        "rows_affected": result.affected_count,
                    }
                )
                errors.extend(result.errors)
            except NotImplementedError as exc:
                cascade_log.append(
                    {
                        "store_name": adapter.store_name,
                        "status": "not_implemented",
                        "error": str(exc),
                    }
                )
                store_results.append(
                    {"store": adapter.store_name, "status": "skipped", "rows_affected": 0}
                )
                errors.append(f"{adapter.store_name}: {exc}")
            except Exception as exc:
                cascade_log.append(
                    {
                        "store_name": adapter.store_name,
                        "status": "failed",
                        "error": str(exc),
                    }
                )
                store_results.append(
                    {"store": adapter.store_name, "status": "failed", "rows_affected": 0}
                )
                errors.append(f"{adapter.store_name}: {exc}")

        cascade_completed_at = datetime.now(UTC)
        return {
            "scope_label": scope_label,
            "cascade_started_at": cascade_started_at,
            "cascade_completed_at": cascade_completed_at,
            "store_results": store_results,
            "cascade_log": cascade_log,
            "errors": errors,
            "requested_by_user_id": requested_by_user_id,
        }

    async def export_signed(self, tombstone_id: UUID) -> SignedTombstone:
        tombstone = await self.repository.get_tombstone(tombstone_id)
        if tombstone is None:
            raise TombstoneNotFoundError(tombstone_id)
        canonical_json = self._canonical_json_from_tombstone(tombstone)
        proof_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
        if proof_hash != tombstone.proof_hash:
            raise ValueError("tombstone integrity check failed")
        signature = await self.signer.sign(canonical_json.encode("utf-8"))
        return SignedTombstone(
            tombstone=canonical_json,
            key_version=await self.signer.current_key_version(),
            signature=base64.b64encode(signature).decode("ascii"),
            proof_hash=proof_hash,
        )

    async def _produce_tombstone(
        self,
        *,
        subject_user_id: UUID,
        entities_deleted: dict[str, int],
        cascade_log: list[dict[str, Any]],
    ) -> PrivacyDeletionTombstone:
        salt = await self.salt_provider.get_current_salt()
        salt_version = await self.salt_provider.get_current_version()
        subject_hash = hashlib.sha256(subject_user_id.bytes + salt).hexdigest()
        created_at = datetime.now(UTC)
        payload = _canonical_payload(
            subject_user_id_hash=subject_hash,
            salt_version=salt_version,
            entities_deleted=entities_deleted,
            cascade_log=cascade_log,
            created_at=created_at,
        )
        canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        proof_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
        tombstone = await self.repository.insert_tombstone(
            subject_user_id_hash=subject_hash,
            salt_version=salt_version,
            entities_deleted=payload["entities_deleted"],
            cascade_log=payload["cascade_log"],
            proof_hash=proof_hash,
            created_at=created_at,
        )
        await self._append_audit(tombstone.id, canonical_json.encode("utf-8"))
        return tombstone

    def _canonical_json_from_tombstone(self, tombstone: PrivacyDeletionTombstone) -> str:
        payload = _canonical_payload(
            subject_user_id_hash=tombstone.subject_user_id_hash,
            salt_version=tombstone.salt_version,
            entities_deleted=tombstone.entities_deleted,
            cascade_log=tombstone.cascade_log,
            created_at=tombstone.created_at,
        )
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    async def _append_audit(self, audit_event_id: UUID, canonical_payload: bytes) -> None:
        append = getattr(self.audit_chain, "append", None)
        if callable(append):
            await append(audit_event_id, "privacy_compliance", canonical_payload)


def _canonical_payload(
    *,
    subject_user_id_hash: str,
    salt_version: int,
    entities_deleted: dict[str, int],
    cascade_log: list[dict[str, Any]],
    created_at: datetime,
) -> dict[str, Any]:
    return {
        "subject_user_id_hash": subject_user_id_hash,
        "salt_version": salt_version,
        "entities_deleted": dict(sorted(entities_deleted.items())),
        "cascade_log": sorted(
            cascade_log,
            key=lambda item: str(item.get("started_at_iso", item.get("store_name", ""))),
        ),
        "created_at_iso": created_at.isoformat(),
    }
