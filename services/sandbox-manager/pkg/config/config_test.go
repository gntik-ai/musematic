package config

import (
	"testing"
	"time"
)

func TestLoadReadsEnvironment(t *testing.T) {
	t.Setenv("GRPC_PORT", "60000")
	t.Setenv("HTTP_PORT", "18080")
	t.Setenv("POSTGRES_DSN", "postgres://test")
	t.Setenv("KAFKA_BROKERS", "kafka-1:9092,kafka-2:9092")
	t.Setenv("S3_ENDPOINT_URL", "https://s3.internal.example.com")
	t.Setenv("S3_BUCKET", "artifacts")
	t.Setenv("K8S_NAMESPACE", "sandbox-ns")
	t.Setenv("DEFAULT_TIMEOUT", "45s")
	t.Setenv("MAX_TIMEOUT", "10m")
	t.Setenv("MAX_OUTPUT_SIZE", "2048")
	t.Setenv("ORPHAN_SCAN_INTERVAL", "90s")
	t.Setenv("IDLE_TIMEOUT", "120s")
	t.Setenv("MAX_CONCURRENT_SANDBOXES", "12")
	t.Setenv("K8S_DRY_RUN", "true")
	t.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "otel:4317")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}
	if cfg.GRPCPort != 60000 || cfg.HTTPPort != 18080 {
		t.Fatalf("unexpected ports %+v", cfg)
	}
	if len(cfg.KafkaBrokers) != 2 || cfg.KafkaBrokers[1] != "kafka-2:9092" {
		t.Fatalf("unexpected kafka brokers %+v", cfg.KafkaBrokers)
	}
	if cfg.DefaultTimeout != 45*time.Second || cfg.MaxTimeout != 10*time.Minute {
		t.Fatalf("unexpected timeouts %+v", cfg)
	}
	if cfg.S3EndpointURL != "https://s3.internal.example.com" || cfg.S3Bucket != "artifacts" {
		t.Fatalf("unexpected s3 settings %+v", cfg)
	}
	if !cfg.K8sDryRun || cfg.OTLPExporterEndpoint != "otel:4317" {
		t.Fatalf("unexpected flags %+v", cfg)
	}
}

func TestLoadRequiresPostgresDSN(t *testing.T) {
	t.Setenv("POSTGRES_DSN", "")
	if _, err := Load(); err == nil || err.Error() != "POSTGRES_DSN is required" {
		t.Fatalf("Load() error = %v", err)
	}
}

func TestReadersFallbackOnInvalidInput(t *testing.T) {
	t.Setenv("BROKERS", " a, ,b ")
	t.Setenv("INT_VALUE", "invalid")
	t.Setenv("BOOL_VALUE", "invalid")
	t.Setenv("DURATION_VALUE", "invalid")

	if got := readString("MISSING_VALUE", "fallback"); got != "fallback" {
		t.Fatalf("readString() = %q", got)
	}
	if got := readList("BROKERS", "ignored"); len(got) != 2 || got[0] != "a" || got[1] != "b" {
		t.Fatalf("readList() = %+v", got)
	}
	if got := readInt("INT_VALUE", 7); got != 7 {
		t.Fatalf("readInt() = %d", got)
	}
	if got := readBool("BOOL_VALUE", true); !got {
		t.Fatalf("readBool() = %v", got)
	}
	if got := readDuration("DURATION_VALUE", time.Minute); got != time.Minute {
		t.Fatalf("readDuration() = %s", got)
	}
}

func TestLoadFallsBackToLegacyMinIOSettings(t *testing.T) {
	t.Setenv("POSTGRES_DSN", "postgres://test")
	t.Setenv("MINIO_ENDPOINT", "http://legacy-minio:9000")
	t.Setenv("MINIO_BUCKET", "legacy-bucket")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}
	if cfg.S3EndpointURL != "http://legacy-minio:9000" || cfg.S3Bucket != "legacy-bucket" {
		t.Fatalf("unexpected fallback s3 settings %+v", cfg)
	}
}
