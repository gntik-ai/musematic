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


def test_platform_settings_reads_e2e_mode_from_flat_environment(monkeypatch) -> None:
    monkeypatch.setenv("FEATURE_E2E_MODE", "true")

    settings = PlatformSettings()

    assert settings.feature_e2e_mode is True


def test_platform_settings_reads_api_governance_overrides(monkeypatch) -> None:
    monkeypatch.setenv("FEATURE_API_RATE_LIMITING", "false")
    monkeypatch.setenv("FEATURE_API_RATE_LIMITING_FAIL_OPEN", "true")
    monkeypatch.setenv("API_TIER_CACHE_TTL_SECONDS", "120")
    monkeypatch.setenv("API_PRINCIPAL_CACHE_TTL_SECONDS", "30")
    monkeypatch.setenv("API_ANONYMOUS_TIER_NAME", "public")
    monkeypatch.setenv("API_DEFAULT_TIER_NAME", "starter")

    settings = PlatformSettings()

    assert settings.api_governance.rate_limiting_enabled is False
    assert settings.api_governance.rate_limiting_fail_open is True
    assert settings.api_governance.tier_cache_ttl_seconds == 120
    assert settings.api_governance.principal_cache_ttl_seconds == 30
    assert settings.api_governance.anonymous_tier_name == "public"
    assert settings.api_governance.default_tier_name == "starter"


def test_platform_settings_reads_model_catalog_overrides(monkeypatch) -> None:
    monkeypatch.setenv("FEATURE_MODEL_ROUTER_ENABLED", "true")
    monkeypatch.setenv("MODEL_ROUTER_AUTO_DEPRECATION_INTERVAL_SECONDS", "600")
    monkeypatch.setenv("MODEL_ROUTER_DEFAULT_RECOVERY_WINDOW_SECONDS", "120")
    monkeypatch.setenv("MODEL_ROUTER_PRIMARY_TIMEOUT_SECONDS", "7.5")
    monkeypatch.setenv("MODEL_ROUTER_OPENAI_BASE_URL", "https://openai.example/v1/chat")
    monkeypatch.setenv("MODEL_ROUTER_ANTHROPIC_BASE_URL", "https://anthropic.example/v1/messages")
    monkeypatch.setenv("MODEL_ROUTER_GOOGLE_BASE_URL", "https://google.example/v1/models")
    monkeypatch.setenv("MODEL_ROUTER_MISTRAL_BASE_URL", "https://mistral.example/v1/chat")

    settings = PlatformSettings()

    assert settings.model_catalog.router_enabled is True
    assert settings.model_catalog.auto_deprecation_interval_seconds == 600
    assert settings.model_catalog.default_recovery_window_seconds == 120
    assert settings.model_catalog.router_primary_timeout_seconds == 7.5
    assert settings.model_catalog.openai_base_url == "https://openai.example/v1/chat"
    assert settings.model_catalog.anthropic_base_url == "https://anthropic.example/v1/messages"
    assert settings.model_catalog.google_base_url == "https://google.example/v1/models"
    assert settings.model_catalog.mistral_base_url == "https://mistral.example/v1/chat"
