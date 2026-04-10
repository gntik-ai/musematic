package main

import "testing"

func TestEnvHelpersAndLoadConfig(t *testing.T) {
	t.Setenv("GRPC_PORT", "60000")
	t.Setenv("MINIO_BUCKET", "custom-bucket")
	t.Setenv("MAX_TOT_CONCURRENCY", "12")
	t.Setenv("TRACE_BUFFER_SIZE", "200")
	t.Setenv("TRACE_PAYLOAD_THRESHOLD", "1234")
	t.Setenv("BUDGET_DEFAULT_TTL_SECONDS", "99")

	cfg, err := loadConfig()
	if err != nil {
		t.Fatalf("loadConfig() error = %v", err)
	}
	if cfg.grpcPort != 60000 || cfg.minioBucket != "custom-bucket" || cfg.maxToTConcurrency != 12 {
		t.Fatalf("unexpected config: %+v", cfg)
	}
	if envString("MISSING_STRING", "fallback") != "fallback" {
		t.Fatal("envString() did not return fallback")
	}
	if envInt("MISSING_INT", 7) != 7 {
		t.Fatal("envInt() did not return fallback")
	}
	if envInt64("MISSING_INT64", 9) != 9 {
		t.Fatal("envInt64() did not return fallback")
	}
}

func TestRunReturnsMissingRedisError(t *testing.T) {
	t.Setenv("REDIS_ADDR", "")
	t.Setenv("POSTGRES_DSN", "")
	t.Setenv("KAFKA_BROKERS", "")
	t.Setenv("MINIO_ENDPOINT", "")
	t.Setenv("MINIO_BUCKET", "")

	if err := run(); err == nil || err.Error() != "REDIS_ADDR is required" {
		t.Fatalf("run() error = %v, want REDIS_ADDR is required", err)
	}
}

func TestRunValidatesDependenciesInOrder(t *testing.T) {
	t.Setenv("REDIS_TEST_MODE", "standalone")
	t.Setenv("REDIS_ADDR", "127.0.0.1:6379")
	t.Setenv("POSTGRES_DSN", "")
	t.Setenv("KAFKA_BROKERS", "")
	t.Setenv("MINIO_ENDPOINT", "")
	t.Setenv("MINIO_BUCKET", "")

	if err := run(); err == nil || err.Error() != "POSTGRES_DSN is required" {
		t.Fatalf("run() error = %v, want POSTGRES_DSN is required", err)
	}

	t.Setenv("POSTGRES_DSN", "postgres://user:pass@127.0.0.1:5432/musematic?sslmode=disable")
	if err := run(); err == nil || err.Error() != "KAFKA_BROKERS is required" {
		t.Fatalf("run() error = %v, want KAFKA_BROKERS is required", err)
	}

	t.Setenv("KAFKA_BROKERS", "127.0.0.1:9092")
	if err := run(); err == nil || err.Error() != "MINIO_ENDPOINT and MINIO_BUCKET are required" {
		t.Fatalf("run() error = %v, want MINIO_ENDPOINT and MINIO_BUCKET are required", err)
	}
}

func TestRunReturnsLuaLoadErrorAfterDependencies(t *testing.T) {
	t.Setenv("REDIS_TEST_MODE", "standalone")
	t.Setenv("REDIS_ADDR", "127.0.0.1:6379")
	t.Setenv("POSTGRES_DSN", "postgres://user:pass@127.0.0.1:5432/musematic?sslmode=disable")
	t.Setenv("KAFKA_BROKERS", "127.0.0.1:9092")
	t.Setenv("MINIO_ENDPOINT", "http://127.0.0.1:9000")
	t.Setenv("MINIO_BUCKET", "reasoning-traces")

	if err := run(); err == nil {
		t.Fatal("expected lua load error without a live redis instance")
	}
}
