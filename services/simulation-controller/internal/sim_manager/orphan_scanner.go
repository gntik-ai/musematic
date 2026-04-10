package sim_manager

import (
	"context"
	"log/slog"
	"time"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
)

type PodDeleter interface {
	DeletePod(ctx context.Context, podName string) error
}

type OrphanScanner struct {
	Client    kubernetes.Interface
	Namespace string
	Registry  *StateRegistry
	Pods      PodDeleter
	Interval  time.Duration
	Logger    *slog.Logger
}

func (s *OrphanScanner) Run(ctx context.Context) error {
	if s == nil || s.Client == nil || s.Registry == nil {
		return nil
	}

	interval := s.Interval
	if interval <= 0 {
		interval = 60 * time.Second
	}

	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	for {
		if err := s.scan(ctx); err != nil && s.Logger != nil {
			s.Logger.Error("orphan scan failed", "error", err)
		}

		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
		}
	}
}

func (s *OrphanScanner) scan(ctx context.Context) error {
	pods, err := s.Client.CoreV1().Pods(s.Namespace).List(ctx, metav1.ListOptions{
		LabelSelector: SimulationLabelKey + "=true",
	})
	if err != nil {
		return err
	}

	for _, pod := range pods.Items {
		simulationID := pod.Labels[SimulationIDLabelKey]
		if simulationID == "" {
			continue
		}
		if _, ok := s.Registry.Get(simulationID); ok {
			continue
		}
		if s.Pods != nil {
			if err := s.Pods.DeletePod(ctx, pod.Name); err != nil {
				return err
			}
		}
		if s.Logger != nil {
			s.Logger.Info("deleted orphan simulation pod", "pod_name", pod.Name, "simulation_id", simulationID)
		}
	}

	return nil
}
