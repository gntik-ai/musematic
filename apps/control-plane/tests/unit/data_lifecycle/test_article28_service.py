"""Unit tests for Article28Service.

Asserts the composite ZIP layout matches FR-758.1: dpa, dpa_metadata,
sub_processors_snapshot, audit_chain_last_12_months, residency_config,
maintenance_history, manifest. The manifest carries SHA-256 hashes for
every other file.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from platform.data_lifecycle.services.article28_service import Article28Service


PDF_BYTES = b"%PDF-1.7\n%fake-clean\n%%EOF\n"


class _DPAStub:
    def __init__(self, *, version: str | None = "v1.0") -> None:
        self.version = version

    async def get_active(self, tenant_id):
        if self.version is None:
            return None
        return {
            "version": self.version,
            "signed_at": datetime.now(UTC).isoformat(),
            "sha256": hashlib.sha256(PDF_BYTES).hexdigest(),
            "vault_path": f"secret/data/musematic/test/tenants/acme/dpa/dpa-{self.version}.pdf",
        }

    async def download(self, *, tenant_id, version, actor_user_id):
        return PDF_BYTES


class _Result:
    def __init__(self, mapping=None, mappings=None) -> None:
        self._first = mapping
        self._all = mappings or []

    def mappings(self):
        return self

    def first(self):
        return self._first

    def all(self):
        return list(self._all)


class _SessionStub:
    """Returns deterministic rows per SQL fragment for the composer.

    The Article28Service issues four queries: sub_processors,
    audit_chain_entries, privacy_residency_configs, maintenance_windows.
    """

    def __init__(
        self,
        *,
        sub_processors=None,
        audit_rows=None,
        residency=None,
        maintenance=None,
    ) -> None:
        self.sub_processors = sub_processors or []
        self.audit_rows = audit_rows or []
        self.residency = residency
        self.maintenance = maintenance or []

    async def execute(self, sql_text, params=None):
        s = str(sql_text)
        if "FROM sub_processors" in s:
            return _Result(mappings=self.sub_processors)
        if "FROM audit_chain_entries" in s:
            return _Result(mappings=self.audit_rows)
        if "FROM privacy_residency_configs" in s:
            return _Result(mapping=self.residency)
        if "FROM maintenance_windows" in s:
            return _Result(mappings=self.maintenance)
        return _Result()


@pytest.mark.asyncio
async def test_evidence_zip_contains_all_required_files() -> None:
    session = _SessionStub(
        sub_processors=[
            {
                "name": "Anthropic, PBC",
                "category": "LLM provider",
                "location": "USA",
                "data_categories": ["prompts"],
                "privacy_policy_url": "https://example",
                "dpa_url": None,
                "started_using_at": date(2024, 9, 1),
            }
        ],
        audit_rows=[
            {
                "id": "abc",
                "event_type": "auth.login_succeeded",
                "actor_user_id": "11111111-1111-1111-1111-111111111111",
                "chain_hash": b"\x01\x02",
                "prior_hash": b"\x00",
                "created_at": datetime.now(UTC),
            }
        ],
        residency={"region": "eu-central", "allowed_regions": ["eu-central", "eu-west"], "denied_regions": [], "updated_at": datetime.now(UTC)},
        maintenance=[
            {
                "id": "00000000-0000-0000-0000-000000000001",
                "scope_type": "tenant",
                "scope_id": "00000000-0000-0000-0000-000000000aaa",
                "reason": "scheduled-upgrade",
                "scheduled_for": datetime.now(UTC),
                "completed_at": datetime.now(UTC),
                "created_at": datetime.now(UTC),
            }
        ],
    )
    service = Article28Service(session=session, dpa_service=_DPAStub())
    tenant_id = UUID("00000000-0000-0000-0000-000000000aaa")

    zip_bytes = await service.build_evidence_zip(
        tenant_id=tenant_id, actor_user_id=uuid4()
    )

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
        assert "dpa-v1.0.pdf" in names
        assert "dpa_metadata.json" in names
        assert "sub_processors_snapshot.json" in names
        assert "audit_chain_last_12_months.jsonl" in names
        assert "residency_config.json" in names
        assert "maintenance_history.json" in names
        assert "manifest.json" in names

        # Manifest includes hashes for every other file.
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["tenant_id"] == str(tenant_id)
        files_section = manifest["files"]
        for required in (
            "dpa-v1.0.pdf",
            "dpa_metadata.json",
            "sub_processors_snapshot.json",
            "audit_chain_last_12_months.jsonl",
            "residency_config.json",
            "maintenance_history.json",
        ):
            assert required in files_section, f"manifest missing {required}"
            # Hash matches actual zip content.
            actual = hashlib.sha256(zf.read(required)).hexdigest()
            assert files_section[required] == actual, f"hash mismatch on {required}"


@pytest.mark.asyncio
async def test_evidence_zip_handles_missing_dpa_gracefully() -> None:
    session = _SessionStub()
    service = Article28Service(session=session, dpa_service=_DPAStub(version=None))
    zip_bytes = await service.build_evidence_zip(
        tenant_id=uuid4(), actor_user_id=uuid4()
    )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
        # No DPA pdf or metadata when version is None.
        assert "dpa-v1.0.pdf" not in names
        # All other components still present.
        assert "manifest.json" in names
        assert "sub_processors_snapshot.json" in names


@pytest.mark.asyncio
async def test_manifest_orders_files_deterministically() -> None:
    session = _SessionStub()
    service = Article28Service(session=session, dpa_service=_DPAStub(version=None))
    zip_bytes = await service.build_evidence_zip(
        tenant_id=uuid4(), actor_user_id=uuid4()
    )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    files = list(manifest["files"].keys())
    assert files == sorted(files)
