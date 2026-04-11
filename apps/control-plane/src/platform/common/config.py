from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="POSTGRES_", extra="ignore")

    dsn: str = "postgresql+asyncpg://musematic:musematic@localhost:5432/musematic"
    pool_size: int = 20
    max_overflow: int = 10


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REDIS_", extra="ignore")

    url: str = "redis://localhost:6379"
    nodes: list[str] = Field(default_factory=list)
    password: str = ""
    test_mode: str = "standalone"


class KafkaSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KAFKA_", extra="ignore")

    brokers: str = "localhost:9092"
    consumer_group: str = "platform"


class QdrantSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="QDRANT_", extra="ignore")

    host: str = "localhost"
    port: int = 6333
    grpc_port: int = 6334
    api_key: str = ""
    collection_dimensions: int = 768

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


class Neo4jSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NEO4J_", extra="ignore")

    uri: str = "bolt://localhost:7687"
    user: str = "neo4j"
    password: str = "neo4j"
    max_connection_pool_size: int = 50
    graph_mode: str = "auto"


class ClickHouseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CLICKHOUSE_", extra="ignore")

    host: str = "localhost"
    port: int = 8123
    user: str = "default"
    password: str = ""
    database: str = "default"
    insert_batch_size: int = 1000
    insert_flush_interval: float = 5.0

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


class OpenSearchSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPENSEARCH_", extra="ignore")

    hosts: str = "http://localhost:9200"
    username: str = ""
    password: str = ""
    use_ssl: bool = False
    verify_certs: bool = False
    ca_certs: str | None = None
    timeout: int = 30


class MinIOSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MINIO_", extra="ignore")

    endpoint: str = "http://localhost:9000"
    access_key: str = "minioadmin"
    secret_key: str = "minioadmin"
    default_bucket: str = "platform-artifacts"
    use_ssl: bool = False


class GRPCSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GRPC_", extra="ignore")

    runtime_controller: str = "localhost:50051"
    reasoning_engine: str = "localhost:50052"
    sandbox_manager: str = "localhost:50053"
    simulation_controller: str = "localhost:50055"


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUTH_", extra="ignore")

    jwt_secret_key: str = ""
    jwt_private_key: str = ""
    jwt_public_key: str = ""
    jwt_algorithm: str = "RS256"
    access_token_ttl: int = 900
    refresh_token_ttl: int = 604800
    lockout_threshold: int = 5
    lockout_duration: int = 900
    mfa_encryption_key: str = ""
    mfa_enrollment_ttl: int = 600
    session_ttl: int = 604800
    password_reset_ttl: int = 3600

    @property
    def signing_key(self) -> str:
        if self.jwt_private_key:
            return self.jwt_private_key
        if self.jwt_secret_key:
            return self.jwt_secret_key
        return ""

    @property
    def verification_key(self) -> str:
        if self.jwt_public_key:
            return self.jwt_public_key
        if self.jwt_secret_key:
            return self.jwt_secret_key
        if self.jwt_private_key:
            return self.jwt_private_key
        return ""

    @property
    def session_ttl_seconds(self) -> int:
        return self.session_ttl


class OTelSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OTEL_", extra="ignore")

    exporter_endpoint: str = ""
    service_name: str = "musematic-control-plane"


class AccountsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ACCOUNTS_", extra="ignore")

    signup_mode: Literal["open", "invite_only", "admin_approval"] = "open"
    email_verify_ttl_hours: int = 24
    invite_ttl_days: int = 7
    resend_rate_limit: int = 3


class WorkspacesSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WORKSPACES_", extra="ignore")

    default_name_template: str = "{display_name}'s Workspace"
    default_limit: int = 0


class WsHubSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WS_", extra="ignore")

    client_buffer_size: int = 1000
    heartbeat_interval_seconds: int = 30
    heartbeat_timeout_seconds: int = 10
    max_malformed_messages: int = 10


class PlatformSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PLATFORM_", extra="ignore")

    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    kafka: KafkaSettings = Field(default_factory=KafkaSettings)
    qdrant: QdrantSettings = Field(default_factory=QdrantSettings)
    neo4j: Neo4jSettings = Field(default_factory=Neo4jSettings)
    clickhouse: ClickHouseSettings = Field(default_factory=ClickHouseSettings)
    opensearch: OpenSearchSettings = Field(default_factory=OpenSearchSettings)
    minio: MinIOSettings = Field(default_factory=MinIOSettings)
    grpc: GRPCSettings = Field(default_factory=GRPCSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    otel: OTelSettings = Field(default_factory=OTelSettings)
    accounts: AccountsSettings = Field(default_factory=AccountsSettings)
    workspaces: WorkspacesSettings = Field(default_factory=WorkspacesSettings)
    ws_hub: WsHubSettings = Field(default_factory=WsHubSettings)
    profile: str = "api"

    @model_validator(mode="before")
    @classmethod
    def _expand_flat_settings(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        values = dict(data)
        mappings = {
            "POSTGRES_DSN": ("db", "dsn"),
            "POSTGRES_POOL_SIZE": ("db", "pool_size"),
            "POSTGRES_MAX_OVERFLOW": ("db", "max_overflow"),
            "REDIS_URL": ("redis", "url"),
            "REDIS_NODES": ("redis", "nodes"),
            "REDIS_PASSWORD": ("redis", "password"),
            "REDIS_TEST_MODE": ("redis", "test_mode"),
            "KAFKA_BROKERS": ("kafka", "brokers"),
            "KAFKA_CONSUMER_GROUP": ("kafka", "consumer_group"),
            "KAFKA_CONSUMER_GROUP_ID": ("kafka", "consumer_group"),
            "QDRANT_HOST": ("qdrant", "host"),
            "QDRANT_PORT": ("qdrant", "port"),
            "QDRANT_GRPC_PORT": ("qdrant", "grpc_port"),
            "QDRANT_API_KEY": ("qdrant", "api_key"),
            "QDRANT_COLLECTION_DIMENSIONS": ("qdrant", "collection_dimensions"),
            "QDRANT_URL": ("qdrant", "host"),
            "NEO4J_URI": ("neo4j", "uri"),
            "NEO4J_URL": ("neo4j", "uri"),
            "NEO4J_USER": ("neo4j", "user"),
            "NEO4J_PASSWORD": ("neo4j", "password"),
            "NEO4J_MAX_CONNECTION_POOL_SIZE": ("neo4j", "max_connection_pool_size"),
            "GRAPH_MODE": ("neo4j", "graph_mode"),
            "CLICKHOUSE_HOST": ("clickhouse", "host"),
            "CLICKHOUSE_PORT": ("clickhouse", "port"),
            "CLICKHOUSE_USER": ("clickhouse", "user"),
            "CLICKHOUSE_PASSWORD": ("clickhouse", "password"),
            "CLICKHOUSE_DATABASE": ("clickhouse", "database"),
            "CLICKHOUSE_INSERT_BATCH_SIZE": ("clickhouse", "insert_batch_size"),
            "CLICKHOUSE_INSERT_FLUSH_INTERVAL": ("clickhouse", "insert_flush_interval"),
            "CLICKHOUSE_URL": ("clickhouse", "host"),
            "OPENSEARCH_HOSTS": ("opensearch", "hosts"),
            "OPENSEARCH_USERNAME": ("opensearch", "username"),
            "OPENSEARCH_PASSWORD": ("opensearch", "password"),
            "OPENSEARCH_USE_SSL": ("opensearch", "use_ssl"),
            "OPENSEARCH_VERIFY_CERTS": ("opensearch", "verify_certs"),
            "OPENSEARCH_CA_CERTS": ("opensearch", "ca_certs"),
            "OPENSEARCH_TIMEOUT": ("opensearch", "timeout"),
            "MINIO_ENDPOINT": ("minio", "endpoint"),
            "MINIO_ACCESS_KEY": ("minio", "access_key"),
            "MINIO_SECRET_KEY": ("minio", "secret_key"),
            "MINIO_DEFAULT_BUCKET": ("minio", "default_bucket"),
            "MINIO_USE_SSL": ("minio", "use_ssl"),
            "GRPC_RUNTIME_CONTROLLER": ("grpc", "runtime_controller"),
            "GRPC_REASONING_ENGINE": ("grpc", "reasoning_engine"),
            "GRPC_SANDBOX_MANAGER": ("grpc", "sandbox_manager"),
            "GRPC_SIMULATION_CONTROLLER": ("grpc", "simulation_controller"),
            "AUTH_JWT_SECRET_KEY": ("auth", "jwt_secret_key"),
            "AUTH_JWT_PRIVATE_KEY": ("auth", "jwt_private_key"),
            "AUTH_JWT_PUBLIC_KEY": ("auth", "jwt_public_key"),
            "AUTH_JWT_ALGORITHM": ("auth", "jwt_algorithm"),
            "AUTH_ACCESS_TOKEN_TTL": ("auth", "access_token_ttl"),
            "AUTH_REFRESH_TOKEN_TTL": ("auth", "refresh_token_ttl"),
            "AUTH_LOCKOUT_THRESHOLD": ("auth", "lockout_threshold"),
            "AUTH_LOCKOUT_DURATION": ("auth", "lockout_duration"),
            "AUTH_MFA_ENCRYPTION_KEY": ("auth", "mfa_encryption_key"),
            "AUTH_MFA_ENROLLMENT_TTL": ("auth", "mfa_enrollment_ttl"),
            "AUTH_SESSION_TTL": ("auth", "session_ttl"),
            "AUTH_SESSION_TTL_SECONDS": ("auth", "session_ttl"),
            "AUTH_PASSWORD_RESET_TTL": ("auth", "password_reset_ttl"),
            "OTEL_EXPORTER_ENDPOINT": ("otel", "exporter_endpoint"),
            "OTEL_SERVICE_NAME": ("otel", "service_name"),
            "ACCOUNTS_SIGNUP_MODE": ("accounts", "signup_mode"),
            "ACCOUNTS_EMAIL_VERIFY_TTL_HOURS": ("accounts", "email_verify_ttl_hours"),
            "ACCOUNTS_INVITE_TTL_DAYS": ("accounts", "invite_ttl_days"),
            "ACCOUNTS_RESEND_RATE_LIMIT": ("accounts", "resend_rate_limit"),
            "WORKSPACES_DEFAULT_NAME_TEMPLATE": ("workspaces", "default_name_template"),
            "WORKSPACES_DEFAULT_LIMIT": ("workspaces", "default_limit"),
            "WS_CLIENT_BUFFER_SIZE": ("ws_hub", "client_buffer_size"),
            "WS_HEARTBEAT_INTERVAL_SECONDS": ("ws_hub", "heartbeat_interval_seconds"),
            "WS_HEARTBEAT_TIMEOUT_SECONDS": ("ws_hub", "heartbeat_timeout_seconds"),
            "WS_MAX_MALFORMED_MESSAGES": ("ws_hub", "max_malformed_messages"),
            "PLATFORM_PROFILE": ("profile", ""),
        }
        for key, target in mappings.items():
            if key not in values:
                continue
            section, field = target
            value = values.pop(key)
            if section == "profile":
                values["profile"] = value
                continue
            nested = dict(values.get(section, {}))
            if key == "QDRANT_URL" and isinstance(value, str):
                stripped = value.removeprefix("http://").removeprefix("https://")
                host, _, port = stripped.partition(":")
                nested["host"] = host
                if port:
                    nested["port"] = int(port)
            elif key == "CLICKHOUSE_URL" and isinstance(value, str):
                stripped = value.removeprefix("http://").removeprefix("https://")
                host, _, port = stripped.partition(":")
                nested["host"] = host
                if port:
                    nested["port"] = int(port)
            else:
                nested[field] = value
            values[section] = nested
        return values

    @property
    def PLATFORM_PROFILE(self) -> str:
        return self.profile

    @property
    def POSTGRES_DSN(self) -> str:
        return self.db.dsn

    @property
    def REDIS_URL(self) -> str:
        return self.redis.url

    @property
    def REDIS_NODES(self) -> list[str]:
        return self.redis.nodes

    @property
    def REDIS_PASSWORD(self) -> str:
        return self.redis.password

    @property
    def REDIS_TEST_MODE(self) -> str:
        return self.redis.test_mode

    @property
    def KAFKA_BROKERS(self) -> str:
        return self.kafka.brokers

    @property
    def KAFKA_BOOTSTRAP_SERVERS(self) -> str:
        return self.kafka.brokers

    @property
    def KAFKA_CONSUMER_GROUP_ID(self) -> str:
        return self.kafka.consumer_group

    @property
    def QDRANT_URL(self) -> str:
        return self.qdrant.url

    @property
    def QDRANT_API_KEY(self) -> str:
        return self.qdrant.api_key

    @property
    def QDRANT_GRPC_PORT(self) -> int:
        return self.qdrant.grpc_port

    @property
    def QDRANT_COLLECTION_DIMENSIONS(self) -> int:
        return self.qdrant.collection_dimensions

    @property
    def NEO4J_URL(self) -> str:
        return self.neo4j.uri

    @property
    def NEO4J_URI(self) -> str:
        return self.neo4j.uri

    @property
    def NEO4J_MAX_CONNECTION_POOL_SIZE(self) -> int:
        return self.neo4j.max_connection_pool_size

    @property
    def GRAPH_MODE(self) -> str:
        return self.neo4j.graph_mode

    @property
    def CLICKHOUSE_URL(self) -> str:
        return self.clickhouse.url

    @property
    def CLICKHOUSE_USER(self) -> str:
        return self.clickhouse.user

    @property
    def CLICKHOUSE_PASSWORD(self) -> str:
        return self.clickhouse.password

    @property
    def CLICKHOUSE_DATABASE(self) -> str:
        return self.clickhouse.database

    @property
    def CLICKHOUSE_INSERT_BATCH_SIZE(self) -> int:
        return self.clickhouse.insert_batch_size

    @property
    def CLICKHOUSE_INSERT_FLUSH_INTERVAL(self) -> float:
        return self.clickhouse.insert_flush_interval

    @property
    def OPENSEARCH_HOSTS(self) -> str:
        return self.opensearch.hosts

    @property
    def OPENSEARCH_USERNAME(self) -> str:
        return self.opensearch.username

    @property
    def OPENSEARCH_PASSWORD(self) -> str:
        return self.opensearch.password

    @property
    def OPENSEARCH_USE_SSL(self) -> bool:
        return self.opensearch.use_ssl

    @property
    def OPENSEARCH_VERIFY_CERTS(self) -> bool:
        return self.opensearch.verify_certs

    @property
    def OPENSEARCH_CA_CERTS(self) -> str | None:
        return self.opensearch.ca_certs

    @property
    def OPENSEARCH_TIMEOUT(self) -> int:
        return self.opensearch.timeout

    @property
    def MINIO_ENDPOINT(self) -> str:
        return self.minio.endpoint

    @property
    def MINIO_ACCESS_KEY(self) -> str:
        return self.minio.access_key

    @property
    def MINIO_SECRET_KEY(self) -> str:
        return self.minio.secret_key

    @property
    def MINIO_DEFAULT_BUCKET(self) -> str:
        return self.minio.default_bucket

    @property
    def MINIO_USE_SSL(self) -> bool:
        return self.minio.use_ssl

    @property
    def GRPC_RUNTIME_CONTROLLER(self) -> str:
        return self.grpc.runtime_controller

    @property
    def GRPC_REASONING_ENGINE(self) -> str:
        return self.grpc.reasoning_engine

    @property
    def GRPC_SANDBOX_MANAGER(self) -> str:
        return self.grpc.sandbox_manager

    @property
    def GRPC_SIMULATION_CONTROLLER(self) -> str:
        return self.grpc.simulation_controller

    @property
    def AUTH_JWT_SECRET_KEY(self) -> str:
        return self.auth.jwt_secret_key

    @property
    def AUTH_JWT_PRIVATE_KEY(self) -> str:
        return self.auth.jwt_private_key

    @property
    def AUTH_JWT_PUBLIC_KEY(self) -> str:
        return self.auth.jwt_public_key

    @property
    def AUTH_JWT_ALGORITHM(self) -> str:
        return self.auth.jwt_algorithm

    @property
    def AUTH_ACCESS_TOKEN_TTL(self) -> int:
        return self.auth.access_token_ttl

    @property
    def AUTH_REFRESH_TOKEN_TTL(self) -> int:
        return self.auth.refresh_token_ttl

    @property
    def AUTH_LOCKOUT_THRESHOLD(self) -> int:
        return self.auth.lockout_threshold

    @property
    def AUTH_LOCKOUT_DURATION(self) -> int:
        return self.auth.lockout_duration

    @property
    def AUTH_MFA_ENCRYPTION_KEY(self) -> str:
        return self.auth.mfa_encryption_key

    @property
    def AUTH_MFA_ENROLLMENT_TTL(self) -> int:
        return self.auth.mfa_enrollment_ttl

    @property
    def AUTH_SESSION_TTL(self) -> int:
        return self.auth.session_ttl

    @property
    def AUTH_SESSION_TTL_SECONDS(self) -> int:
        return self.auth.session_ttl

    @property
    def AUTH_PASSWORD_RESET_TTL(self) -> int:
        return self.auth.password_reset_ttl

    @property
    def OTEL_EXPORTER_ENDPOINT(self) -> str:
        return self.otel.exporter_endpoint

    @property
    def ACCOUNTS_SIGNUP_MODE(self) -> Literal["open", "invite_only", "admin_approval"]:
        return self.accounts.signup_mode

    @property
    def ACCOUNTS_EMAIL_VERIFY_TTL_HOURS(self) -> int:
        return self.accounts.email_verify_ttl_hours

    @property
    def ACCOUNTS_INVITE_TTL_DAYS(self) -> int:
        return self.accounts.invite_ttl_days

    @property
    def ACCOUNTS_RESEND_RATE_LIMIT(self) -> int:
        return self.accounts.resend_rate_limit

    @property
    def WORKSPACES_DEFAULT_NAME_TEMPLATE(self) -> str:
        return self.workspaces.default_name_template

    @property
    def WORKSPACES_DEFAULT_LIMIT(self) -> int:
        return self.workspaces.default_limit

    @property
    def WS_CLIENT_BUFFER_SIZE(self) -> int:
        return self.ws_hub.client_buffer_size

    @property
    def WS_HEARTBEAT_INTERVAL_SECONDS(self) -> int:
        return self.ws_hub.heartbeat_interval_seconds

    @property
    def WS_HEARTBEAT_TIMEOUT_SECONDS(self) -> int:
        return self.ws_hub.heartbeat_timeout_seconds

    @property
    def WS_MAX_MALFORMED_MESSAGES(self) -> int:
        return self.ws_hub.max_malformed_messages


Settings = PlatformSettings
settings = PlatformSettings()
