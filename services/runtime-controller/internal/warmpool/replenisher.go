package warmpool

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/state"
	v1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

type PodCreator interface {
	CreatePod(context.Context, *v1.Pod) (*v1.Pod, error)
	GetPod(context.Context, string) (*v1.Pod, error)
}

type Replenisher struct {
	Interval time.Duration
	Logger   *slog.Logger
	Store    interface {
		InsertWarmPoolPod(context.Context, state.WarmPoolPod) error
	}
	Manager   *Manager
	Pods      PodCreator
	Namespace string
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
			status := "ready"
			if r.Pods != nil {
				status = "warming"
				if _, err := r.Pods.CreatePod(ctx, buildWarmPod(podName, namespaceOrDefault(r.Namespace), workspaceID, agentType)); err != nil {
					if r.Logger != nil {
						r.Logger.Error("create warm pool pod", "pod", podName, "error", err)
					}
					continue
				}
				if pod, err := r.Pods.GetPod(ctx, podName); err == nil && pod.Status.Phase == v1.PodRunning {
					status = "ready"
				}
			}
			if status == "ready" {
				r.Manager.RegisterReadyPod(workspaceID, agentType, podName)
			}
			_ = r.Store.InsertWarmPoolPod(ctx, state.WarmPoolPod{
				WorkspaceID:  workspaceID,
				AgentType:    agentType,
				PodName:      podName,
				PodNamespace: namespaceOrDefault(r.Namespace),
				Status:       status,
			})
		}
	}
}

func buildWarmPod(podName string, namespace string, workspaceID string, agentType string) *v1.Pod {
	return &v1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name:      podName,
			Namespace: namespace,
			Labels: map[string]string{
				"managed_by":   "runtime-controller",
				"warm_pool":    "warming",
				"workspace_id": workspaceID,
				"agent_type":   agentType,
			},
		},
		Spec: v1.PodSpec{
			RestartPolicy: v1.RestartPolicyNever,
			Containers: []v1.Container{{
				Name:  "agent-runtime",
				Image: "ghcr.io/andrea-mucci/musematic-agent-runtime:latest",
				Env: []v1.EnvVar{
					{Name: "WARM_POOL", Value: "true"},
					{Name: "WORKSPACE_ID", Value: workspaceID},
					{Name: "AGENT_TYPE", Value: agentType},
				},
			}},
		},
	}
}

func namespaceOrDefault(namespace string) string {
	if namespace == "" {
		return "platform-execution"
	}
	return namespace
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
