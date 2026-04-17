"""Secret generation and persistence helpers."""

from __future__ import annotations

import json
import secrets
import string
import subprocess
import tempfile
from pathlib import Path

import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import BaseModel

from platform_cli.config import SecretsConfig


class GeneratedSecrets(BaseModel):
    """All generated or provided secrets used during installation."""

    admin_password: str
    postgresql_password: str
    redis_password: str
    neo4j_password: str
    clickhouse_password: str
    opensearch_password: str
    minio_access_key: str
    minio_secret_key: str
    jwt_private_key_pem: str
    jwt_public_key_pem: str


def _generate_password() -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    required = [
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*()-_=+"),
    ]
    required.extend(secrets.choice(alphabet) for _ in range(28))
    secrets.SystemRandom().shuffle(required)
    return "".join(required)


def _generate_rsa_key_pair() -> tuple[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return private_pem, public_pem


def _derive_public_key(private_key_pem: str) -> str:
    private_key = serialization.load_pem_private_key(
        private_key_pem.encode("utf-8"),
        password=None,
    )
    public_key = private_key.public_key()
    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")


def generate_secrets(config: SecretsConfig) -> GeneratedSecrets:
    """Generate a complete secret bundle, preserving provided values."""

    private_key = config.jwt_private_key_pem
    public_key: str
    if private_key:
        public_key = _derive_public_key(private_key)
    else:
        private_key, public_key = _generate_rsa_key_pair()

    return GeneratedSecrets(
        admin_password=_generate_password(),
        postgresql_password=config.postgresql_password or _generate_password(),
        redis_password=config.redis_password or _generate_password(),
        neo4j_password=config.neo4j_password or _generate_password(),
        clickhouse_password=config.clickhouse_password or _generate_password(),
        opensearch_password=config.opensearch_password or _generate_password(),
        minio_access_key=config.minio_access_key or _generate_password(),
        minio_secret_key=config.minio_secret_key or _generate_password(),
        jwt_private_key_pem=private_key,
        jwt_public_key_pem=public_key,
    )


def store_secrets_kubernetes(secrets_bundle: GeneratedSecrets, namespace: str) -> None:
    """Persist the generated secrets as a Kubernetes Secret."""

    payload = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": "platform-generated-secrets",
            "namespace": namespace,
        },
        "type": "Opaque",
        "stringData": secrets_bundle.model_dump(),
    }
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".yaml", delete=False) as handle:
        yaml.safe_dump(payload, handle, sort_keys=True)
        manifest_path = Path(handle.name)
    try:
        subprocess.run(
            ["kubectl", "apply", "-f", str(manifest_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    finally:
        manifest_path.unlink(missing_ok=True)


def store_secrets_env_file(secrets_bundle: GeneratedSecrets, path: Path) -> Path:
    """Persist secrets as an env file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key.upper()}={value}" for key, value in secrets_bundle.model_dump().items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def store_secrets_local(secrets_bundle: GeneratedSecrets, data_dir: Path) -> Path:
    """Persist secrets to a local JSON file."""

    data_dir.mkdir(parents=True, exist_ok=True)
    secrets_path = data_dir / "generated-secrets.json"
    secrets_path.write_text(
        json.dumps(secrets_bundle.model_dump(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return secrets_path
