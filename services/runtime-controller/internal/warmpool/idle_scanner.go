package warmpool

import (
	"context"
	"log/slog"
	"time"

	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/state"
	"github.com/google/uuid"
)

type IdleScanner struct {
	Interval    time.Duration
	IdleTimeout time.Duration
	Logger      *slog.Logger
	Pods        interface {
		DeletePod(context.Context, string, int64) error
	}
	Manager *Manager
	Store   interface {
		ListWarmPoolPodsByStatus(context.Context, string) ([]state.WarmPoolPod, error)
		UpdateWarmPoolPodStatus(context.Context, string, string, *uuid.UUID) error
	}
}

func (s *IdleScanner) Run(ctx context.Context) error {
	ticker := time.NewTicker(s.Interval)
	defer ticker.Stop()
	for {
		if err := s.ScanOnce(ctx); err != nil && s.Logger != nil {
			s.Logger.Error("warm pool idle scan failed", "error", err)
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
		}
	}
}

func (s *IdleScanner) ScanOnce(ctx context.Context) error {
	pods, err := s.Store.ListWarmPoolPodsByStatus(ctx, "ready")
	if err != nil {
		return err
	}
	cutoff := time.Now().Add(-s.IdleTimeout)
	for _, pod := range pods {
		if pod.IdleSince != nil && pod.IdleSince.Before(cutoff) {
			if s.Pods != nil {
				_ = s.Pods.DeletePod(ctx, pod.PodName, 0)
			}
			_ = s.Store.UpdateWarmPoolPodStatus(ctx, pod.PodName, "recycling", nil)
			if s.Manager != nil {
				s.Manager.RemoveReadyPod(pod.WorkspaceID, pod.AgentType, pod.PodName)
			}
		}
	}
	return nil
}
