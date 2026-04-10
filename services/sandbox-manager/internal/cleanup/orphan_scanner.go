package cleanup

import (
	"context"
	"time"

	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/sandbox"
	v1 "k8s.io/api/core/v1"
)

type PodInventory interface {
	ListPodsByLabel(context.Context, string) ([]v1.Pod, error)
	DeletePod(context.Context, string, int64) error
}

type OrphanScanner struct {
	Pods     PodInventory
	Manager  *sandbox.Manager
	Interval time.Duration
}

func (o *OrphanScanner) Run(ctx context.Context) error {
	if o == nil || o.Pods == nil || o.Manager == nil {
		return nil
	}
	if err := o.scan(ctx); err != nil {
		return err
	}
	ticker := time.NewTicker(o.Interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
			if err := o.scan(ctx); err != nil {
				return err
			}
		}
	}
}

func (o *OrphanScanner) scan(ctx context.Context) error {
	pods, err := o.Pods.ListPodsByLabel(ctx, "managed-by=sandbox-manager")
	if err != nil {
		return err
	}
	for _, pod := range pods {
		id := pod.Labels["sandbox_id"]
		if id == "" || o.Manager.HasSandbox(id) {
			continue
		}
		if err := o.Pods.DeletePod(ctx, pod.Name, 5); err != nil {
			return err
		}
	}
	return nil
}
