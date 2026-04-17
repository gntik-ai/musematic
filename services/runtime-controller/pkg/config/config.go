package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

type Config struct {
	GRPCPort                  int
	HTTPPort                  int
	PostgresDSN               string
	RedisAddr                 string
	KafkaBrokers              []string
	MinIOEndpoint             string
	MinIOBucket               string
	K8sNamespace              string
	ReconcileInterval         time.Duration
	HeartbeatTimeout          time.Duration
	HeartbeatCheckInterval    time.Duration
	WarmPoolIdleTimeout       time.Duration
	WarmPoolReplenishInterval time.Duration
	WarmPoolTargets           map[string]int
	StopGracePeriod           time.Duration
	AgentPackagePresignTTL    time.Duration
	K8sDryRun                 bool
	OTLPExporterEndpoint      string
}

func Load() (Config, error) {
	cfg := Config{
		GRPCPort:                  readInt("GRPC_PORT", 50051),
		HTTPPort:                  readInt("HTTP_PORT", 8080),
		PostgresDSN:               strings.TrimSpace(os.Getenv("POSTGRES_DSN")),
		RedisAddr:                 strings.TrimSpace(os.Getenv("REDIS_ADDR")),
		KafkaBrokers:              readList("KAFKA_BROKERS", "localhost:9092"),
		MinIOEndpoint:             readString("MINIO_ENDPOINT", "http://musematic-minio.platform-data:9000"),
		MinIOBucket:               readString("MINIO_BUCKET", "musematic-artifacts"),
		K8sNamespace:              readString("K8S_NAMESPACE", "platform-execution"),
		ReconcileInterval:         readDuration("RECONCILE_INTERVAL", 30*time.Second),
		HeartbeatTimeout:          readDuration("HEARTBEAT_TIMEOUT", 60*time.Second),
		HeartbeatCheckInterval:    readDuration("HEARTBEAT_CHECK_INTERVAL", 10*time.Second),
		WarmPoolIdleTimeout:       readDuration("WARM_POOL_IDLE_TIMEOUT", 5*time.Minute),
		WarmPoolReplenishInterval: readDuration("WARM_POOL_REPLENISH_INTERVAL", 30*time.Second),
		WarmPoolTargets:           readTargetMap("WARM_POOL_TARGETS"),
		StopGracePeriod:           readDuration("STOP_GRACE_PERIOD", 30*time.Second),
		AgentPackagePresignTTL:    readDuration("AGENT_PACKAGE_PRESIGN_TTL", 2*time.Hour),
		K8sDryRun:                 readBool("K8S_DRY_RUN", false),
		OTLPExporterEndpoint:      readString("OTEL_EXPORTER_OTLP_ENDPOINT", ""),
	}
	if cfg.PostgresDSN == "" {
		return Config{}, fmt.Errorf("POSTGRES_DSN is required")
	}
	if cfg.RedisAddr == "" {
		return Config{}, fmt.Errorf("REDIS_ADDR is required")
	}
	return cfg, nil
}

func readTargetMap(key string) map[string]int {
	raw := strings.TrimSpace(os.Getenv(key))
	targets := map[string]int{}
	if raw == "" {
		return targets
	}
	for _, part := range strings.Split(raw, ",") {
		name, value, ok := strings.Cut(strings.TrimSpace(part), "=")
		if !ok || strings.TrimSpace(name) == "" {
			continue
		}
		count, err := strconv.Atoi(strings.TrimSpace(value))
		if err != nil || count < 0 {
			continue
		}
		targets[strings.TrimSpace(name)] = count
	}
	return targets
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
