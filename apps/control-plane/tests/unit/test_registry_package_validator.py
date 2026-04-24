from __future__ import annotations

import io
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path
from platform.common.config import PlatformSettings
from platform.registry.exceptions import PackageValidationError
from platform.registry.package_validator import PackageValidator

import pytest

from tests.registry_support import build_manifest_payload, build_tar_package, build_zip_package


@pytest.mark.asyncio
async def test_package_validator_accepts_valid_tar_yaml_package() -> None:
    validator = PackageValidator(PlatformSettings())
    package_bytes = build_tar_package()

    result = await validator.validate(package_bytes, "agent.tar.gz")

    try:
        assert result.manifest.local_name == "kyc-verifier"
        assert result.manifest.version == "1.0.0"
        assert result.sha256_digest
        assert result.temp_dir.exists()
    finally:
        shutil.rmtree(result.temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_package_validator_accepts_valid_zip_json_package() -> None:
    validator = PackageValidator(PlatformSettings())
    package_bytes = build_zip_package(
        manifest_name="manifest.json",
        manifest_payload=build_manifest_payload(local_name="ops-runner"),
    )

    result = await validator.validate(package_bytes, "agent.zip")

    try:
        assert result.manifest.local_name == "ops-runner"
        assert result.manifest.display_name == "KYC Verifier"
    finally:
        shutil.rmtree(result.temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_package_validator_rejects_path_traversal() -> None:
    validator = PackageValidator(PlatformSettings())
    package_bytes = build_tar_package(extra_files={"../../etc/passwd": b"x"})

    with pytest.raises(PackageValidationError) as exc_info:
        await validator.validate(package_bytes, "agent.tar.gz")

    assert exc_info.value.error_type == "path_traversal"


@pytest.mark.asyncio
async def test_package_validator_rejects_symlinks() -> None:
    validator = PackageValidator(PlatformSettings())
    package_bytes = build_zip_package(symlink_target="../../etc/passwd")

    with pytest.raises(PackageValidationError) as exc_info:
        await validator.validate(package_bytes, "agent.zip")

    assert exc_info.value.error_type == "symlink_rejected"


@pytest.mark.asyncio
async def test_package_validator_rejects_size_limit() -> None:
    settings = PlatformSettings(REGISTRY_PACKAGE_SIZE_LIMIT_MB=1)
    validator = PackageValidator(settings)
    package_bytes = b"x" * (2 * 1024 * 1024)

    with pytest.raises(PackageValidationError) as exc_info:
        await validator.validate(package_bytes, "agent.tar.gz")

    assert exc_info.value.error_type == "size_limit"


@pytest.mark.asyncio
async def test_package_validator_rejects_missing_required_manifest_field() -> None:
    validator = PackageValidator(PlatformSettings())
    package_bytes = build_tar_package(
        manifest_payload=build_manifest_payload(purpose="short")
    )

    with pytest.raises(PackageValidationError) as exc_info:
        await validator.validate(package_bytes, "agent.tar.gz")

    assert exc_info.value.error_type == "manifest_invalid"


@pytest.mark.asyncio
async def test_package_validator_rejects_custom_role_without_description() -> None:
    validator = PackageValidator(PlatformSettings())
    package_bytes = build_tar_package(
        manifest_name="manifest.json",
        manifest_payload={
            key: value
            for key, value in build_manifest_payload(role_types=["custom"]).items()
            if key != "custom_role_description"
        },
    )

    with pytest.raises(PackageValidationError) as exc_info:
        await validator.validate(package_bytes, "agent.tar.gz")

    assert exc_info.value.error_type == "manifest_invalid"


def test_package_validator_rejects_unsupported_extension() -> None:
    validator = PackageValidator(PlatformSettings())

    with pytest.raises(PackageValidationError) as exc_info:
        validator._validate_extension("agent.tgz")

    assert exc_info.value.error_type == "unsupported_extension"


def test_package_validator_rejects_tar_symlink_file_count_depth_and_missing_manifest() -> None:
    symlink_validator = PackageValidator(PlatformSettings())

    with pytest.raises(PackageValidationError) as symlink_exc:
        symlink_validator._extract_tar(
            build_tar_package(symlink_target="../../etc/passwd"),
            Path(tempfile.mkdtemp(prefix="registry-symlink-")),
        )
    assert symlink_exc.value.error_type == "symlink_rejected"

    validator = PackageValidator(
        PlatformSettings(REGISTRY_MAX_FILE_COUNT=1, REGISTRY_MAX_DIRECTORY_DEPTH=2)
    )
    with pytest.raises(PackageValidationError) as count_exc:
        validator._validate_archive_members(["a", "b"])
    assert count_exc.value.error_type == "file_count_limit"

    with pytest.raises(PackageValidationError) as depth_exc:
        validator._validate_member_path(Path.cwd(), "a/b/c/d.txt")
    assert depth_exc.value.error_type == "depth_limit"

    missing_dir = Path(tempfile.mkdtemp(prefix="registry-missing-"))
    try:
        with pytest.raises(PackageValidationError) as missing_exc:
            validator._find_manifest_path(missing_dir)
        assert missing_exc.value.error_type == "manifest_missing"
    finally:
        shutil.rmtree(missing_dir, ignore_errors=True)


def test_package_validator_rejects_extracted_symlink_and_non_object_manifest() -> None:
    validator = PackageValidator(PlatformSettings())
    temp_dir = Path(tempfile.mkdtemp(prefix="registry-tree-"))
    try:
        target = temp_dir / "payload.txt"
        target.write_text("payload", encoding="utf-8")
        (temp_dir / "link").symlink_to(target)
        with pytest.raises(PackageValidationError) as symlink_exc:
            validator._validate_extracted_tree(temp_dir)
        assert symlink_exc.value.error_type == "symlink_rejected"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    manifest_dir = Path(tempfile.mkdtemp(prefix="registry-manifest-"))
    manifest_path = manifest_dir / "manifest.json"
    manifest_path.write_text('["not", "an", "object"]', encoding="utf-8")
    try:
        with pytest.raises(PackageValidationError) as invalid_exc:
            validator._load_manifest(manifest_path)
        assert invalid_exc.value.error_type == "manifest_invalid"
    finally:
        shutil.rmtree(manifest_dir, ignore_errors=True)


def test_package_validator_rejects_unsupported_tar_entries() -> None:
    validator = PackageValidator(PlatformSettings())
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        character_device = tarfile.TarInfo(name="device")
        character_device.type = tarfile.CHRTYPE
        archive.addfile(character_device)

    temp_dir = Path(tempfile.mkdtemp(prefix="registry-special-"))
    try:
        with pytest.raises(PackageValidationError) as exc_info:
            validator._extract_tar(buffer.getvalue(), temp_dir)
        assert exc_info.value.error_type == "unsupported_archive_entry"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_package_validator_rejects_unsupported_zip_entries() -> None:
    validator = PackageValidator(PlatformSettings())
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        fifo = zipfile.ZipInfo("fifo")
        fifo.external_attr = (0o10000 | 0o644) << 16
        archive.writestr(fifo, "")

    temp_dir = Path(tempfile.mkdtemp(prefix="registry-special-zip-"))
    try:
        with pytest.raises(PackageValidationError) as exc_info:
            validator._extract_zip(buffer.getvalue(), temp_dir)
        assert exc_info.value.error_type == "unsupported_archive_entry"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
