from __future__ import annotations

import hashlib
import io
import json
import shutil
import stat
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from platform.common.config import PlatformSettings
from platform.common.config import settings as default_settings
from platform.registry.exceptions import PackageValidationError
from platform.registry.schemas import AgentManifest
from typing import Any

import yaml


@dataclass(slots=True)
class ValidationResult:
    sha256_digest: str
    manifest: AgentManifest
    temp_dir: Path


class PackageValidator:
    def __init__(self, settings: PlatformSettings | None = None) -> None:
        resolved = settings or default_settings
        self.settings = resolved
        self.max_size_bytes = resolved.registry.package_size_limit_bytes
        self.max_file_count = resolved.registry.max_file_count
        self.max_directory_depth = resolved.registry.max_directory_depth

    async def validate(self, package_bytes: bytes, filename: str) -> ValidationResult:
        self._validate_extension(filename)
        self._validate_size(package_bytes)

        temp_dir = Path(tempfile.mkdtemp(prefix="registry-package-"))
        try:
            self._extract_archive(package_bytes, filename, temp_dir)
            manifest_path = self._find_manifest_path(temp_dir)
            manifest = self._load_manifest(manifest_path)
            return ValidationResult(
                sha256_digest=hashlib.sha256(package_bytes).hexdigest(),
                manifest=manifest,
                temp_dir=temp_dir,
            )
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise

    def _validate_extension(self, filename: str) -> None:
        if filename.endswith((".tar.gz", ".zip")):
            return
        raise PackageValidationError(
            "unsupported_extension",
            "Package must be a .tar.gz or .zip archive",
        )

    def _validate_size(self, package_bytes: bytes) -> None:
        package_size = len(package_bytes)
        if package_size <= self.max_size_bytes:
            return
        size_mb = round(package_size / (1024 * 1024), 2)
        raise PackageValidationError(
            "size_limit",
            (
                "Package size "
                f"{size_mb} MB exceeds maximum of "
                f"{self.settings.registry.package_size_limit_mb} MB"
            ),
        )

    def _extract_archive(self, package_bytes: bytes, filename: str, temp_dir: Path) -> None:
        if filename.endswith(".tar.gz"):
            self._extract_tar(package_bytes, temp_dir)
            return
        self._extract_zip(package_bytes, temp_dir)

    def _extract_tar(self, package_bytes: bytes, temp_dir: Path) -> None:
        with tarfile.open(fileobj=io.BytesIO(package_bytes), mode="r:gz") as archive:
            members = archive.getmembers()
            self._validate_archive_members([member.name for member in members])
            for member in members:
                self._validate_member_path(temp_dir, member.name)
                if member.issym() or member.islnk():
                    raise PackageValidationError(
                        "symlink_rejected",
                        f"Package contains symlink entry: {member.name}",
                    )
            archive.extractall(path=temp_dir, filter="data")
        self._validate_extracted_tree(temp_dir)

    def _extract_zip(self, package_bytes: bytes, temp_dir: Path) -> None:
        with zipfile.ZipFile(io.BytesIO(package_bytes)) as archive:
            members = archive.infolist()
            self._validate_archive_members([member.filename for member in members])
            for member in members:
                self._validate_member_path(temp_dir, member.filename)
                mode = member.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise PackageValidationError(
                        "symlink_rejected",
                        f"Package contains symlink entry: {member.filename}",
                    )
            archive.extractall(temp_dir)
        self._validate_extracted_tree(temp_dir)

    def _validate_archive_members(self, members: list[str]) -> None:
        if len(members) > self.max_file_count:
            raise PackageValidationError(
                "file_count_limit",
                f"Package contains {len(members)} entries; maximum is {self.max_file_count}",
            )

    def _validate_member_path(self, temp_dir: Path, member_name: str) -> None:
        try:
            resolved = (temp_dir / member_name).resolve()
            resolved.relative_to(temp_dir.resolve())
        except ValueError as exc:
            raise PackageValidationError(
                "path_traversal",
                f"Package contains path traversal: {member_name}",
            ) from exc

        parts = [part for part in Path(member_name).parts if part not in {"", "."}]
        if len(parts) > self.max_directory_depth:
            raise PackageValidationError(
                "depth_limit",
                f"Package member exceeds directory depth limit: {member_name}",
            )

    def _validate_extracted_tree(self, temp_dir: Path) -> None:
        extracted_paths = list(temp_dir.rglob("*"))
        if len(extracted_paths) > self.max_file_count:
            raise PackageValidationError(
                "file_count_limit",
                (
                    f"Package contains {len(extracted_paths)} extracted entries; "
                    f"maximum is {self.max_file_count}"
                ),
            )
        for path in extracted_paths:
            if path.is_symlink():
                raise PackageValidationError(
                    "symlink_rejected",
                    f"Package contains symlink entry: {path.relative_to(temp_dir)}",
                )

    def _find_manifest_path(self, temp_dir: Path) -> Path:
        candidates = sorted(temp_dir.rglob("manifest.yaml")) + sorted(
            temp_dir.rglob("manifest.json")
        )
        if not candidates:
            raise PackageValidationError(
                "manifest_missing",
                "Package must contain manifest.yaml or manifest.json",
            )
        return candidates[0]

    def _load_manifest(self, manifest_path: Path) -> AgentManifest:
        try:
            contents = manifest_path.read_text(encoding="utf-8")
            raw_manifest = self._parse_manifest(contents, manifest_path)
            return AgentManifest.model_validate(raw_manifest)
        except PackageValidationError:
            raise
        except Exception as exc:
            raise PackageValidationError(
                "manifest_invalid",
                f"Failed to parse manifest: {exc}",
            ) from exc

    def _parse_manifest(self, contents: str, manifest_path: Path) -> dict[str, Any]:
        if manifest_path.suffix == ".json":
            payload = json.loads(contents)
        else:
            payload = yaml.safe_load(contents)
        if not isinstance(payload, dict):
            raise PackageValidationError(
                "manifest_invalid",
                "Manifest must be an object",
            )
        return payload
