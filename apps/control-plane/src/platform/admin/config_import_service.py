from __future__ import annotations

import hashlib
import io
import json
import tarfile
from dataclasses import dataclass, field
from platform.admin.audit_utils import append_admin_audit
from platform.audit.service import AuditChainService
from typing import Any

import yaml


@dataclass(frozen=True)
class ResourceDiff:
    category: str
    operation: str
    before: object | None = None
    after: object | None = None


@dataclass(frozen=True)
class DiffPreview:
    valid_signature: bool
    bundle_hash: str
    diffs: list[ResourceDiff] = field(default_factory=list)


@dataclass(frozen=True)
class ImportResult:
    bundle_hash: str
    applied: bool
    changed_count: int


class ConfigImportService:
    def __init__(self, audit_chain: AuditChainService) -> None:
        self.audit_chain = audit_chain

    async def preview_import(self, bundle: bytes) -> DiffPreview:
        extracted = _extract_bundle(bundle)
        _verify_bundle(extracted, self.audit_chain)
        config = yaml.safe_load(extracted["config.yaml"]) or {}
        if not isinstance(config, dict):
            config = {}
        diffs = [
            ResourceDiff(category=str(category), operation="unchanged", after=value)
            for category, value in sorted(config.items())
        ]
        return DiffPreview(
            valid_signature=True,
            bundle_hash=hashlib.sha256(bundle).hexdigest(),
            diffs=diffs,
        )

    async def apply_import(
        self,
        bundle: bytes,
        confirmation_phrase: str,
        actor: dict[str, Any],
    ) -> ImportResult:
        if confirmation_phrase != "IMPORT CONFIG":
            raise ValueError("confirmation phrase must be IMPORT CONFIG")
        preview = await self.preview_import(bundle)
        await append_admin_audit(
            self.audit_chain,
            event_type="platform.config.imported",
            actor=actor,
            payload={"bundle_hash": preview.bundle_hash, "changed_count": len(preview.diffs)},
        )
        return ImportResult(
            bundle_hash=preview.bundle_hash,
            applied=True,
            changed_count=len(preview.diffs),
        )


def _extract_bundle(bundle: bytes) -> dict[str, bytes]:
    extracted: dict[str, bytes] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(bundle), mode="r:gz") as archive:
            for member in archive.getmembers():
                handle = archive.extractfile(member)
                if handle is not None:
                    extracted[member.name] = handle.read()
    except tarfile.TarError as exc:
        raise ValueError("config bundle is not a valid gzip tar archive") from exc
    required = {"config.yaml", "manifest.json", "signature.bin"}
    missing = required - set(extracted)
    if missing:
        raise ValueError(f"config bundle missing required member(s): {', '.join(sorted(missing))}")
    return extracted


def _verify_bundle(extracted: dict[str, bytes], audit_chain: AuditChainService) -> None:
    manifest = json.loads(extracted["manifest.json"].decode("utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("config bundle manifest is invalid")
    expected_hash = manifest.get("hashes", {}).get("config.yaml")
    actual_hash = hashlib.sha256(extracted["config.yaml"]).hexdigest()
    if expected_hash != actual_hash:
        raise ValueError("config bundle content hash does not match manifest")
    source_key = str(manifest.get("source_public_key_hex") or "")
    if not audit_chain.signing.verify(
        extracted["manifest.json"],
        extracted["signature.bin"],
        source_key,
    ):
        raise ValueError("Bundle signature does not verify; the bundle may have been tampered with")
