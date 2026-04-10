package heartbeat

import (
	"context"
	"fmt"
	"time"

	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/state"
	"github.com/redis/go-redis/v9"
)

type RedisSetter interface {
	Set(context.Context, string, interface{}, time.Duration) *redis.StatusCmd
}

type HeartbeatTracker struct {
	Redis RedisSetter
	Store interface {
		UpdateLastHeartbeat(context.Context, string, time.Time) error
	}
	Timeout time.Duration
}

func (h *HeartbeatTracker) ReceiveHeartbeat(ctx context.Context, runtimeID string) error {
	now := time.Now().UTC()
	if err := h.Redis.Set(ctx, heartbeatKey(runtimeID), now.Format(time.RFC3339Nano), h.Timeout).Err(); err != nil {
		return err
	}
	return h.Store.UpdateLastHeartbeat(ctx, runtimeID, now)
}

func heartbeatKey(runtimeID string) string {
	return fmt.Sprintf("heartbeat:%s", runtimeID)
}

var _ interface {
	UpdateLastHeartbeat(context.Context, string, time.Time) error
} = (*state.Store)(nil)
