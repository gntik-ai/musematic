package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

type Config struct {
	GRPCPort               int
	HTTPPort               int
	PostgresDSN            string
	KafkaBrokers           []string
	MinIOEndpoint          string
	MinIOBucket            string
	K8sNamespace           string
	DefaultTimeout         time.Duration
	MaxTimeout             time.Duration
	MaxOutputSize          int
	OrphanScanInterval     time.Duration
	IdleTimeout            time.Duration
	MaxConcurrentSandboxes int
	K8sDryRun              bool
	OTLPExporterEndpoint   string
}

func Load() (Config, error) {
	cfg := Config{
		GRPCPort:               readInt("GRPC_PORT", 50053),
		HTTPPort:               readInt("HTTP_PORT", 8080),
		PostgresDSN:            strings.TrimSpace(os.Getenv("POSTGRES_DSN")),
		KafkaBrokers:           readList("KAFKA_BROKERS", "localhost:9092"),
		MinIOEndpoint:          readString("MINIO_ENDPOINT", "http://musematic-minio.platform-data:9000"),
		MinIOBucket:            readString("MINIO_BUCKET", "musematic-artifacts"),
		K8sNamespace:           readString("K8S_NAMESPACE", "platform-execution"),
		DefaultTimeout:         readDuration("DEFAULT_TIMEOUT", 30*time.Second),
		MaxTimeout:             readDuration("MAX_TIMEOUT", 300*time.Second),
		MaxOutputSize:          readInt("MAX_OUTPUT_SIZE", 10*1024*1024),
		OrphanScanInterval:     readDuration("ORPHAN_SCAN_INTERVAL", 60*time.Second),
		IdleTimeout:            readDuration("IDLE_TIMEOUT", 300*time.Second),
		MaxConcurrentSandboxes: readInt("MAX_CONCURRENT_SANDBOXES", 50),
		K8sDryRun:              readBool("K8S_DRY_RUN", false),
		OTLPExporterEndpoint:   readString("OTEL_EXPORTER_OTLP_ENDPOINT", ""),
	}
	if cfg.PostgresDSN == "" {
		return Config{}, fmt.Errorf("POSTGRES_DSN is required")
	}
	return cfg, nil
}

func readString(key string, defaultValue string) string {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return defaultValue
	}
	return value
}

func readList(key string, defaultValue string) []string {
	raw := readString(key, defaultValue)
	parts := strings.Split(raw, ",")
	out := make([]string, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part != "" {
			out = append(out, part)
		}
	}
	return out
}

func readInt(key string, defaultValue int) int {
	raw := strings.TrimSpace(os.Getenv(key))
	if raw == "" {
		return defaultValue
	}
	value, err := strconv.Atoi(raw)
	if err != nil {
		return defaultValue
	}
	return value
}

func readBool(key string, defaultValue bool) bool {
	raw := strings.TrimSpace(os.Getenv(key))
	if raw == "" {
		return defaultValue
	}
	value, err := strconv.ParseBool(raw)
	if err != nil {
		return defaultValue
	}
	return value
}

func readDuration(key string, defaultValue time.Duration) time.Duration {
	raw := strings.TrimSpace(os.Getenv(key))
	if raw == "" {
		return defaultValue
	}
	value, err := time.ParseDuration(raw)
	if err != nil {
		return defaultValue
	}
	return value
}
