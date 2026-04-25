from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from platform.privacy_compliance.cascade_adapters.base import (
    STORE_ORDER,
    CascadeAdapter,
    CascadePlan,
    CascadeResult,
)
from platform.privacy_compliance.exceptions import CascadePartialFailure
from platform.privacy_compliance.services.cascade_orchestrator import CascadeOrchestrator
from types import SimpleNamespace
from uuid import UUID, uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


class MemoryTombstoneRepository:
    def __init__(self) -> None:
        self.tombstones: dict[UUID, SimpleNamespace] = {}

    async def insert_tombstone(self, **kwargs):
        tombstone = SimpleNamespace(id=uuid4(), **kwargs)
        self.tombstones[tombstone.id] = tombstone
        return tombstone

    async def get_tombstone(self, tombstone_id: UUID):
        return self.tombstones.get(tombstone_id)


class SaltProvider:
    async def get_current_salt(self) -> bytes:
        return b"integration-test-salt"

    async def get_current_version(self) -> int:
        return 1


class Ed25519Signer:
    def __init__(self) -> None:
        self.private_key = Ed25519PrivateKey.generate()

    async def sign(self, payload: bytes) -> bytes:
        return self.private_key.sign(payload)

    async def current_key_version(self) -> str:
        return "integration-test-key"

    def public_key_pem(self) -> str:
        return self.private_key.public_key().public_bytes(
            Encoding.PEM,
            PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")


class MemoryStoreAdapter(CascadeAdapter):
    def __init__(
        self,
        store_name: str,
        rows_by_user: dict[str, int],
        *,
        failure: str | None = None,
    ) -> None:
        self.store_name = store_name
        self.rows_by_user = rows_by_user
        self.failure = failure
        self.calls: list[UUID] = []

    async def dry_run(self, subject_user_id: UUID) -> CascadePlan:
        count = self.rows_by_user.get(str(subject_user_id), 0)
        return CascadePlan(self.store_name, count, {self.store_name: count})

    async def execute(self, subject_user_id: UUID) -> CascadeResult:
        self.calls.append(subject_user_id)
        if self.failure is not None:
            raise RuntimeError(self.failure)
        now = datetime.now(UTC)
        count = self.rows_by_user.pop(str(subject_user_id), 0)
        return CascadeResult(
            self.store_name,
            now,
            now,
            count,
            {f"{self.store_name}_records": count},
            [],
        )


@dataclass(frozen=True)
class DSRRun:
    status: str
    tombstone: SimpleNamespace
    failure_reason: str | None = None


def populated_stores(subject_user_id: UUID) -> dict[str, dict[str, int]]:
    return {
        store_name: {str(subject_user_id): index + 1}
        for index, store_name in enumerate(STORE_ORDER)
    }


def build_orchestrator(
    *,
    stores: dict[str, dict[str, int]],
    signer: Ed25519Signer | None = None,
    failures: dict[str, str] | None = None,
) -> tuple[CascadeOrchestrator, MemoryTombstoneRepository, list[MemoryStoreAdapter]]:
    repository = MemoryTombstoneRepository()
    adapters = [
        MemoryStoreAdapter(store_name, stores[store_name], failure=(failures or {}).get(store_name))
        for store_name in STORE_ORDER
    ]
    orchestrator = CascadeOrchestrator(
        repository=repository,
        adapters=adapters,
        signer=signer or Ed25519Signer(),
        salt_provider=SaltProvider(),
    )
    return orchestrator, repository, adapters


async def run_dsr(
    orchestrator: CascadeOrchestrator,
    *,
    dsr_id: UUID,
    subject_user_id: UUID,
) -> DSRRun:
    try:
        tombstone = await orchestrator.run(dsr_id, subject_user_id)
        return DSRRun("completed", tombstone)
    except CascadePartialFailure as exc:
        return DSRRun("failed", exc.tombstone, ";".join(exc.errors))
