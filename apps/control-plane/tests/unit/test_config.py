from __future__ import annotations

from platform.common.config import PlatformSettings


def test_platform_settings_defaults() -> None:
    settings = PlatformSettings()

    assert settings.profile == "api"
    assert settings.db.pool_size == 20
    assert settings.redis.url.startswith("redis://")
    assert settings.kafka.brokers == "localhost:9092"
    assert settings.grpc.runtime_controller.endswith(":50051")


def test_platform_settings_reads_environment(monkeypatch) -> None:
    monkeypatch.setenv("POSTGRES_DSN", "postgresql+asyncpg://example/test")
    monkeypatch.setenv("REDIS_URL", "redis://cache:6379")
    monkeypatch.setenv("KAFKA_BROKERS", "kafka:9092")
    monkeypatch.setenv("AUTH_JWT_SECRET_KEY", "secret")
    monkeypatch.setenv("PLATFORM_PROFILE", "scheduler")

    settings = PlatformSettings()

    assert settings.db.dsn == "postgresql+asyncpg://example/test"
    assert settings.redis.url == "redis://cache:6379"
    assert settings.kafka.brokers == "kafka:9092"
    assert settings.auth.jwt_secret_key == "secret"
    assert settings.profile == "scheduler"


def test_platform_settings_accepts_flat_instantiation() -> None:
    settings = PlatformSettings(
        POSTGRES_DSN="postgresql+asyncpg://flat/test",
        QDRANT_URL="http://qdrant:7000",
        CLICKHOUSE_URL="http://clickhouse:8124",
        PLATFORM_PROFILE="worker",
    )

    assert settings.db.dsn == "postgresql+asyncpg://flat/test"
    assert settings.qdrant.host == "qdrant"
    assert settings.qdrant.port == 7000
    assert settings.clickhouse.host == "clickhouse"
    assert settings.clickhouse.port == 8124
    assert settings.profile == "worker"


def test_platform_settings_s3_aliases_and_precedence(monkeypatch) -> None:
    monkeypatch.setenv("MINIO_ENDPOINT", "http://legacy-minio:9000")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "legacy-access")
    monkeypatch.setenv("MINIO_SECRET_KEY", "legacy-secret")

    legacy = PlatformSettings()

    monkeypatch.setenv("S3_ENDPOINT_URL", "https://new-endpoint.example.com")
    monkeypatch.setenv("S3_ACCESS_KEY", "new-access")
    monkeypatch.setenv("S3_SECRET_KEY", "new-secret")
    monkeypatch.setenv("S3_REGION", "eu-central-1")
    monkeypatch.setenv("S3_BUCKET_PREFIX", "custom")
    monkeypatch.setenv("S3_USE_PATH_STYLE", "false")
    monkeypatch.setenv("S3_PROVIDER", "hetzner")

    settings = PlatformSettings()

    assert legacy.s3.endpoint_url == "http://legacy-minio:9000"
    assert legacy.s3.access_key == "legacy-access"
    assert legacy.s3.secret_key == "legacy-secret"
    assert settings.s3.endpoint_url == "https://new-endpoint.example.com"
    assert settings.s3.access_key == "new-access"
    assert settings.s3.secret_key == "new-secret"
    assert settings.s3.region == "eu-central-1"
    assert settings.s3.bucket_prefix == "custom"
    assert settings.s3.use_path_style is False
    assert settings.s3.provider == "hetzner"
    assert settings.S3_ENDPOINT_URL == "https://new-endpoint.example.com"
    assert settings.S3_BUCKET_DEAD_LETTERS == settings.connectors.dead_letter_bucket


def test_platform_settings_support_a2a_flat_keys_and_single_field_overrides() -> None:
    settings = PlatformSettings(
        A2A_PROTOCOL_VERSION="1.1",
        A2A_MAX_PAYLOAD_BYTES=2048,
        A2A_TASK_IDLE_TIMEOUT_MINUTES=45,
        A2A_DEFAULT_CARD_TTL_SECONDS=120,
        A2A_RATE_LIMIT_PER_PRINCIPAL_PER_MINUTE=5,
        FEATURE_GOAL_AUTO_COMPLETE=False,
    )

    assert settings.A2A_PROTOCOL_VERSION == "1.1"
    assert settings.A2A_MAX_PAYLOAD_BYTES == 2048
    assert settings.A2A_TASK_IDLE_TIMEOUT_MINUTES == 45
    assert settings.A2A_DEFAULT_CARD_TTL_SECONDS == 120
    assert settings.A2A_RATE_LIMIT_PER_PRINCIPAL_PER_MINUTE == 5
    assert settings.FEATURE_GOAL_AUTO_COMPLETE is False
