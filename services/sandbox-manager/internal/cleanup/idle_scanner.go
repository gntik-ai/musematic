package cleanup

import (
	"context"
	"time"

	sandboxv1 "github.com/andrea-mucci/musematic/services/sandbox-manager/api/grpc/v1"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/sandbox"
)

type IdleScanner struct {
	Manager     *sandbox.Manager
	IdleTimeout time.Duration
	Interval    time.Duration
}

func (i *IdleScanner) Run(ctx context.Context) error {
	if i == nil || i.Manager == nil {
		return nil
	}
	ticker := time.NewTicker(i.Interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
			now := time.Now().UTC()
			for _, entry := range i.Manager.List() {
				if entry.State != sandboxv1.SandboxState_SANDBOX_STATE_READY && entry.State != sandboxv1.SandboxState_SANDBOX_STATE_COMPLETED {
					continue
				}
				if entry.LastActivityAt.Add(i.IdleTimeout).Before(now) {
					_ = i.Manager.MarkTerminated(ctx, entry.SandboxID, 5)
				}
			}
		}
	}
}
