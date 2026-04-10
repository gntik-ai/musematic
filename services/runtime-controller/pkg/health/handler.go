package health

import (
	"context"
	"encoding/json"
	"net/http"
	"time"

	"github.com/confluentinc/confluent-kafka-go/v2/kafka"
)

type Pinger interface {
	Ping(context.Context) error
}

type KafkaMetadataChecker interface {
	GetMetadata(*string, bool, int) (*kafka.Metadata, error)
}

type K8sHealthChecker interface {
	DoRaw(context.Context, string) ([]byte, error)
}

type Dependencies struct {
	Postgres Pinger
	Redis    Pinger
	Kafka    KafkaMetadataChecker
	K8s      K8sHealthChecker
}

func LivezHandler(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func ReadyzHandler(deps Dependencies) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
		defer cancel()
		checks := map[string]string{}
		statusCode := http.StatusOK
		if deps.Postgres != nil && deps.Postgres.Ping(ctx) != nil {
			checks["postgres"] = "error"
			statusCode = http.StatusServiceUnavailable
		} else {
			checks["postgres"] = "ok"
		}
		if deps.Redis != nil && deps.Redis.Ping(ctx) != nil {
			checks["redis"] = "error"
			statusCode = http.StatusServiceUnavailable
		} else {
			checks["redis"] = "ok"
		}
		if deps.Kafka != nil {
			if _, err := deps.Kafka.GetMetadata(nil, true, 5000); err != nil {
				checks["kafka"] = "error"
				statusCode = http.StatusServiceUnavailable
			} else {
				checks["kafka"] = "ok"
			}
		}
		if deps.K8s != nil {
			if _, err := deps.K8s.DoRaw(ctx, "/healthz"); err != nil {
				checks["k8s"] = "error"
				statusCode = http.StatusServiceUnavailable
			} else {
				checks["k8s"] = "ok"
			}
		}
		status := "ok"
		if statusCode != http.StatusOK {
			status = "error"
		}
		writeJSON(w, statusCode, map[string]any{"status": status, "checks": checks})
	}
}

func writeJSON(w http.ResponseWriter, statusCode int, payload map[string]any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(statusCode)
	_ = json.NewEncoder(w).Encode(payload)
}
