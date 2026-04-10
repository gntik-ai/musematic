package health

import (
	"context"
	"encoding/json"
	"net/http"
)

type PostgresPinger interface {
	Ping(context.Context) error
}

type KafkaMetadataChecker interface {
	GetMetadata(*string, bool, int) (*struct{}, error)
}

type K8sChecker interface {
	DoRaw(context.Context, string) ([]byte, error)
}

type Dependencies struct {
	Postgres PostgresPinger
	Kafka    KafkaMetadataChecker
	K8s      K8sChecker
}

func LivezHandler(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
}

func ReadyzHandler(deps Dependencies) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()
		if deps.Postgres != nil {
			if err := deps.Postgres.Ping(ctx); err != nil {
				http.Error(w, err.Error(), http.StatusServiceUnavailable)
				return
			}
		}
		if deps.Kafka != nil {
			if _, err := deps.Kafka.GetMetadata(nil, false, 1000); err != nil {
				http.Error(w, err.Error(), http.StatusServiceUnavailable)
				return
			}
		}
		if deps.K8s != nil {
			if _, err := deps.K8s.DoRaw(ctx, "/readyz"); err != nil {
				http.Error(w, err.Error(), http.StatusServiceUnavailable)
				return
			}
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
	})
}
