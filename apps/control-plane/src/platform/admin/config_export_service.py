from __future__ import annotations

import hashlib
import io
import json
import tarfile
from dataclasses import dataclass
from platform.audit.service import AuditChainService
from platform.common.config import PlatformSettings
from typing import Literal
from uuid import UUID

import yaml

ConfigScope = Literal["platform", "tenant"]


@dataclass(frozen=True)
class ConfigBundle:
    bundle_bytes: bytes
    sha256_hex: str


class ConfigExportService:
    def __init__(self, settings: PlatformSettings, audit_chain: AuditChainService) -> None:
        self.settings = settings
        self.audit_chain = audit_chain

    async def export_config(
        self,
        scope: ConfigScope,
        tenant_id: UUID | None = None,
    ) -> tuple[bytes, str]:
        config = _redacted_config(scope, tenant_id)
        config_yaml = yaml.safe_dump(config, sort_keys=True).encode("utf-8")
        manifest = {
            "format": "musematic-admin-config-v1",
            "scope": scope,
            "tenant_id": None if tenant_id is None else str(tenant_id),
            "categories": sorted(config.keys()),
            "hashes": {"config.yaml": hashlib.sha256(config_yaml).hexdigest()},
            "source_public_key_hex": await self.audit_chain.get_public_verifying_key(),
        }
        manifest_bytes = json.dumps(
            manifest,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        signature = self.audit_chain.signing.sign(manifest_bytes)
        bundle = _tar_bundle(
            {
                "config.yaml": config_yaml,
                "manifest.json": manifest_bytes,
                "signature.bin": signature,
            }
        )
        return bundle, hashlib.sha256(bundle).hexdigest()


def _redacted_config(scope: ConfigScope, tenant_id: UUID | None) -> dict[str, object]:
    return {
        "settings": {"scope": scope, "tenant_id": None if tenant_id is None else str(tenant_id)},
        "policies": [],
        "quotas": [],
        "roles": [],
        "connectors": [],
        "feature_flags": [],
        "model_catalog": [],
    }


def _tar_bundle(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, payload in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()
