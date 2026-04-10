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
