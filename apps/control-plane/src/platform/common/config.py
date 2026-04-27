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
    oauth_google_authorize_url: str = "https://accounts.google.com/o/oauth2/v2/auth"
    oauth_google_token_url: str = "https://oauth2.googleapis.com/token"
    oauth_google_token_info_url: str = "https://oauth2.googleapis.com/tokeninfo"
    oauth_github_authorize_url: str = "https://github.com/login/oauth/authorize"
    oauth_github_token_url: str = "https://github.com/login/oauth/access_token"
    oauth_github_user_url: str = "https://api.github.com/user"
    oauth_github_emails_url: str = "https://api.github.com/user/emails"
    oauth_github_teams_url: str = "https://api.github.com/user/teams"
    oauth_github_org_membership_url_template: str = (
        "https://api.github.com/user/memberships/orgs/{org}"
    )

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


class CostGovernanceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="COST_GOVERNANCE_", extra="ignore")

    anomaly_evaluation_interval_seconds: int = 3600
    forecast_evaluation_interval_seconds: int = 3600
    override_token_ttl_seconds: int = 300
    minimum_history_periods_for_forecast: int = 4
    default_alert_thresholds: list[int] = Field(default_factory=lambda: [50, 80, 100])
    default_currency: str = "USD"
    attribution_clickhouse_batch_size: int = 500
    attribution_clickhouse_flush_interval_seconds: float = 5.0
    compute_cost_per_ms_cents: float = 0.0
    storage_cost_per_byte_cents: float = 0.0
    overhead_cost_per_execution_cents: float = 0.0
    attribution_fail_open: bool = True


class MultiRegionOpsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MULTI_REGION_OPS_", extra="ignore")

    replication_probe_interval_seconds: int = 60
    replication_probe_request_timeout_seconds: float = 5.0
    rpo_alert_sustained_intervals: int = 3
    failover_lock_max_seconds: int = 3600
    capacity_projection_interval_seconds: int = 3600
    capacity_default_utilization_threshold: float = 0.8
    capacity_saturation_horizon_days: int = 7
    maintenance_announcement_lead_minutes: int = 60
    replication_status_retention_days: int = 730
    failover_plan_rehearsal_staleness_days: int = 90


class TaggingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TAGGING_", extra="ignore")

    label_expression_lru_size: int = 256
    label_expression_redis_ttl_seconds: int = 86_400
    cross_entity_search_max_visible_ids: int = 10_000
    saved_view_share_propagation_target_seconds: int = 5
    orphan_owner_resolution: str = "transfer_to_workspace_superadmin"


class IncidentResponseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="INCIDENT_RESPONSE_",
        extra="ignore",
        populate_by_name=True,
    )

    delivery_retry_initial_seconds: int = 30
    delivery_retry_max_attempts: int = 6
    delivery_retry_max_window_seconds: int = 86_400
    delivery_retry_scan_interval_seconds: int = 30
    runbook_freshness_window_days: int = 90
    timeline_max_window_hours: int = 24
    dedup_fingerprint_ttl_seconds: int = 86_400 * 30
    external_alert_request_timeout_seconds: float = 5.0
    postmortem_blob_threshold_bytes: int = 524_288
    postmortem_minio_bucket: str = "incident-response-postmortems"
    timeline_kafka_topics: list[str] = Field(
        default_factory=lambda: [
            "monitor.alerts",
            "governance.verdict.issued",
            "governance.enforcement.executed",
            "runtime.lifecycle",
            "auth.events",
            "policy.gate.blocked",
        ],
    )
    alert_rule_class_to_scenario: dict[str, str] = Field(
        default_factory=lambda: {
            "error_rate_spike": "pod_failure",
            "sla_breach": "runtime_pod_crash_loop",
            "certification_failure": "certificate_expiry",
            "security_event": "auth_service_degradation",
            "chaos_unexpected_behavior": "governance_verdict_storm",
            "kafka_lag": "kafka_lag",
            "model_provider_outage": "model_provider_outage",
            "database_connection_issue": "database_connection_issue",
            "s3_quota_breach": "s3_quota_breach",
            "reasoning_engine_oom": "reasoning_engine_oom",
        },
    )


class LocalizationSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LOCALIZATION_", extra="ignore")

    localization_locale_lru_size: int = 12
    localization_drift_threshold_days: int = 7
    localization_default_locale: str = "en"
    localization_supported_locales: list[str] = Field(
        default_factory=lambda: ["en", "es", "fr", "de", "ja", "zh-CN"]
    )
    localization_translation_vendor: str = "lokalise"
    localization_default_data_export_format: str = "json"


class VisibilitySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VISIBILITY_", extra="ignore")

    zero_trust_enabled: bool = False


class PrivacyComplianceSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)

    dsr_enabled: bool = Field(
        default=False,
        description="Enables data-subject request endpoints and workers.",
        validation_alias="FEATURE_PRIVACY_DSR_ENABLED",
    )
    erasure_hold_hours_default: int = Field(
        default=0,
        description="Default hold window in hours before erasure cascades begin.",
        validation_alias="PRIVACY_ERASURE_HOLD_HOURS_DEFAULT",
    )
    erasure_hold_hours_max: int = Field(
        default=72,
        description="Maximum allowed hold window in hours for erasure DSRs.",
        validation_alias="PRIVACY_ERASURE_HOLD_HOURS_MAX",
    )
    dlp_enabled: bool = Field(
        default=False,
        description="Enables privacy DLP scanning for outputs and guardrails.",
        validation_alias="FEATURE_DLP_ENABLED",
    )
    residency_enforcement_enabled: bool = Field(
        default=False,
        description="Enables request-time workspace data residency enforcement.",
        validation_alias="FEATURE_RESIDENCY_ENFORCEMENT",
    )
    dlp_event_retention_days: int = Field(
        default=90,
        description="Retention period for full-fidelity DLP event records.",
        validation_alias="PRIVACY_DLP_EVENT_RETENTION_DAYS",
    )
    consent_propagator_interval_seconds: int = Field(
        default=60,
        description="Cadence for propagating consent revocations to runtime caches.",
        validation_alias="PRIVACY_CONSENT_PROPAGATOR_INTERVAL_SECONDS",
    )
    salt_vault_path: str = Field(
        default="secret/data/musematic/local/privacy/subject-hash-salt",
        description="Vault path containing subject-hash salt history.",
        validation_alias="PRIVACY_SUBJECT_HASH_SALT_VAULT_PATH",
    )
    clickhouse_pii_tables: list[str] = Field(
        default_factory=lambda: ["execution_metrics", "agent_performance", "token_usage"],
        description="ClickHouse tables that contain user identifiers and support tombstones.",
        validation_alias="PRIVACY_CLICKHOUSE_PII_TABLES",
    )


class ApiGovernanceSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)

    rate_limiting_enabled: bool = Field(
        default=True,
        description="Master switch controlling whether API rate limiting is enforced.",
        validation_alias="FEATURE_API_RATE_LIMITING",
    )
    rate_limiting_fail_open: bool = Field(
        default=False,
        description=(
            "Incident-only override that allows requests through when Redis is unavailable."
        ),
        validation_alias="FEATURE_API_RATE_LIMITING_FAIL_OPEN",
    )
    tier_cache_ttl_seconds: int = Field(
        default=60,
        description="TTL in seconds for cached subscription-tier budget documents.",
        validation_alias="API_TIER_CACHE_TTL_SECONDS",
    )
    principal_cache_ttl_seconds: int = Field(
        default=60,
        description="TTL in seconds for cached principal-to-tier bindings.",
        validation_alias="API_PRINCIPAL_CACHE_TTL_SECONDS",
    )
    anonymous_tier_name: str = Field(
        default="anonymous",
        description="Subscription-tier name applied to anonymous or auth-exempt traffic.",
        validation_alias="API_ANONYMOUS_TIER_NAME",
    )
    default_tier_name: str = Field(
        default="default",
        description="Subscription-tier name applied when a principal has no explicit override.",
        validation_alias="API_DEFAULT_TIER_NAME",
    )


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
    model_config = SettingsConfigDict(
        env_prefix="NOTIFICATIONS_",
        extra="ignore",
        populate_by_name=True,
    )

    rate_limit_per_source_per_minute: int = 20
    alert_retention_days: int = 90
    webhook_max_retries: int = 5
    retry_scan_interval_seconds: int = 30
    gc_interval_hours: int = 24
    multi_channel_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "FEATURE_MULTI_CHANNEL_NOTIFICATIONS",
            "NOTIFICATIONS_MULTI_CHANNEL_ENABLED",
        ),
    )
    webhook_default_backoff_seconds: list[int] = Field(default_factory=lambda: [60, 300, 1800])
    webhook_max_retry_window_seconds: int = 86_400
    webhook_replay_window_seconds: int = 300
    channels_per_user_max: int = 6
    webhooks_per_workspace_max: int = 50
    dead_letter_retention_days: int = 30
    dead_letter_warning_threshold: int = 100
    sms_default_severity_floor: str = "critical"
    sms_provider: str = "twilio"
    sms_workspace_monthly_cost_cap_eur: float = 50.0
    allow_http_webhooks: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "FEATURE_ALLOW_HTTP_WEBHOOKS",
            "NOTIFICATIONS_ALLOW_HTTP_WEBHOOKS",
        ),
    )
    quiet_hours_default_severity_bypass: str = "critical"

    @model_validator(mode="after")
    def _reject_http_webhooks_in_production(self) -> NotificationsSettings:
        env = (
            os.getenv("ENV")
            or os.getenv("ENVIRONMENT")
            or os.getenv("PLATFORM_ENV")
            or os.getenv("APP_ENV")
            or ""
        ).lower()
        if self.allow_http_webhooks and env == "production":
            raise ValueError("FEATURE_ALLOW_HTTP_WEBHOOKS cannot be enabled when ENV=production")
        return self


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


class ContentModerationSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CONTENT_MODERATION_",
        extra="ignore",
        populate_by_name=True,
    )

    enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "FEATURE_CONTENT_MODERATION",
            "CONTENT_MODERATION_ENABLED",
        ),
    )
    default_per_call_timeout_ms: int = 2000
    default_per_execution_budget_ms: int = 5000
    default_monthly_cost_cap_eur: float = 50.0
    default_fairness_band: float = 0.10
    default_min_group_size: int = 5
    default_fairness_staleness_days: int = 90
    audit_all_evaluations: bool = False
    self_hosted_model_name: str = "unitary/multilingual-toxic-xlm-roberta"


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


class ModelCatalogSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MODEL_ROUTER_",
        extra="ignore",
        populate_by_name=True,
    )

    router_enabled: bool = Field(
        default=False,
        description="Enable the model catalogue router for LLM dispatch.",
        validation_alias=AliasChoices("FEATURE_MODEL_ROUTER_ENABLED", "MODEL_ROUTER_ENABLED"),
    )
    auto_deprecation_interval_seconds: int = Field(
        default=3600,
        description="Interval in seconds for the model catalogue auto-deprecation scanner.",
    )
    default_recovery_window_seconds: int = Field(
        default=300,
        description="Default sticky fallback recovery window in seconds.",
    )
    router_primary_timeout_seconds: float = Field(
        default=25.0,
        description="Timeout in seconds for primary model provider calls.",
        validation_alias=AliasChoices(
            "MODEL_ROUTER_PRIMARY_TIMEOUT_SECONDS",
            "MODEL_ROUTER_ROUTER_PRIMARY_TIMEOUT_SECONDS",
        ),
    )
    openai_base_url: str = Field(
        default="https://api.openai.com/v1/chat/completions",
        description="OpenAI-compatible chat completion endpoint for OpenAI models.",
    )
    anthropic_base_url: str = Field(
        default="https://api.anthropic.com/v1/messages",
        description="Anthropic messages endpoint used by the model router.",
    )
    google_base_url: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        description="OpenAI-compatible Google Gemini endpoint used by the model router.",
    )
    mistral_base_url: str = Field(
        default="https://api.mistral.ai/v1/chat/completions",
        description="OpenAI-compatible Mistral endpoint used by the model router.",
    )
    injection_input_sanitizer_enabled: bool = Field(
        default=False,
        description="Enable input sanitization before model router provider dispatch.",
    )
    injection_system_prompt_hardener_enabled: bool = Field(
        default=False,
        description="Enable system prompt hardening for untrusted user text.",
    )
    injection_output_validator_enabled: bool = Field(
        default=False,
        description="Enable output validation and redaction after provider responses.",
    )


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


class AuditSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUDIT_CHAIN_", extra="ignore")

    signing_key_hex: str = Field(
        default="0" * 64,
        description="Hex-encoded 32-byte Ed25519 seed used to sign audit attestations.",
    )
    verifying_key_hex: str = Field(
        default="",
        description="Hex-encoded 32-byte Ed25519 public key; derived from signing key when empty.",
    )
    fail_closed_on_append_error: bool = Field(
        default=True,
        description="Fail originating audit writes when audit-chain append fails.",
    )


class SecurityComplianceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SECURITY_COMPLIANCE_", extra="ignore")

    vuln_gate_enabled: bool = Field(
        default=True,
        description="Enable release blocking when vulnerability scan policy fails.",
    )
    rotation_scheduler_interval_seconds: int = Field(
        default=300,
        description="Interval in seconds for scanning due secret rotations.",
    )
    rotation_overlap_min_hours: int = Field(
        default=24,
        description="Minimum allowed dual-credential overlap window in hours.",
    )
    rotation_overlap_max_hours: int = Field(
        default=168,
        description="Maximum allowed dual-credential overlap window in hours.",
    )
    pentest_overdue_scan_cron: str = Field(
        default="0 3 * * *",
        description="Cron expression for the pentest overdue scanner.",
    )
    manual_evidence_bucket: str = Field(
        default="compliance-evidence",
        description="S3 bucket used for manually uploaded compliance evidence.",
    )
    jit_max_expiry_minutes_floor: int = Field(
        default=1440,
        description="Maximum JIT credential lifetime in minutes.",
    )


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
    feature_cost_hard_caps: bool = Field(
        default=False,
        validation_alias=AliasChoices("FEATURE_COST_HARD_CAPS", "PLATFORM_FEATURE_COST_HARD_CAPS"),
    )
    feature_maintenance_mode: bool = Field(
        default=False,
        validation_alias=AliasChoices("FEATURE_MAINTENANCE_MODE", "feature_maintenance_mode"),
    )
    feature_multi_region: bool = Field(
        default=False,
        validation_alias=AliasChoices("FEATURE_MULTI_REGION", "feature_multi_region"),
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
    cost_governance: CostGovernanceSettings = Field(default_factory=CostGovernanceSettings)
    multi_region_ops: MultiRegionOpsSettings = Field(default_factory=MultiRegionOpsSettings)
    tagging: TaggingSettings = Field(default_factory=TaggingSettings)
    incident_response: IncidentResponseSettings = Field(default_factory=IncidentResponseSettings)
    localization: LocalizationSettings = Field(default_factory=LocalizationSettings)
    visibility: VisibilitySettings = Field(default_factory=VisibilitySettings)
    privacy_compliance: PrivacyComplianceSettings = Field(default_factory=PrivacyComplianceSettings)
    api_governance: ApiGovernanceSettings = Field(default_factory=ApiGovernanceSettings)
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
    model_catalog: ModelCatalogSettings = Field(default_factory=ModelCatalogSettings)
    discovery: DiscoverySettings = Field(default_factory=DiscoverySettings)
    simulation: SimulationSettings = Field(default_factory=SimulationSettings)
    content_moderation: ContentModerationSettings = Field(default_factory=ContentModerationSettings)
    audit: AuditSettings = Field(default_factory=AuditSettings)
    security_compliance: SecurityComplianceSettings = Field(
        default_factory=SecurityComplianceSettings
    )
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
            "AUTH_OAUTH_GOOGLE_AUTHORIZE_URL": ("auth", "oauth_google_authorize_url"),
            "AUTH_OAUTH_GOOGLE_TOKEN_URL": ("auth", "oauth_google_token_url"),
            "AUTH_OAUTH_GOOGLE_TOKEN_INFO_URL": ("auth", "oauth_google_token_info_url"),
            "AUTH_OAUTH_GITHUB_AUTHORIZE_URL": ("auth", "oauth_github_authorize_url"),
            "AUTH_OAUTH_GITHUB_TOKEN_URL": ("auth", "oauth_github_token_url"),
            "AUTH_OAUTH_GITHUB_USER_URL": ("auth", "oauth_github_user_url"),
            "AUTH_OAUTH_GITHUB_EMAILS_URL": ("auth", "oauth_github_emails_url"),
            "AUTH_OAUTH_GITHUB_TEAMS_URL": ("auth", "oauth_github_teams_url"),
            "AUTH_OAUTH_GITHUB_ORG_MEMBERSHIP_URL_TEMPLATE": (
                "auth",
                "oauth_github_org_membership_url_template",
            ),
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
            "FEATURE_COST_HARD_CAPS": ("feature_cost_hard_caps",),
            "FEATURE_MAINTENANCE_MODE": ("feature_maintenance_mode",),
            "FEATURE_MULTI_REGION": ("feature_multi_region",),
            "COST_GOVERNANCE_ANOMALY_EVALUATION_INTERVAL_SECONDS": (
                "cost_governance",
                "anomaly_evaluation_interval_seconds",
            ),
            "COST_GOVERNANCE_FORECAST_EVALUATION_INTERVAL_SECONDS": (
                "cost_governance",
                "forecast_evaluation_interval_seconds",
            ),
            "COST_GOVERNANCE_OVERRIDE_TOKEN_TTL_SECONDS": (
                "cost_governance",
                "override_token_ttl_seconds",
            ),
            "COST_GOVERNANCE_MINIMUM_HISTORY_PERIODS_FOR_FORECAST": (
                "cost_governance",
                "minimum_history_periods_for_forecast",
            ),
            "COST_GOVERNANCE_DEFAULT_ALERT_THRESHOLDS": (
                "cost_governance",
                "default_alert_thresholds",
            ),
            "COST_GOVERNANCE_DEFAULT_CURRENCY": ("cost_governance", "default_currency"),
            "COST_GOVERNANCE_ATTRIBUTION_CLICKHOUSE_BATCH_SIZE": (
                "cost_governance",
                "attribution_clickhouse_batch_size",
            ),
            "COST_GOVERNANCE_ATTRIBUTION_CLICKHOUSE_FLUSH_INTERVAL_SECONDS": (
                "cost_governance",
                "attribution_clickhouse_flush_interval_seconds",
            ),
            "COST_GOVERNANCE_COMPUTE_COST_PER_MS_CENTS": (
                "cost_governance",
                "compute_cost_per_ms_cents",
            ),
            "COST_GOVERNANCE_STORAGE_COST_PER_BYTE_CENTS": (
                "cost_governance",
                "storage_cost_per_byte_cents",
            ),
            "COST_GOVERNANCE_OVERHEAD_COST_PER_EXECUTION_CENTS": (
                "cost_governance",
                "overhead_cost_per_execution_cents",
            ),
            "COST_GOVERNANCE_ATTRIBUTION_FAIL_OPEN": (
                "cost_governance",
                "attribution_fail_open",
            ),
            "MULTI_REGION_OPS_REPLICATION_PROBE_INTERVAL_SECONDS": (
                "multi_region_ops",
                "replication_probe_interval_seconds",
            ),
            "MULTI_REGION_OPS_REPLICATION_PROBE_REQUEST_TIMEOUT_SECONDS": (
                "multi_region_ops",
                "replication_probe_request_timeout_seconds",
            ),
            "MULTI_REGION_OPS_RPO_ALERT_SUSTAINED_INTERVALS": (
                "multi_region_ops",
                "rpo_alert_sustained_intervals",
            ),
            "MULTI_REGION_OPS_FAILOVER_LOCK_MAX_SECONDS": (
                "multi_region_ops",
                "failover_lock_max_seconds",
            ),
            "MULTI_REGION_OPS_CAPACITY_PROJECTION_INTERVAL_SECONDS": (
                "multi_region_ops",
                "capacity_projection_interval_seconds",
            ),
            "MULTI_REGION_OPS_CAPACITY_DEFAULT_UTILIZATION_THRESHOLD": (
                "multi_region_ops",
                "capacity_default_utilization_threshold",
            ),
            "MULTI_REGION_OPS_CAPACITY_SATURATION_HORIZON_DAYS": (
                "multi_region_ops",
                "capacity_saturation_horizon_days",
            ),
            "MULTI_REGION_OPS_MAINTENANCE_ANNOUNCEMENT_LEAD_MINUTES": (
                "multi_region_ops",
                "maintenance_announcement_lead_minutes",
            ),
            "MULTI_REGION_OPS_REPLICATION_STATUS_RETENTION_DAYS": (
                "multi_region_ops",
                "replication_status_retention_days",
            ),
            "MULTI_REGION_OPS_FAILOVER_PLAN_REHEARSAL_STALENESS_DAYS": (
                "multi_region_ops",
                "failover_plan_rehearsal_staleness_days",
            ),
            "TAGGING_LABEL_EXPRESSION_LRU_SIZE": ("tagging", "label_expression_lru_size"),
            "TAGGING_LABEL_EXPRESSION_REDIS_TTL_SECONDS": (
                "tagging",
                "label_expression_redis_ttl_seconds",
            ),
            "TAGGING_CROSS_ENTITY_SEARCH_MAX_VISIBLE_IDS": (
                "tagging",
                "cross_entity_search_max_visible_ids",
            ),
            "TAGGING_SAVED_VIEW_SHARE_PROPAGATION_TARGET_SECONDS": (
                "tagging",
                "saved_view_share_propagation_target_seconds",
            ),
            "TAGGING_ORPHAN_OWNER_RESOLUTION": ("tagging", "orphan_owner_resolution"),
            "INCIDENT_RESPONSE_DELIVERY_RETRY_INITIAL_SECONDS": (
                "incident_response",
                "delivery_retry_initial_seconds",
            ),
            "INCIDENT_RESPONSE_DELIVERY_RETRY_MAX_ATTEMPTS": (
                "incident_response",
                "delivery_retry_max_attempts",
            ),
            "INCIDENT_RESPONSE_DELIVERY_RETRY_MAX_WINDOW_SECONDS": (
                "incident_response",
                "delivery_retry_max_window_seconds",
            ),
            "INCIDENT_RESPONSE_DELIVERY_RETRY_SCAN_INTERVAL_SECONDS": (
                "incident_response",
                "delivery_retry_scan_interval_seconds",
            ),
            "INCIDENT_RESPONSE_RUNBOOK_FRESHNESS_WINDOW_DAYS": (
                "incident_response",
                "runbook_freshness_window_days",
            ),
            "INCIDENT_RESPONSE_TIMELINE_MAX_WINDOW_HOURS": (
                "incident_response",
                "timeline_max_window_hours",
            ),
            "INCIDENT_RESPONSE_DEDUP_FINGERPRINT_TTL_SECONDS": (
                "incident_response",
                "dedup_fingerprint_ttl_seconds",
            ),
            "INCIDENT_RESPONSE_EXTERNAL_ALERT_REQUEST_TIMEOUT_SECONDS": (
                "incident_response",
                "external_alert_request_timeout_seconds",
            ),
            "INCIDENT_RESPONSE_POSTMORTEM_BLOB_THRESHOLD_BYTES": (
                "incident_response",
                "postmortem_blob_threshold_bytes",
            ),
            "INCIDENT_RESPONSE_POSTMORTEM_MINIO_BUCKET": (
                "incident_response",
                "postmortem_minio_bucket",
            ),
            "INCIDENT_RESPONSE_TIMELINE_KAFKA_TOPICS": (
                "incident_response",
                "timeline_kafka_topics",
            ),
            "LOCALIZATION_LOCALE_LRU_SIZE": (
                "localization",
                "localization_locale_lru_size",
            ),
            "LOCALIZATION_DRIFT_THRESHOLD_DAYS": (
                "localization",
                "localization_drift_threshold_days",
            ),
            "LOCALIZATION_DEFAULT_LOCALE": (
                "localization",
                "localization_default_locale",
            ),
            "LOCALIZATION_SUPPORTED_LOCALES": (
                "localization",
                "localization_supported_locales",
            ),
            "LOCALIZATION_TRANSLATION_VENDOR": (
                "localization",
                "localization_translation_vendor",
            ),
            "LOCALIZATION_DEFAULT_DATA_EXPORT_FORMAT": (
                "localization",
                "localization_default_data_export_format",
            ),
            "VISIBILITY_ZERO_TRUST_ENABLED": ("visibility", "zero_trust_enabled"),
            "FEATURE_PRIVACY_DSR_ENABLED": ("privacy_compliance", "dsr_enabled"),
            "PRIVACY_ERASURE_HOLD_HOURS_DEFAULT": (
                "privacy_compliance",
                "erasure_hold_hours_default",
            ),
            "PRIVACY_ERASURE_HOLD_HOURS_MAX": (
                "privacy_compliance",
                "erasure_hold_hours_max",
            ),
            "FEATURE_DLP_ENABLED": ("privacy_compliance", "dlp_enabled"),
            "FEATURE_RESIDENCY_ENFORCEMENT": (
                "privacy_compliance",
                "residency_enforcement_enabled",
            ),
            "PRIVACY_DLP_EVENT_RETENTION_DAYS": (
                "privacy_compliance",
                "dlp_event_retention_days",
            ),
            "PRIVACY_CONSENT_PROPAGATOR_INTERVAL_SECONDS": (
                "privacy_compliance",
                "consent_propagator_interval_seconds",
            ),
            "PRIVACY_SUBJECT_HASH_SALT_VAULT_PATH": (
                "privacy_compliance",
                "salt_vault_path",
            ),
            "PRIVACY_CLICKHOUSE_PII_TABLES": (
                "privacy_compliance",
                "clickhouse_pii_tables",
            ),
            "FEATURE_API_RATE_LIMITING": ("api_governance", "rate_limiting_enabled"),
            "FEATURE_API_RATE_LIMITING_FAIL_OPEN": ("api_governance", "rate_limiting_fail_open"),
            "API_TIER_CACHE_TTL_SECONDS": ("api_governance", "tier_cache_ttl_seconds"),
            "API_PRINCIPAL_CACHE_TTL_SECONDS": ("api_governance", "principal_cache_ttl_seconds"),
            "API_ANONYMOUS_TIER_NAME": ("api_governance", "anonymous_tier_name"),
            "API_DEFAULT_TIER_NAME": ("api_governance", "default_tier_name"),
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
            "AUDIT_CHAIN_SIGNING_KEY": ("audit", "signing_key_hex"),
            "AUDIT_CHAIN_VERIFYING_KEY": ("audit", "verifying_key_hex"),
            "FEATURE_AUDIT_CHAIN_STRICT": ("audit", "fail_closed_on_append_error"),
            "FEATURE_VULN_GATE_ENABLED": ("security_compliance", "vuln_gate_enabled"),
            "SECURITY_COMPLIANCE_ROTATION_SCHEDULER_INTERVAL_SECONDS": (
                "security_compliance",
                "rotation_scheduler_interval_seconds",
            ),
            "SECURITY_COMPLIANCE_ROTATION_OVERLAP_MIN_HOURS": (
                "security_compliance",
                "rotation_overlap_min_hours",
            ),
            "SECURITY_COMPLIANCE_ROTATION_OVERLAP_MAX_HOURS": (
                "security_compliance",
                "rotation_overlap_max_hours",
            ),
            "SECURITY_COMPLIANCE_PENTEST_OVERDUE_SCAN_CRON": (
                "security_compliance",
                "pentest_overdue_scan_cron",
            ),
            "SECURITY_COMPLIANCE_MANUAL_EVIDENCE_BUCKET": (
                "security_compliance",
                "manual_evidence_bucket",
            ),
            "SECURITY_COMPLIANCE_JIT_MAX_EXPIRY_MINUTES_FLOOR": (
                "security_compliance",
                "jit_max_expiry_minutes_floor",
            ),
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
            "FEATURE_MULTI_CHANNEL_NOTIFICATIONS": (
                "notifications",
                "multi_channel_enabled",
            ),
            "NOTIFICATIONS_MULTI_CHANNEL_ENABLED": (
                "notifications",
                "multi_channel_enabled",
            ),
            "NOTIFICATIONS_WEBHOOK_DEFAULT_BACKOFF_SECONDS": (
                "notifications",
                "webhook_default_backoff_seconds",
            ),
            "NOTIFICATIONS_WEBHOOK_MAX_RETRY_WINDOW_SECONDS": (
                "notifications",
                "webhook_max_retry_window_seconds",
            ),
            "NOTIFICATIONS_WEBHOOK_REPLAY_WINDOW_SECONDS": (
                "notifications",
                "webhook_replay_window_seconds",
            ),
            "NOTIFICATIONS_CHANNELS_PER_USER_MAX": (
                "notifications",
                "channels_per_user_max",
            ),
            "NOTIFICATIONS_WEBHOOKS_PER_WORKSPACE_MAX": (
                "notifications",
                "webhooks_per_workspace_max",
            ),
            "NOTIFICATIONS_DEAD_LETTER_RETENTION_DAYS": (
                "notifications",
                "dead_letter_retention_days",
            ),
            "NOTIFICATIONS_DEAD_LETTER_WARNING_THRESHOLD": (
                "notifications",
                "dead_letter_warning_threshold",
            ),
            "NOTIFICATIONS_SMS_DEFAULT_SEVERITY_FLOOR": (
                "notifications",
                "sms_default_severity_floor",
            ),
            "NOTIFICATIONS_SMS_PROVIDER": (
                "notifications",
                "sms_provider",
            ),
            "NOTIFICATIONS_SMS_WORKSPACE_MONTHLY_COST_CAP_EUR": (
                "notifications",
                "sms_workspace_monthly_cost_cap_eur",
            ),
            "FEATURE_ALLOW_HTTP_WEBHOOKS": (
                "notifications",
                "allow_http_webhooks",
            ),
            "NOTIFICATIONS_ALLOW_HTTP_WEBHOOKS": (
                "notifications",
                "allow_http_webhooks",
            ),
            "NOTIFICATIONS_QUIET_HOURS_DEFAULT_SEVERITY_BYPASS": (
                "notifications",
                "quiet_hours_default_severity_bypass",
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
            "FEATURE_MODEL_ROUTER_ENABLED": ("model_catalog", "router_enabled"),
            "MODEL_ROUTER_ENABLED": ("model_catalog", "router_enabled"),
            "MODEL_ROUTER_AUTO_DEPRECATION_INTERVAL_SECONDS": (
                "model_catalog",
                "auto_deprecation_interval_seconds",
            ),
            "MODEL_ROUTER_DEFAULT_RECOVERY_WINDOW_SECONDS": (
                "model_catalog",
                "default_recovery_window_seconds",
            ),
            "MODEL_ROUTER_PRIMARY_TIMEOUT_SECONDS": (
                "model_catalog",
                "router_primary_timeout_seconds",
            ),
            "MODEL_ROUTER_OPENAI_BASE_URL": ("model_catalog", "openai_base_url"),
            "MODEL_ROUTER_ANTHROPIC_BASE_URL": (
                "model_catalog",
                "anthropic_base_url",
            ),
            "MODEL_ROUTER_GOOGLE_BASE_URL": ("model_catalog", "google_base_url"),
            "MODEL_ROUTER_MISTRAL_BASE_URL": ("model_catalog", "mistral_base_url"),
            "MODEL_ROUTER_INJECTION_INPUT_SANITIZER_ENABLED": (
                "model_catalog",
                "injection_input_sanitizer_enabled",
            ),
            "MODEL_ROUTER_INJECTION_SYSTEM_PROMPT_HARDENER_ENABLED": (
                "model_catalog",
                "injection_system_prompt_hardener_enabled",
            ),
            "MODEL_ROUTER_INJECTION_OUTPUT_VALIDATOR_ENABLED": (
                "model_catalog",
                "injection_output_validator_enabled",
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
            "FEATURE_CONTENT_MODERATION": ("content_moderation", "enabled"),
            "CONTENT_MODERATION_ENABLED": ("content_moderation", "enabled"),
            "CONTENT_MODERATION_DEFAULT_PER_CALL_TIMEOUT_MS": (
                "content_moderation",
                "default_per_call_timeout_ms",
            ),
            "CONTENT_MODERATION_DEFAULT_PER_EXECUTION_BUDGET_MS": (
                "content_moderation",
                "default_per_execution_budget_ms",
            ),
            "CONTENT_MODERATION_DEFAULT_MONTHLY_COST_CAP_EUR": (
                "content_moderation",
                "default_monthly_cost_cap_eur",
            ),
            "CONTENT_MODERATION_DEFAULT_FAIRNESS_BAND": (
                "content_moderation",
                "default_fairness_band",
            ),
            "CONTENT_MODERATION_DEFAULT_MIN_GROUP_SIZE": (
                "content_moderation",
                "default_min_group_size",
            ),
            "CONTENT_MODERATION_DEFAULT_FAIRNESS_STALENESS_DAYS": (
                "content_moderation",
                "default_fairness_staleness_days",
            ),
            "CONTENT_MODERATION_AUDIT_ALL_EVALUATIONS": (
                "content_moderation",
                "audit_all_evaluations",
            ),
            "CONTENT_MODERATION_SELF_HOSTED_MODEL_NAME": (
                "content_moderation",
                "self_hosted_model_name",
            ),
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
    def FEATURE_MULTI_CHANNEL_NOTIFICATIONS(self) -> bool:
        return self.notifications.multi_channel_enabled

    @property
    def FEATURE_ALLOW_HTTP_WEBHOOKS(self) -> bool:
        return self.notifications.allow_http_webhooks

    @property
    def FEATURE_CONTENT_MODERATION(self) -> bool:
        return self.content_moderation.enabled

    @property
    def FEATURE_COST_HARD_CAPS(self) -> bool:
        return self.feature_cost_hard_caps

    @property
    def FEATURE_MAINTENANCE_MODE(self) -> bool:
        return self.feature_maintenance_mode

    @property
    def FEATURE_MULTI_REGION(self) -> bool:
        return self.feature_multi_region

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
    def AUTH_OAUTH_GOOGLE_AUTHORIZE_URL(self) -> str:
        return self.auth.oauth_google_authorize_url

    @property
    def AUTH_OAUTH_GOOGLE_TOKEN_URL(self) -> str:
        return self.auth.oauth_google_token_url

    @property
    def AUTH_OAUTH_GOOGLE_TOKEN_INFO_URL(self) -> str:
        return self.auth.oauth_google_token_info_url

    @property
    def AUTH_OAUTH_GITHUB_AUTHORIZE_URL(self) -> str:
        return self.auth.oauth_github_authorize_url

    @property
    def AUTH_OAUTH_GITHUB_TOKEN_URL(self) -> str:
        return self.auth.oauth_github_token_url

    @property
    def AUTH_OAUTH_GITHUB_USER_URL(self) -> str:
        return self.auth.oauth_github_user_url

    @property
    def AUTH_OAUTH_GITHUB_EMAILS_URL(self) -> str:
        return self.auth.oauth_github_emails_url

    @property
    def AUTH_OAUTH_GITHUB_TEAMS_URL(self) -> str:
        return self.auth.oauth_github_teams_url

    @property
    def AUTH_OAUTH_GITHUB_ORG_MEMBERSHIP_URL_TEMPLATE(self) -> str:
        return self.auth.oauth_github_org_membership_url_template

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
    def FEATURE_PRIVACY_DSR_ENABLED(self) -> bool:
        return self.privacy_compliance.dsr_enabled

    @property
    def FEATURE_DLP_ENABLED(self) -> bool:
        return self.privacy_compliance.dlp_enabled

    @property
    def FEATURE_RESIDENCY_ENFORCEMENT(self) -> bool:
        return self.privacy_compliance.residency_enforcement_enabled

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
    def AUDIT_CHAIN_SIGNING_KEY(self) -> str:
        return self.audit.signing_key_hex

    @property
    def AUDIT_CHAIN_VERIFYING_KEY(self) -> str:
        return self.audit.verifying_key_hex

    @property
    def FEATURE_AUDIT_CHAIN_STRICT(self) -> bool:
        return self.audit.fail_closed_on_append_error

    @property
    def FEATURE_VULN_GATE_ENABLED(self) -> bool:
        return self.security_compliance.vuln_gate_enabled

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
