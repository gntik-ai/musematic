package escalation

import (
	"context"
	"encoding/json"
	"time"
)

type Producer interface {
	Produce(ctx context.Context, topic, key string, value []byte) error
}

type Router struct {
	producer Producer
	now      func() time.Time
}

func NewRouter(producer Producer) *Router {
	return &Router{
		producer: producer,
		now:      func() time.Time { return time.Now().UTC() },
	}
}

func (r *Router) Escalate(ctx context.Context, loopID, execID string, iterationsUsed int, costUsed, lastQuality float64) error {
	if r == nil || r.producer == nil {
		return nil
	}

	payload, err := json.Marshal(map[string]any{
		"event_type":         "reasoning.escalate_to_human",
		"version":            "1.0",
		"source":             "reasoning-engine",
		"execution_id":       execID,
		"loop_id":            loopID,
		"iterations_used":    iterationsUsed,
		"cost_used":          costUsed,
		"last_quality_score": lastQuality,
		"occurred_at":        r.now().Format(time.RFC3339Nano),
	})
	if err != nil {
		return err
	}
	return r.producer.Produce(ctx, "monitor.alerts", execID, payload)
}
