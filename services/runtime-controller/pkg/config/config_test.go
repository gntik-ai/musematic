package config

import (
	"testing"
	"time"
)

func clearConfigEnv(t *testing.T) {
	t.Helper()
	for _, key := range []string{
		"GRPC_PORT",
		"HTTP_PORT",
		"POSTGRES_DSN",
		"REDIS_ADDR",
		"KAFKA_BROKERS",
		"S3_ENDPOINT_URL",
		"MINIO_ENDPOINT",
		"S3_BUCKET",
		"MINIO_BUCKET",
		"S3_ACCESS_KEY",
		"MINIO_ACCESS_KEY",
		"S3_SECRET_KEY",
		"MINIO_SECRET_KEY",
		"S3_REGION",
		"S3_USE_PATH_STYLE",
		"K8S_NAMESPACE",
		"RECONCILE_INTERVAL",
		"HEARTBEAT_TIMEOUT",
		"HEARTBEAT_CHECK_INTERVAL",
		"WARM_POOL_IDLE_TIMEOUT",
		"WARM_POOL_REPLENISH_INTERVAL",
		"WARM_POOL_TARGETS",
		"STOP_GRACE_PERIOD",
		"AGENT_PACKAGE_PRESIGN_TTL",
		"K8S_DRY_RUN",
		"OTEL_EXPORTER_OTLP_ENDPOINT",
	} {
		t.Setenv(key, "")
	}
}

func TestLoadRequiresPostgresAndRedis(t *testing.T) {
	clearConfigEnv(t)

	if _, err := Load(); err == nil {
		t.Fatalf("expected missing POSTGRES_DSN error")
	}

	t.Setenv("POSTGRES_DSN", "postgres://example")
	if _, err := Load(); err == nil {
		t.Fatalf("expected missing REDIS_ADDR error")
	}
}

func TestLoadUsesDefaults(t *testing.T) {
	clearConfigEnv(t)
	t.Setenv("POSTGRES_DSN", "postgres://user:pass@localhost:5432/musematic")
	t.Setenv("REDIS_ADDR", "localhost:6379")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load returned error: %v", err)
	}
	if cfg.GRPCPort != 50051 || cfg.HTTPPort != 8080 {
		t.Fatalf("unexpected default ports: %+v", cfg)
	}
	if len(cfg.KafkaBrokers) != 1 || cfg.KafkaBrokers[0] != "localhost:9092" {
		t.Fatalf("unexpected default brokers: %+v", cfg.KafkaBrokers)
	}
	if cfg.S3Bucket != "musematic-artifacts" || cfg.K8sNamespace != "platform-execution" {
		t.Fatalf("unexpected defaults: %+v", cfg)
	}
	if cfg.ReconcileInterval != 30*time.Second || cfg.AgentPackagePresignTTL != 2*time.Hour {
		t.Fatalf("unexpected duration defaults: %+v", cfg)
	}
	if cfg.K8sDryRun {
		t.Fatalf("expected dry-run default false")
	}
	if cfg.OTLPExporterEndpoint != "" {
		t.Fatalf("expected empty OTLP endpoint by default, got %q", cfg.OTLPExporterEndpoint)
	}
	if len(cfg.WarmPoolTargets) != 0 {
		t.Fatalf("expected empty warm pool targets by default")
	}
}

func TestLoadPrefersS3ValuesOverLegacyMinIOFallback(t *testing.T) {
	clearConfigEnv(t)
	t.Setenv("POSTGRES_DSN", "postgres://test")
	t.Setenv("REDIS_ADDR", "localhost:6379")
	t.Setenv("MINIO_ENDPOINT", "http://legacy-minio:9000")
	t.Setenv("MINIO_BUCKET", "legacy-bucket")
	t.Setenv("S3_ENDPOINT_URL", "https://preferred.example.com")
	t.Setenv("S3_BUCKET", "preferred-bucket")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load returned error: %v", err)
	}
	if cfg.S3EndpointURL != "https://preferred.example.com" || cfg.S3Bucket != "preferred-bucket" {
		t.Fatalf("expected S3 values to take precedence: %+v", cfg)
	}
}

func TestLoadFallsBackToLegacyMinIOValues(t *testing.T) {
	clearConfigEnv(t)
	t.Setenv("POSTGRES_DSN", "postgres://test")
	t.Setenv("REDIS_ADDR", "localhost:6379")
	t.Setenv("MINIO_ENDPOINT", "http://legacy-minio:9000")
	t.Setenv("MINIO_BUCKET", "legacy-bucket")
	t.Setenv("MINIO_ACCESS_KEY", "legacy-access")
	t.Setenv("MINIO_SECRET_KEY", "legacy-secret")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load returned error: %v", err)
	}
	if cfg.S3EndpointURL != "http://legacy-minio:9000" || cfg.S3Bucket != "legacy-bucket" {
		t.Fatalf("expected legacy MinIO fallback values: %+v", cfg)
	}
	if cfg.S3AccessKey != "legacy-access" || cfg.S3SecretKey != "legacy-secret" {
		t.Fatalf("expected legacy MinIO credentials fallback: %+v", cfg)
	}
}

func TestLoadParsesCustomValues(t *testing.T) {
	clearConfigEnv(t)
	t.Setenv("POSTGRES_DSN", "postgres://custom")
	t.Setenv("REDIS_ADDR", "redis.internal:6380")
	t.Setenv("GRPC_PORT", "6000")
	t.Setenv("HTTP_PORT", "9000")
	t.Setenv("KAFKA_BROKERS", "k1:9092, k2:9092 , ,k3:9092")
	t.Setenv("S3_ENDPOINT_URL", "https://s3.example.com")
	t.Setenv("S3_BUCKET", "runtime-artifacts")
	t.Setenv("S3_ACCESS_KEY", "runtime-access")
	t.Setenv("S3_SECRET_KEY", "runtime-secret")
	t.Setenv("S3_REGION", "eu-central-1")
	t.Setenv("S3_USE_PATH_STYLE", "false")
	t.Setenv("K8S_NAMESPACE", "runtime")
	t.Setenv("RECONCILE_INTERVAL", "45s")
	t.Setenv("HEARTBEAT_TIMEOUT", "90s")
	t.Setenv("HEARTBEAT_CHECK_INTERVAL", "15s")
	t.Setenv("WARM_POOL_IDLE_TIMEOUT", "10m")
	t.Setenv("WARM_POOL_REPLENISH_INTERVAL", "90s")
	t.Setenv("WARM_POOL_TARGETS", "ws-1/agent-a=2,invalid,ws-2/agent-b=1")
	t.Setenv("STOP_GRACE_PERIOD", "45s")
	t.Setenv("AGENT_PACKAGE_PRESIGN_TTL", "30m")
	t.Setenv("K8S_DRY_RUN", "true")
	t.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "otel-collector:4317")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load returned error: %v", err)
	}
	if cfg.GRPCPort != 6000 || cfg.HTTPPort != 9000 {
		t.Fatalf("unexpected custom ports: %+v", cfg)
	}
	if got := cfg.KafkaBrokers; len(got) != 3 || got[1] != "k2:9092" {
		t.Fatalf("unexpected broker list: %+v", got)
	}
	if cfg.S3EndpointURL != "https://s3.example.com" || cfg.S3Bucket != "runtime-artifacts" || cfg.K8sNamespace != "runtime" {
		t.Fatalf("unexpected custom strings: %+v", cfg)
	}
	if cfg.ReconcileInterval != 45*time.Second || cfg.WarmPoolIdleTimeout != 10*time.Minute {
		t.Fatalf("unexpected custom durations: %+v", cfg)
	}
	if cfg.S3AccessKey != "runtime-access" || cfg.S3SecretKey != "runtime-secret" || cfg.S3Region != "eu-central-1" || cfg.S3UsePathStyle {
		t.Fatalf("unexpected s3 configuration: %+v", cfg)
	}
	if !cfg.K8sDryRun {
		t.Fatalf("expected dry-run true")
	}
	if cfg.OTLPExporterEndpoint != "otel-collector:4317" {
		t.Fatalf("unexpected OTLP endpoint: %q", cfg.OTLPExporterEndpoint)
	}
	if cfg.WarmPoolTargets["ws-1/agent-a"] != 2 || cfg.WarmPoolTargets["ws-2/agent-b"] != 1 {
		t.Fatalf("unexpected warm pool targets: %+v", cfg.WarmPoolTargets)
	}
}

func TestReadHelpersFallbackOnInvalidValues(t *testing.T) {
	clearConfigEnv(t)
	t.Setenv("INT_VALUE", "invalid")
	t.Setenv("BOOL_VALUE", "invalid")
	t.Setenv("DURATION_VALUE", "invalid")
	t.Setenv("LIST_VALUE", " one, two ,,three ")

	if got := readInt("INT_VALUE", 42); got != 42 {
		t.Fatalf("expected fallback int, got %d", got)
	}
	if got := readBool("BOOL_VALUE", true); !got {
		t.Fatalf("expected fallback bool true")
	}
	if got := readDuration("DURATION_VALUE", time.Minute); got != time.Minute {
		t.Fatalf("expected fallback duration, got %s", got)
	}
	if got := readList("LIST_VALUE", "unused"); len(got) != 3 || got[0] != "one" || got[2] != "three" {
		t.Fatalf("unexpected list parsing: %+v", got)
	}
}
