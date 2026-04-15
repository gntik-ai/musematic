package reconciler

import (
	"context"
	"log/slog"
	"time"

	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/events"
	"github.com/andrea-mucci/musematic/services/runtime-controller/pkg/metrics"
)

type Reconciler struct {
	Interval time.Duration
	Store    interface {
		RuntimeLister
		EventRecorder
	}
	Pods    PodLister
	Emitter *events.EventEmitter
	Fanout  *events.FanoutRegistry
	Logger  *slog.Logger
	Metrics *metrics.Registry
}

func (r *Reconciler) Run(ctx context.Context) error {
	ticker := time.NewTicker(r.Interval)
	defer ticker.Stop()
	for {
		if err := r.RunOnce(ctx); err != nil && r.Logger != nil {
			r.Logger.Error("reconciliation cycle failed", "error", err)
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
		}
	}
}

func (r *Reconciler) RunOnce(ctx context.Context) error {
	start := time.Now()
	report, err := DetectDrift(ctx, r.Store, r.Pods)
	if err != nil {
		return err
	}
	if err := ApplyRepairs(ctx, report, r.Store, r.Pods, r.Store, r.Emitter, r.Fanout, r.Logger); err != nil {
		return err
	}
	if r.Metrics != nil {
		active := len(report.Missing) + len(report.Mismatches)
		r.Metrics.SetActiveRuntimes(int64(active))
		r.Metrics.ObserveReconciliationDuration(time.Since(start))
	}
	return nil
}
