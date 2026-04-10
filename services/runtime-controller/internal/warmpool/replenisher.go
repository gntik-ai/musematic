package warmpool

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/state"
)

type Replenisher struct {
	Interval time.Duration
	Logger   *slog.Logger
	Store    interface {
		InsertWarmPoolPod(context.Context, state.WarmPoolPod) error
	}
	Manager *Manager
}

func (r *Replenisher) Run(ctx context.Context, targets map[string]int) error {
	ticker := time.NewTicker(r.Interval)
	defer ticker.Stop()
	for {
		r.ReconcileOnce(ctx, targets)
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
		}
	}
}

func (r *Replenisher) ReconcileOnce(ctx context.Context, targets map[string]int) {
	for targetKey, targetCount := range targets {
		workspaceID, agentType := splitKey(targetKey)
		current := r.Manager.Count(workspaceID, agentType)
		for index := current; index < targetCount; index++ {
			podName := fmt.Sprintf("warm-%s-%d", sanitize(workspaceID+"-"+agentType), index)
			r.Manager.RegisterReadyPod(workspaceID, agentType, podName)
			_ = r.Store.InsertWarmPoolPod(ctx, state.WarmPoolPod{
				WorkspaceID: workspaceID,
				AgentType:   agentType,
				PodName:     podName,
				Status:      "ready",
			})
		}
	}
}

func splitKey(value string) (string, string) {
	for i := 0; i < len(value); i++ {
		if value[i] == '/' {
			return value[:i], value[i+1:]
		}
	}
	return value, ""
}

func sanitize(value string) string {
	if value == "" {
		return "default"
	}
	return value
}
