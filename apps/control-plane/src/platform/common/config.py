from __future__ import annotations

import os
import secrets
from typing import Any, Literal

from pydantic import AliasChoices, Field, model_validator
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


class ObjectStorageSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="S3_", extra="ignore", populate_by_name=True)

    endpoint_url: str = Field(
        default="", validation_alias=AliasChoices("S3_ENDPOINT_URL", "MINIO_ENDPOINT")
    )
    access_key: str = Field(
        default="minioadmin",
        validation_alias=AliasChoices("S3_ACCESS_KEY", "MINIO_ACCESS_KEY"),
    )
    secret_key: str = Field(
        default="minioadmin",
        validation_alias=AliasChoices("S3_SECRET_KEY", "MINIO_SECRET_KEY"),
    )
    region: str = Field(default="us-east-1", validation_alias="S3_REGION")
    bucket_prefix: str = Field(default="platform", validation_alias="S3_BUCKET_PREFIX")
    use_path_style: bool = Field(default=True, validation_alias="S3_USE_PATH_STYLE")
    provider: str = Field(default="generic", validation_alias="S3_PROVIDER")


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
    oauth_state_secret: str = Field(default_factory=lambda: secrets.token_hex(32))
    oauth_state_ttl: int = 600
    oauth_jwks_cache_ttl: int = 3600
    oauth_rate_limit_max: int = 10
    oauth_rate_limit_window: int = 60

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


class AnalyticsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ANALYTICS_", extra="ignore")

    budget_threshold_usd: float = 0.0


class VisibilitySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VISIBILITY_", extra="ignore")

    zero_trust_enabled: bool = False


class RegistrySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REGISTRY_", extra="ignore")

    package_bucket: str = "agent-packages"
    package_size_limit_mb: int = 50
    max_file_count: int = 256
    max_directory_depth: int = 10
    embedding_api_url: str = "http://localhost:8081/v1/embeddings"
    embedding_vector_size: int = 1536
    search_index: str = "marketplace-agents"
    search_backing_index: str = "marketplace-agents-000001"
    embeddings_collection: str = "agent_embeddings"
    reindex_poll_interval_seconds: int = 30

    @property
    def package_size_limit_bytes(self) -> int:
        return self.package_size_limit_mb * 1024 * 1024


class ContextEngineeringSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CONTEXT_ENGINEERING_", extra="ignore")

    bundle_bucket: str = "context-assembly-records"
    quality_scores_table: str = "context_quality_scores"
    policy_cache_ttl_seconds: int = 60
    drift_window_days: int = 7
    drift_recent_hours: int = 24
    drift_stddev_multiplier: float = 2.0
    drift_schedule_minutes: int = 5
    correlation_window_days: int = 30
    correlation_min_data_points: int = 30
    correlation_recompute_interval_hours: int = 24


class MemorySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MEMORY_", extra="ignore")

    embedding_dimensions: int = 1536
    embedding_api_url: str = "http://localhost:8081/v1/embeddings"
    embedding_model: str = "text-embedding-3-small"
    rate_limit_per_min: int = 60
    rate_limit_per_hour: int = 500
    contradiction_similarity_threshold: float = 0.90
    contradiction_edit_distance_threshold: float = 0.15
    consolidation_enabled: bool = True
    consolidation_interval_minutes: int = 15
    consolidation_cluster_threshold: float = 0.85
    consolidation_llm_enabled: bool = False
    consolidation_min_cluster_size: int = 3
    differential_privacy_enabled: bool = False
    differential_privacy_epsilon: float = 1.0
    rrf_k: int = 60
    session_cleaner_interval_minutes: int = 60
    recency_decay: float = 0.08


class InteractionsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="INTERACTIONS_", extra="ignore")

    max_messages_per_conversation: int = 10000
    default_page_size: int = 20
    goal_auto_complete_scan_interval_seconds: int = 60


class NotificationsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NOTIFICATIONS_", extra="ignore")

    rate_limit_per_source_per_minute: int = 20
    alert_retention_days: int = 90
    webhook_max_retries: int = 5
    retry_scan_interval_seconds: int = 30
    gc_interval_hours: int = 24


class GovernanceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GOVERNANCE_", extra="ignore")

    rate_limit_per_observer_per_minute: int = 100
    retention_days: int = 90
    gc_interval_hours: int = 24
    judge_timeout_seconds: int = 30


class EvaluationSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EVALUATION_", extra="ignore")

    llm_judge_api_url: str = ""
    llm_judge_model: str = "gpt-4"
    llm_judge_timeout_seconds: int = 30
    llm_judge_max_retries: int = 2
    trajectory_max_steps: int = 10000
    calibration_variance_envelope: float = 0.2


class ConnectorsSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CONNECTOR_",
        extra="ignore",
        populate_by_name=True,
    )

    ingress_topic: str = "connector.ingress"
    delivery_topic: str = "connector.delivery"
    dead_letter_bucket: str = Field(
        default="connector-dead-letters",
        validation_alias=AliasChoices(
            "CONNECTOR_DEAD_LETTER_BUCKET",
            "S3_BUCKET_DEAD_LETTERS",
            "MINIO_BUCKET_DEAD_LETTERS",
        ),
    )
    delivery_consumer_group: str = "connector-delivery-worker"
    retry_scan_interval_seconds: int = 30
    route_cache_ttl_seconds: int = 60
    max_payload_size_bytes: int = 1_048_576
    worker_enabled: bool = True
    delivery_max_concurrent: int = 10
    email_poll_interval_seconds: int = 60
    vault_mode: Literal["mock", "vault"] = "mock"
    vault_mock_secrets_file: str = ".vault-secrets.json"


class TrustSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TRUST_", extra="ignore")

    evidence_bucket: str = "trust-evidence"
    output_moderation_url: str = ""
    recertification_expiry_threshold_days: int = 30
    surveillance_warning_window_days: int = 7
    recertification_grace_period_days: int = 14
    attention_target_identity: str = "platform_admin"
    default_workspace_id: str = "00000000-0000-0000-0000-000000000000"


class AgentOpsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENTOPS_", extra="ignore")

    health_scoring_interval_minutes: int = 15
    default_min_sample_size: int = 50
    default_rolling_window_days: int = 30
    regression_significance_threshold: float = 0.05
    regression_normality_sample_min: int = 30
    canary_monitor_interval_minutes: int = 5
    canary_max_traffic_pct: int = 50
    retirement_grace_period_days: int = 14
    retirement_critical_intervals: int = 5
    recertification_grace_period_days: int = 7
    adaptation_proposal_ttl_hours: int = 168
    adaptation_rollback_retention_days: int = 30
    adaptation_observation_window_hours: int = 72
    adaptation_signal_poll_interval_minutes: int = 60
    adaptation_min_observations_per_dimension: int = 10
    adaptation_proficiency_dwell_time_hours: int = 24


class CompositionSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="COMPOSITION_", extra="ignore")

    llm_api_url: str = "http://localhost:8080/v1/chat/completions"
    llm_model: str = "claude-opus-4-6"
    llm_timeout_seconds: float = 25.0
    llm_max_retries: int = 2
    description_max_chars: int = 10000
    low_confidence_threshold: float = 0.5
    validation_timeout_seconds: float = 10.0


class DiscoverySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DISCOVERY_", extra="ignore")

    elo_k_factor: int = 32
    elo_default_score: float = 1000.0
    convergence_threshold: float = 0.05
    convergence_stable_rounds: int = 2
    max_cycles_default: int = 10
    min_hypotheses: int = 3
    proximity_clustering_threshold: float = 0.3
    proximity_over_explored_min_size: int = 5
    proximity_over_explored_similarity: float = 0.85
    proximity_gap_distance_threshold: float = 0.5
    proximity_graph_max_neighbors_per_node: int = 8
    proximity_graph_recompute_interval_minutes: int = 15
    proximity_graph_staleness_warning_minutes: int = 60
    proximity_bias_default_enabled: bool = True
    qdrant_collection: str = "discovery_hypotheses"
    embedding_vector_size: int = 1536
    experiment_sandbox_timeout_seconds: int = 120


class SimulationSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SIMULATION_", extra="ignore")

    max_duration_seconds: int = 1800
    behavioral_history_days: int = 30
    min_prediction_history_days: int = 7
    comparison_significance_alpha: float = 0.05
    default_strict_isolation: bool = True
    prediction_worker_interval_seconds: int = 30


class PlatformSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PLATFORM_",
        extra="ignore",
        populate_by_name=True,
    )

    FEATURE_GOAL_AUTO_COMPLETE: bool = False
    feature_e2e_mode: bool = Field(
        default=False,
        validation_alias=AliasChoices("FEATURE_E2E_MODE", "PLATFORM_FEATURE_E2E_MODE"),
    )
    A2A_PROTOCOL_VERSION: str = "1.0"
    A2A_MAX_PAYLOAD_BYTES: int = 10_485_760
    A2A_TASK_IDLE_TIMEOUT_MINUTES: int = 30
    A2A_DEFAULT_CARD_TTL_SECONDS: int = 3600
    A2A_RATE_LIMIT_PER_PRINCIPAL_PER_MINUTE: int = 60
    MCP_CATALOG_TTL_SECONDS: int = 3600
    MCP_MAX_PAYLOAD_BYTES: int = 10_485_760
    MCP_INVOCATION_TIMEOUT_SECONDS: int = 30
    MCP_RATE_LIMIT_PER_PRINCIPAL_PER_MINUTE: int = 60
    MCP_PROTOCOL_VERSION: str = "2024-11-05"

    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    kafka: KafkaSettings = Field(default_factory=KafkaSettings)
    qdrant: QdrantSettings = Field(default_factory=QdrantSettings)
    neo4j: Neo4jSettings = Field(default_factory=Neo4jSettings)
    clickhouse: ClickHouseSettings = Field(default_factory=ClickHouseSettings)
    opensearch: OpenSearchSettings = Field(default_factory=OpenSearchSettings)
    s3: ObjectStorageSettings = Field(default_factory=ObjectStorageSettings)
    grpc: GRPCSettings = Field(default_factory=GRPCSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    otel: OTelSettings = Field(default_factory=OTelSettings)
    accounts: AccountsSettings = Field(default_factory=AccountsSettings)
    workspaces: WorkspacesSettings = Field(default_factory=WorkspacesSettings)
    ws_hub: WsHubSettings = Field(default_factory=WsHubSettings)
    analytics: AnalyticsSettings = Field(default_factory=AnalyticsSettings)
    visibility: VisibilitySettings = Field(default_factory=VisibilitySettings)
    registry: RegistrySettings = Field(default_factory=RegistrySettings)
    context_engineering: ContextEngineeringSettings = Field(
        default_factory=ContextEngineeringSettings
    )
    memory: MemorySettings = Field(default_factory=MemorySettings)
    interactions: InteractionsSettings = Field(default_factory=InteractionsSettings)
    notifications: NotificationsSettings = Field(default_factory=NotificationsSettings)
    governance: GovernanceSettings = Field(default_factory=GovernanceSettings)
    evaluation: EvaluationSettings = Field(default_factory=EvaluationSettings)
    connectors: ConnectorsSettings = Field(default_factory=ConnectorsSettings)
    trust: TrustSettings = Field(default_factory=TrustSettings)
    agentops: AgentOpsSettings = Field(default_factory=AgentOpsSettings)
    composition: CompositionSettings = Field(default_factory=CompositionSettings)
    discovery: DiscoverySettings = Field(default_factory=DiscoverySettings)
    simulation: SimulationSettings = Field(default_factory=SimulationSettings)
    checkpoint_retention_days: int = 30
    checkpoint_max_size_bytes: int = 10_485_760
    profile: str = "api"

    @model_validator(mode="before")
    @classmethod
    def _expand_flat_settings(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        values = dict(data)
        if "feature_e2e_mode" not in values and "FEATURE_E2E_MODE" in os.environ:
            values["feature_e2e_mode"] = os.environ["FEATURE_E2E_MODE"]
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
            "S3_ENDPOINT_URL": ("s3", "endpoint_url"),
            "S3_ACCESS_KEY": ("s3", "access_key"),
            "S3_SECRET_KEY": ("s3", "secret_key"),
            "S3_REGION": ("s3", "region"),
            "S3_BUCKET_PREFIX": ("s3", "bucket_prefix"),
            "S3_USE_PATH_STYLE": ("s3", "use_path_style"),
            "S3_PROVIDER": ("s3", "provider"),
            "MINIO_ENDPOINT": ("s3", "endpoint_url"),
            "MINIO_ACCESS_KEY": ("s3", "access_key"),
            "MINIO_SECRET_KEY": ("s3", "secret_key"),
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
            "AUTH_OAUTH_STATE_SECRET": ("auth", "oauth_state_secret"),
            "AUTH_OAUTH_STATE_TTL": ("auth", "oauth_state_ttl"),
            "AUTH_OAUTH_JWKS_CACHE_TTL": ("auth", "oauth_jwks_cache_ttl"),
            "AUTH_OAUTH_RATE_LIMIT_MAX": ("auth", "oauth_rate_limit_max"),
            "AUTH_OAUTH_RATE_LIMIT_WINDOW": ("auth", "oauth_rate_limit_window"),
            "OTEL_EXPORTER_ENDPOINT": ("otel", "exporter_endpoint"),
            "OTEL_SERVICE_NAME": ("otel", "service_name"),
            "ACCOUNTS_SIGNUP_MODE": ("accounts", "signup_mode"),
            "ACCOUNTS_EMAIL_VERIFY_TTL_HOURS": ("accounts", "email_verify_ttl_hours"),
            "ACCOUNTS_INVITE_TTL_DAYS": ("accounts", "invite_ttl_days"),
            "ACCOUNTS_RESEND_RATE_LIMIT": ("accounts", "resend_rate_limit"),
            "WORKSPACES_DEFAULT_NAME_TEMPLATE": ("workspaces", "default_name_template"),
            "WORKSPACES_DEFAULT_LIMIT": ("workspaces", "default_limit"),
            "FEATURE_GOAL_AUTO_COMPLETE": ("FEATURE_GOAL_AUTO_COMPLETE",),
            "FEATURE_E2E_MODE": ("feature_e2e_mode",),
            "A2A_PROTOCOL_VERSION": ("A2A_PROTOCOL_VERSION",),
            "A2A_MAX_PAYLOAD_BYTES": ("A2A_MAX_PAYLOAD_BYTES",),
            "A2A_TASK_IDLE_TIMEOUT_MINUTES": ("A2A_TASK_IDLE_TIMEOUT_MINUTES",),
            "A2A_DEFAULT_CARD_TTL_SECONDS": ("A2A_DEFAULT_CARD_TTL_SECONDS",),
            "A2A_RATE_LIMIT_PER_PRINCIPAL_PER_MINUTE": ("A2A_RATE_LIMIT_PER_PRINCIPAL_PER_MINUTE",),
            "MCP_CATALOG_TTL_SECONDS": ("MCP_CATALOG_TTL_SECONDS",),
            "MCP_MAX_PAYLOAD_BYTES": ("MCP_MAX_PAYLOAD_BYTES",),
            "MCP_INVOCATION_TIMEOUT_SECONDS": ("MCP_INVOCATION_TIMEOUT_SECONDS",),
            "MCP_RATE_LIMIT_PER_PRINCIPAL_PER_MINUTE": ("MCP_RATE_LIMIT_PER_PRINCIPAL_PER_MINUTE",),
            "MCP_PROTOCOL_VERSION": ("MCP_PROTOCOL_VERSION",),
            "CHECKPOINT_RETENTION_DAYS": ("checkpoint_retention_days",),
            "CHECKPOINT_MAX_SIZE_BYTES": ("checkpoint_max_size_bytes",),
            "ANALYTICS_BUDGET_THRESHOLD_USD": ("analytics", "budget_threshold_usd"),
            "VISIBILITY_ZERO_TRUST_ENABLED": ("visibility", "zero_trust_enabled"),
            "REGISTRY_PACKAGE_BUCKET": ("registry", "package_bucket"),
            "REGISTRY_PACKAGE_SIZE_LIMIT_MB": ("registry", "package_size_limit_mb"),
            "REGISTRY_MAX_FILE_COUNT": ("registry", "max_file_count"),
            "REGISTRY_MAX_DIRECTORY_DEPTH": ("registry", "max_directory_depth"),
            "REGISTRY_EMBEDDING_API_URL": ("registry", "embedding_api_url"),
            "REGISTRY_EMBEDDING_VECTOR_SIZE": ("registry", "embedding_vector_size"),
            "REGISTRY_SEARCH_INDEX": ("registry", "search_index"),
            "REGISTRY_SEARCH_BACKING_INDEX": ("registry", "search_backing_index"),
            "REGISTRY_EMBEDDINGS_COLLECTION": ("registry", "embeddings_collection"),
            "REGISTRY_REINDEX_POLL_INTERVAL_SECONDS": (
                "registry",
                "reindex_poll_interval_seconds",
            ),
            "INTERACTIONS_GOAL_AUTO_COMPLETE_SCAN_INTERVAL_SECONDS": (
                "interactions",
                "goal_auto_complete_scan_interval_seconds",
            ),
            "CONTEXT_ENGINEERING_BUNDLE_BUCKET": (
                "context_engineering",
                "bundle_bucket",
            ),
            "CONTEXT_ENGINEERING_QUALITY_SCORES_TABLE": (
                "context_engineering",
                "quality_scores_table",
            ),
            "CONTEXT_ENGINEERING_POLICY_CACHE_TTL_SECONDS": (
                "context_engineering",
                "policy_cache_ttl_seconds",
            ),
            "CONTEXT_ENGINEERING_DRIFT_WINDOW_DAYS": (
                "context_engineering",
                "drift_window_days",
            ),
            "CONTEXT_ENGINEERING_DRIFT_RECENT_HOURS": (
                "context_engineering",
                "drift_recent_hours",
            ),
            "CONTEXT_ENGINEERING_DRIFT_STDDEV_MULTIPLIER": (
                "context_engineering",
                "drift_stddev_multiplier",
            ),
            "CONTEXT_ENGINEERING_DRIFT_SCHEDULE_MINUTES": (
                "context_engineering",
                "drift_schedule_minutes",
            ),
            "MEMORY_EMBEDDING_DIMENSIONS": ("memory", "embedding_dimensions"),
            "MEMORY_EMBEDDING_API_URL": ("memory", "embedding_api_url"),
            "MEMORY_EMBEDDING_MODEL": ("memory", "embedding_model"),
            "MEMORY_RATE_LIMIT_PER_MIN": ("memory", "rate_limit_per_min"),
            "MEMORY_RATE_LIMIT_PER_HOUR": ("memory", "rate_limit_per_hour"),
            "MEMORY_CONTRADICTION_SIMILARITY_THRESHOLD": (
                "memory",
                "contradiction_similarity_threshold",
            ),
            "MEMORY_CONTRADICTION_EDIT_DISTANCE_THRESHOLD": (
                "memory",
                "contradiction_edit_distance_threshold",
            ),
            "MEMORY_CONSOLIDATION_ENABLED": ("memory", "consolidation_enabled"),
            "MEMORY_CONSOLIDATION_INTERVAL_MINUTES": (
                "memory",
                "consolidation_interval_minutes",
            ),
            "MEMORY_CONSOLIDATION_CLUSTER_THRESHOLD": (
                "memory",
                "consolidation_cluster_threshold",
            ),
            "MEMORY_CONSOLIDATION_LLM_ENABLED": ("memory", "consolidation_llm_enabled"),
            "MEMORY_CONSOLIDATION_MIN_CLUSTER_SIZE": (
                "memory",
                "consolidation_min_cluster_size",
            ),
            "MEMORY_DIFFERENTIAL_PRIVACY_ENABLED": (
                "memory",
                "differential_privacy_enabled",
            ),
            "MEMORY_DIFFERENTIAL_PRIVACY_EPSILON": (
                "memory",
                "differential_privacy_epsilon",
            ),
            "MEMORY_RRF_K": ("memory", "rrf_k"),
            "MEMORY_SESSION_CLEANER_INTERVAL_MINUTES": (
                "memory",
                "session_cleaner_interval_minutes",
            ),
            "MEMORY_RECENCY_DECAY": ("memory", "recency_decay"),
            "INTERACTIONS_MAX_MESSAGES_PER_CONVERSATION": (
                "interactions",
                "max_messages_per_conversation",
            ),
            "INTERACTIONS_DEFAULT_PAGE_SIZE": ("interactions", "default_page_size"),
            "NOTIFICATIONS_RATE_LIMIT_PER_SOURCE_PER_MINUTE": (
                "notifications",
                "rate_limit_per_source_per_minute",
            ),
            "NOTIFICATIONS_ALERT_RETENTION_DAYS": (
                "notifications",
                "alert_retention_days",
            ),
            "NOTIFICATIONS_WEBHOOK_MAX_RETRIES": (
                "notifications",
                "webhook_max_retries",
            ),
            "NOTIFICATIONS_RETRY_SCAN_INTERVAL_SECONDS": (
                "notifications",
                "retry_scan_interval_seconds",
            ),
            "NOTIFICATIONS_GC_INTERVAL_HOURS": (
                "notifications",
                "gc_interval_hours",
            ),
            "GOVERNANCE_RATE_LIMIT_PER_OBSERVER_PER_MINUTE": (
                "governance",
                "rate_limit_per_observer_per_minute",
            ),
            "GOVERNANCE_RETENTION_DAYS": (
                "governance",
                "retention_days",
            ),
            "GOVERNANCE_GC_INTERVAL_HOURS": (
                "governance",
                "gc_interval_hours",
            ),
            "GOVERNANCE_JUDGE_TIMEOUT_SECONDS": (
                "governance",
                "judge_timeout_seconds",
            ),
            "EVALUATION_LLM_JUDGE_API_URL": ("evaluation", "llm_judge_api_url"),
            "EVALUATION_LLM_JUDGE_MODEL": ("evaluation", "llm_judge_model"),
            "EVALUATION_LLM_JUDGE_TIMEOUT_SECONDS": (
                "evaluation",
                "llm_judge_timeout_seconds",
            ),
            "EVALUATION_LLM_JUDGE_MAX_RETRIES": (
                "evaluation",
                "llm_judge_max_retries",
            ),
            "EVALUATION_TRAJECTORY_MAX_STEPS": (
                "evaluation",
                "trajectory_max_steps",
            ),
            "EVALUATION_CALIBRATION_VARIANCE_ENVELOPE": (
                "evaluation",
                "calibration_variance_envelope",
            ),
            "CONNECTOR_INGRESS_TOPIC": ("connectors", "ingress_topic"),
            "CONNECTOR_DELIVERY_TOPIC": ("connectors", "delivery_topic"),
            "S3_BUCKET_DEAD_LETTERS": ("connectors", "dead_letter_bucket"),
            "MINIO_BUCKET_DEAD_LETTERS": ("connectors", "dead_letter_bucket"),
            "CONNECTOR_DELIVERY_CONSUMER_GROUP": (
                "connectors",
                "delivery_consumer_group",
            ),
            "CONNECTOR_RETRY_SCAN_INTERVAL_SECONDS": (
                "connectors",
                "retry_scan_interval_seconds",
            ),
            "CONNECTOR_ROUTE_CACHE_TTL_SECONDS": (
                "connectors",
                "route_cache_ttl_seconds",
            ),
            "CONNECTOR_MAX_PAYLOAD_SIZE_BYTES": (
                "connectors",
                "max_payload_size_bytes",
            ),
            "CONNECTOR_WORKER_ENABLED": ("connectors", "worker_enabled"),
            "CONNECTOR_DELIVERY_MAX_CONCURRENT": (
                "connectors",
                "delivery_max_concurrent",
            ),
            "CONNECTOR_EMAIL_POLL_INTERVAL_SECONDS": (
                "connectors",
                "email_poll_interval_seconds",
            ),
            "EMAIL_POLL_INTERVAL_SECONDS": ("connectors", "email_poll_interval_seconds"),
            "VAULT_MODE": ("connectors", "vault_mode"),
            "VAULT_MOCK_SECRETS_FILE": ("connectors", "vault_mock_secrets_file"),
            "TRUST_EVIDENCE_BUCKET": ("trust", "evidence_bucket"),
            "TRUST_OUTPUT_MODERATION_URL": ("trust", "output_moderation_url"),
            "TRUST_RECERTIFICATION_EXPIRY_THRESHOLD_DAYS": (
                "trust",
                "recertification_expiry_threshold_days",
            ),
            "TRUST_SURVEILLANCE_WARNING_WINDOW_DAYS": (
                "trust",
                "surveillance_warning_window_days",
            ),
            "TRUST_RECERTIFICATION_GRACE_PERIOD_DAYS": (
                "trust",
                "recertification_grace_period_days",
            ),
            "TRUST_ATTENTION_TARGET_IDENTITY": ("trust", "attention_target_identity"),
            "TRUST_DEFAULT_WORKSPACE_ID": ("trust", "default_workspace_id"),
            "AGENTOPS_HEALTH_SCORING_INTERVAL_MINUTES": (
                "agentops",
                "health_scoring_interval_minutes",
            ),
            "AGENTOPS_DEFAULT_MIN_SAMPLE_SIZE": ("agentops", "default_min_sample_size"),
            "AGENTOPS_DEFAULT_ROLLING_WINDOW_DAYS": (
                "agentops",
                "default_rolling_window_days",
            ),
            "AGENTOPS_REGRESSION_SIGNIFICANCE_THRESHOLD": (
                "agentops",
                "regression_significance_threshold",
            ),
            "AGENTOPS_REGRESSION_NORMALITY_SAMPLE_MIN": (
                "agentops",
                "regression_normality_sample_min",
            ),
            "AGENTOPS_CANARY_MONITOR_INTERVAL_MINUTES": (
                "agentops",
                "canary_monitor_interval_minutes",
            ),
            "AGENTOPS_CANARY_MAX_TRAFFIC_PCT": ("agentops", "canary_max_traffic_pct"),
            "AGENTOPS_RETIREMENT_GRACE_PERIOD_DAYS": (
                "agentops",
                "retirement_grace_period_days",
            ),
            "AGENTOPS_RETIREMENT_CRITICAL_INTERVALS": (
                "agentops",
                "retirement_critical_intervals",
            ),
            "AGENTOPS_RECERTIFICATION_GRACE_PERIOD_DAYS": (
                "agentops",
                "recertification_grace_period_days",
            ),
            "COMPOSITION_LLM_API_URL": ("composition", "llm_api_url"),
            "COMPOSITION_LLM_MODEL": ("composition", "llm_model"),
            "COMPOSITION_LLM_TIMEOUT_SECONDS": (
                "composition",
                "llm_timeout_seconds",
            ),
            "COMPOSITION_LLM_MAX_RETRIES": ("composition", "llm_max_retries"),
            "COMPOSITION_DESCRIPTION_MAX_CHARS": (
                "composition",
                "description_max_chars",
            ),
            "COMPOSITION_LOW_CONFIDENCE_THRESHOLD": (
                "composition",
                "low_confidence_threshold",
            ),
            "COMPOSITION_VALIDATION_TIMEOUT_SECONDS": (
                "composition",
                "validation_timeout_seconds",
            ),
            "DISCOVERY_ELO_K_FACTOR": ("discovery", "elo_k_factor"),
            "DISCOVERY_ELO_DEFAULT_SCORE": ("discovery", "elo_default_score"),
            "DISCOVERY_CONVERGENCE_THRESHOLD": ("discovery", "convergence_threshold"),
            "DISCOVERY_CONVERGENCE_STABLE_ROUNDS": (
                "discovery",
                "convergence_stable_rounds",
            ),
            "DISCOVERY_MAX_CYCLES_DEFAULT": ("discovery", "max_cycles_default"),
            "DISCOVERY_MIN_HYPOTHESES": ("discovery", "min_hypotheses"),
            "DISCOVERY_PROXIMITY_CLUSTERING_THRESHOLD": (
                "discovery",
                "proximity_clustering_threshold",
            ),
            "DISCOVERY_PROXIMITY_OVER_EXPLORED_MIN_SIZE": (
                "discovery",
                "proximity_over_explored_min_size",
            ),
            "DISCOVERY_PROXIMITY_OVER_EXPLORED_SIMILARITY": (
                "discovery",
                "proximity_over_explored_similarity",
            ),
            "DISCOVERY_PROXIMITY_GAP_DISTANCE_THRESHOLD": (
                "discovery",
                "proximity_gap_distance_threshold",
            ),
            "DISCOVERY_QDRANT_COLLECTION": ("discovery", "qdrant_collection"),
            "DISCOVERY_EMBEDDING_VECTOR_SIZE": ("discovery", "embedding_vector_size"),
            "DISCOVERY_EXPERIMENT_SANDBOX_TIMEOUT_SECONDS": (
                "discovery",
                "experiment_sandbox_timeout_seconds",
            ),
            "SIMULATION_MAX_DURATION_SECONDS": ("simulation", "max_duration_seconds"),
            "SIMULATION_BEHAVIORAL_HISTORY_DAYS": (
                "simulation",
                "behavioral_history_days",
            ),
            "SIMULATION_MIN_PREDICTION_HISTORY_DAYS": (
                "simulation",
                "min_prediction_history_days",
            ),
            "SIMULATION_COMPARISON_SIGNIFICANCE_ALPHA": (
                "simulation",
                "comparison_significance_alpha",
            ),
            "SIMULATION_DEFAULT_STRICT_ISOLATION": (
                "simulation",
                "default_strict_isolation",
            ),
            "SIMULATION_PREDICTION_WORKER_INTERVAL_SECONDS": (
                "simulation",
                "prediction_worker_interval_seconds",
            ),
            "WS_CLIENT_BUFFER_SIZE": ("ws_hub", "client_buffer_size"),
            "WS_HEARTBEAT_INTERVAL_SECONDS": ("ws_hub", "heartbeat_interval_seconds"),
            "WS_HEARTBEAT_TIMEOUT_SECONDS": ("ws_hub", "heartbeat_timeout_seconds"),
            "WS_MAX_MALFORMED_MESSAGES": ("ws_hub", "max_malformed_messages"),
            "PLATFORM_PROFILE": ("profile", ""),
            "RUNTIME_PROFILE": ("profile", ""),
        }
        for key, target in mappings.items():
            if key not in values:
                continue
            value = values.pop(key)
            if len(target) == 1:
                values[target[0]] = value
                continue
            section, field = target
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
    def S3_ENDPOINT_URL(self) -> str:
        return self.s3.endpoint_url

    @property
    def S3_ACCESS_KEY(self) -> str:
        return self.s3.access_key

    @property
    def S3_SECRET_KEY(self) -> str:
        return self.s3.secret_key

    @property
    def S3_REGION(self) -> str:
        return self.s3.region

    @property
    def S3_BUCKET_PREFIX(self) -> str:
        return self.s3.bucket_prefix

    @property
    def S3_USE_PATH_STYLE(self) -> bool:
        return self.s3.use_path_style

    @property
    def S3_PROVIDER(self) -> str:
        return self.s3.provider

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
    def AUTH_OAUTH_STATE_SECRET(self) -> str:
        return self.auth.oauth_state_secret

    @property
    def AUTH_OAUTH_STATE_TTL(self) -> int:
        return self.auth.oauth_state_ttl

    @property
    def AUTH_OAUTH_JWKS_CACHE_TTL(self) -> int:
        return self.auth.oauth_jwks_cache_ttl

    @property
    def AUTH_OAUTH_RATE_LIMIT_MAX(self) -> int:
        return self.auth.oauth_rate_limit_max

    @property
    def AUTH_OAUTH_RATE_LIMIT_WINDOW(self) -> int:
        return self.auth.oauth_rate_limit_window

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
    def ANALYTICS_BUDGET_THRESHOLD_USD(self) -> float:
        return self.analytics.budget_threshold_usd

    @property
    def REGISTRY_PACKAGE_BUCKET(self) -> str:
        return self.registry.package_bucket

    @property
    def REGISTRY_PACKAGE_SIZE_LIMIT_MB(self) -> int:
        return self.registry.package_size_limit_mb

    @property
    def REGISTRY_MAX_FILE_COUNT(self) -> int:
        return self.registry.max_file_count

    @property
    def REGISTRY_MAX_DIRECTORY_DEPTH(self) -> int:
        return self.registry.max_directory_depth

    @property
    def REGISTRY_EMBEDDING_API_URL(self) -> str:
        return self.registry.embedding_api_url

    @property
    def REGISTRY_EMBEDDING_VECTOR_SIZE(self) -> int:
        return self.registry.embedding_vector_size

    @property
    def REGISTRY_SEARCH_INDEX(self) -> str:
        return self.registry.search_index

    @property
    def REGISTRY_SEARCH_BACKING_INDEX(self) -> str:
        return self.registry.search_backing_index

    @property
    def REGISTRY_EMBEDDINGS_COLLECTION(self) -> str:
        return self.registry.embeddings_collection

    @property
    def REGISTRY_REINDEX_POLL_INTERVAL_SECONDS(self) -> int:
        return self.registry.reindex_poll_interval_seconds

    @property
    def CONTEXT_ENGINEERING_BUNDLE_BUCKET(self) -> str:
        return self.context_engineering.bundle_bucket

    @property
    def CONTEXT_ENGINEERING_QUALITY_SCORES_TABLE(self) -> str:
        return self.context_engineering.quality_scores_table

    @property
    def CONTEXT_ENGINEERING_POLICY_CACHE_TTL_SECONDS(self) -> int:
        return self.context_engineering.policy_cache_ttl_seconds

    @property
    def CONTEXT_ENGINEERING_DRIFT_WINDOW_DAYS(self) -> int:
        return self.context_engineering.drift_window_days

    @property
    def CONTEXT_ENGINEERING_DRIFT_RECENT_HOURS(self) -> int:
        return self.context_engineering.drift_recent_hours

    @property
    def CONTEXT_ENGINEERING_DRIFT_STDDEV_MULTIPLIER(self) -> float:
        return self.context_engineering.drift_stddev_multiplier

    @property
    def CONTEXT_ENGINEERING_DRIFT_SCHEDULE_MINUTES(self) -> int:
        return self.context_engineering.drift_schedule_minutes

    @property
    def MEMORY_EMBEDDING_DIMENSIONS(self) -> int:
        return self.memory.embedding_dimensions

    @property
    def MEMORY_EMBEDDING_API_URL(self) -> str:
        return self.memory.embedding_api_url

    @property
    def MEMORY_EMBEDDING_MODEL(self) -> str:
        return self.memory.embedding_model

    @property
    def MEMORY_RATE_LIMIT_PER_MIN(self) -> int:
        return self.memory.rate_limit_per_min

    @property
    def MEMORY_RATE_LIMIT_PER_HOUR(self) -> int:
        return self.memory.rate_limit_per_hour

    @property
    def MEMORY_CONTRADICTION_SIMILARITY_THRESHOLD(self) -> float:
        return self.memory.contradiction_similarity_threshold

    @property
    def MEMORY_CONTRADICTION_EDIT_DISTANCE_THRESHOLD(self) -> float:
        return self.memory.contradiction_edit_distance_threshold

    @property
    def MEMORY_CONSOLIDATION_ENABLED(self) -> bool:
        return self.memory.consolidation_enabled

    @property
    def MEMORY_CONSOLIDATION_INTERVAL_MINUTES(self) -> int:
        return self.memory.consolidation_interval_minutes

    @property
    def MEMORY_CONSOLIDATION_CLUSTER_THRESHOLD(self) -> float:
        return self.memory.consolidation_cluster_threshold

    @property
    def MEMORY_CONSOLIDATION_LLM_ENABLED(self) -> bool:
        return self.memory.consolidation_llm_enabled

    @property
    def MEMORY_CONSOLIDATION_MIN_CLUSTER_SIZE(self) -> int:
        return self.memory.consolidation_min_cluster_size

    @property
    def MEMORY_DIFFERENTIAL_PRIVACY_ENABLED(self) -> bool:
        return self.memory.differential_privacy_enabled

    @property
    def MEMORY_DIFFERENTIAL_PRIVACY_EPSILON(self) -> float:
        return self.memory.differential_privacy_epsilon

    @property
    def MEMORY_RRF_K(self) -> int:
        return self.memory.rrf_k

    @property
    def MEMORY_SESSION_CLEANER_INTERVAL_MINUTES(self) -> int:
        return self.memory.session_cleaner_interval_minutes

    @property
    def MEMORY_RECENCY_DECAY(self) -> float:
        return self.memory.recency_decay

    @property
    def INTERACTIONS_MAX_MESSAGES_PER_CONVERSATION(self) -> int:
        return self.interactions.max_messages_per_conversation

    @property
    def INTERACTIONS_DEFAULT_PAGE_SIZE(self) -> int:
        return self.interactions.default_page_size

    @property
    def CONNECTOR_INGRESS_TOPIC(self) -> str:
        return self.connectors.ingress_topic

    @property
    def CONNECTOR_DELIVERY_TOPIC(self) -> str:
        return self.connectors.delivery_topic

    @property
    def S3_BUCKET_DEAD_LETTERS(self) -> str:
        return self.connectors.dead_letter_bucket

    @property
    def CONNECTOR_DELIVERY_CONSUMER_GROUP(self) -> str:
        return self.connectors.delivery_consumer_group

    @property
    def CONNECTOR_RETRY_SCAN_INTERVAL_SECONDS(self) -> int:
        return self.connectors.retry_scan_interval_seconds

    @property
    def CONNECTOR_ROUTE_CACHE_TTL_SECONDS(self) -> int:
        return self.connectors.route_cache_ttl_seconds

    @property
    def CONNECTOR_MAX_PAYLOAD_SIZE_BYTES(self) -> int:
        return self.connectors.max_payload_size_bytes

    @property
    def CONNECTOR_WORKER_ENABLED(self) -> bool:
        return self.connectors.worker_enabled

    @property
    def CONNECTOR_DELIVERY_MAX_CONCURRENT(self) -> int:
        return self.connectors.delivery_max_concurrent

    @property
    def CONNECTOR_EMAIL_POLL_INTERVAL_SECONDS(self) -> int:
        return self.connectors.email_poll_interval_seconds

    @property
    def VAULT_MODE(self) -> str:
        return self.connectors.vault_mode

    @property
    def VAULT_MOCK_SECRETS_FILE(self) -> str:
        return self.connectors.vault_mock_secrets_file

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

    @property
    def TRUST_EVIDENCE_BUCKET(self) -> str:
        return self.trust.evidence_bucket

    @property
    def TRUST_OUTPUT_MODERATION_URL(self) -> str:
        return self.trust.output_moderation_url

    @property
    def TRUST_RECERTIFICATION_EXPIRY_THRESHOLD_DAYS(self) -> int:
        return self.trust.recertification_expiry_threshold_days

    @property
    def TRUST_SURVEILLANCE_WARNING_WINDOW_DAYS(self) -> int:
        return self.trust.surveillance_warning_window_days

    @property
    def TRUST_RECERTIFICATION_GRACE_PERIOD_DAYS(self) -> int:
        return self.trust.recertification_grace_period_days

    @property
    def TRUST_ATTENTION_TARGET_IDENTITY(self) -> str:
        return self.trust.attention_target_identity

    @property
    def TRUST_DEFAULT_WORKSPACE_ID(self) -> str:
        return self.trust.default_workspace_id

    @property
    def AGENTOPS_HEALTH_SCORING_INTERVAL_MINUTES(self) -> int:
        return self.agentops.health_scoring_interval_minutes

    @property
    def AGENTOPS_DEFAULT_MIN_SAMPLE_SIZE(self) -> int:
        return self.agentops.default_min_sample_size

    @property
    def AGENTOPS_DEFAULT_ROLLING_WINDOW_DAYS(self) -> int:
        return self.agentops.default_rolling_window_days

    @property
    def AGENTOPS_REGRESSION_SIGNIFICANCE_THRESHOLD(self) -> float:
        return self.agentops.regression_significance_threshold

    @property
    def AGENTOPS_REGRESSION_NORMALITY_SAMPLE_MIN(self) -> int:
        return self.agentops.regression_normality_sample_min

    @property
    def AGENTOPS_CANARY_MONITOR_INTERVAL_MINUTES(self) -> int:
        return self.agentops.canary_monitor_interval_minutes

    @property
    def AGENTOPS_CANARY_MAX_TRAFFIC_PCT(self) -> int:
        return self.agentops.canary_max_traffic_pct

    @property
    def AGENTOPS_RETIREMENT_GRACE_PERIOD_DAYS(self) -> int:
        return self.agentops.retirement_grace_period_days

    @property
    def AGENTOPS_RETIREMENT_CRITICAL_INTERVALS(self) -> int:
        return self.agentops.retirement_critical_intervals

    @property
    def AGENTOPS_RECERTIFICATION_GRACE_PERIOD_DAYS(self) -> int:
        return self.agentops.recertification_grace_period_days

    @property
    def COMPOSITION_LLM_API_URL(self) -> str:
        return self.composition.llm_api_url

    @property
    def COMPOSITION_LLM_MODEL(self) -> str:
        return self.composition.llm_model

    @property
    def COMPOSITION_LLM_TIMEOUT_SECONDS(self) -> float:
        return self.composition.llm_timeout_seconds

    @property
    def COMPOSITION_LLM_MAX_RETRIES(self) -> int:
        return self.composition.llm_max_retries

    @property
    def COMPOSITION_DESCRIPTION_MAX_CHARS(self) -> int:
        return self.composition.description_max_chars

    @property
    def COMPOSITION_LOW_CONFIDENCE_THRESHOLD(self) -> float:
        return self.composition.low_confidence_threshold

    @property
    def COMPOSITION_VALIDATION_TIMEOUT_SECONDS(self) -> float:
        return self.composition.validation_timeout_seconds

    @property
    def DISCOVERY_ELO_K_FACTOR(self) -> int:
        return self.discovery.elo_k_factor

    @property
    def DISCOVERY_ELO_DEFAULT_SCORE(self) -> float:
        return self.discovery.elo_default_score

    @property
    def DISCOVERY_CONVERGENCE_THRESHOLD(self) -> float:
        return self.discovery.convergence_threshold

    @property
    def DISCOVERY_CONVERGENCE_STABLE_ROUNDS(self) -> int:
        return self.discovery.convergence_stable_rounds

    @property
    def DISCOVERY_MAX_CYCLES_DEFAULT(self) -> int:
        return self.discovery.max_cycles_default

    @property
    def DISCOVERY_MIN_HYPOTHESES(self) -> int:
        return self.discovery.min_hypotheses

    @property
    def DISCOVERY_PROXIMITY_CLUSTERING_THRESHOLD(self) -> float:
        return self.discovery.proximity_clustering_threshold

    @property
    def DISCOVERY_PROXIMITY_OVER_EXPLORED_MIN_SIZE(self) -> int:
        return self.discovery.proximity_over_explored_min_size

    @property
    def DISCOVERY_PROXIMITY_OVER_EXPLORED_SIMILARITY(self) -> float:
        return self.discovery.proximity_over_explored_similarity

    @property
    def DISCOVERY_PROXIMITY_GAP_DISTANCE_THRESHOLD(self) -> float:
        return self.discovery.proximity_gap_distance_threshold

    @property
    def DISCOVERY_QDRANT_COLLECTION(self) -> str:
        return self.discovery.qdrant_collection

    @property
    def DISCOVERY_EMBEDDING_VECTOR_SIZE(self) -> int:
        return self.discovery.embedding_vector_size

    @property
    def DISCOVERY_EXPERIMENT_SANDBOX_TIMEOUT_SECONDS(self) -> int:
        return self.discovery.experiment_sandbox_timeout_seconds

    @property
    def SIMULATION_MAX_DURATION_SECONDS(self) -> int:
        return self.simulation.max_duration_seconds

    @property
    def SIMULATION_BEHAVIORAL_HISTORY_DAYS(self) -> int:
        return self.simulation.behavioral_history_days

    @property
    def SIMULATION_MIN_PREDICTION_HISTORY_DAYS(self) -> int:
        return self.simulation.min_prediction_history_days

    @property
    def SIMULATION_COMPARISON_SIGNIFICANCE_ALPHA(self) -> float:
        return self.simulation.comparison_significance_alpha

    @property
    def SIMULATION_DEFAULT_STRICT_ISOLATION(self) -> bool:
        return self.simulation.default_strict_isolation

    @property
    def SIMULATION_PREDICTION_WORKER_INTERVAL_SECONDS(self) -> int:
        return self.simulation.prediction_worker_interval_seconds


Settings = PlatformSettings
settings = PlatformSettings()
