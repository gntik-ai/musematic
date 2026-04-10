package sim_manager

import (
	"context"
	"sync"
	"time"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
)

type SimulationState struct {
	SimulationID  string
	Status        string
	PodName       string
	PodPhase      string
	CreatedAt     *time.Time
	StartedAt     *time.Time
	CompletedAt   *time.Time
	ErrorMessage  string
	ResourceUsage ResourceUsage
}

type StateRegistry struct {
	items sync.Map
}

func NewStateRegistry() *StateRegistry {
	return &StateRegistry{}
}

func (r *StateRegistry) Register(state SimulationState) {
	if r == nil || state.SimulationID == "" {
		return
	}
	r.items.Store(state.SimulationID, state)
}

func (r *StateRegistry) Get(simulationID string) (SimulationState, bool) {
	if r == nil {
		return SimulationState{}, false
	}
	value, ok := r.items.Load(simulationID)
	if !ok {
		return SimulationState{}, false
	}
	state, ok := value.(SimulationState)
	return state, ok
}

func (r *StateRegistry) UpdateStatus(simulationID, status string) bool {
	state, ok := r.Get(simulationID)
	if !ok {
		return false
	}
	state.Status = status
	if status == "COMPLETED" || status == "FAILED" || status == "TERMINATED" {
		now := time.Now().UTC()
		state.CompletedAt = &now
	}
	r.Register(state)
	return true
}

func (r *StateRegistry) Delete(simulationID string) {
	if r == nil {
		return
	}
	r.items.Delete(simulationID)
}

func (r *StateRegistry) List() []SimulationState {
	if r == nil {
		return nil
	}

	states := []SimulationState{}
	r.items.Range(func(_, value any) bool {
		state, ok := value.(SimulationState)
		if ok {
			states = append(states, state)
		}
		return true
	})
	return states
}

func (r *StateRegistry) RebuildFromPodList(ctx context.Context, client kubernetes.Interface, namespace string) error {
	if r == nil || client == nil {
		return nil
	}

	pods, err := client.CoreV1().Pods(namespace).List(ctx, metav1.ListOptions{
		LabelSelector: SimulationLabelKey + "=true",
	})
	if err != nil {
		return err
	}

	for _, pod := range pods.Items {
		state := simulationStateFromPod(pod)
		if state.SimulationID != "" {
			r.Register(state)
		}
	}
	return nil
}

func simulationStateFromPod(pod corev1.Pod) SimulationState {
	createdAt := pod.CreationTimestamp.Time.UTC()
	var startedAt *time.Time
	if pod.Status.StartTime != nil {
		start := pod.Status.StartTime.Time.UTC()
		startedAt = &start
	}

	return SimulationState{
		SimulationID:  pod.Labels[SimulationIDLabelKey],
		Status:        statusFromPhase(pod),
		PodName:       pod.Name,
		PodPhase:      string(pod.Status.Phase),
		CreatedAt:     &createdAt,
		StartedAt:     startedAt,
		ResourceUsage: resourceUsageFromPod(pod),
	}
}

func resourceUsageFromPod(pod corev1.Pod) ResourceUsage {
	if len(pod.Spec.Containers) == 0 {
		return ResourceUsage{}
	}
	container := pod.Spec.Containers[0]
	return ResourceUsage{
		CPURequest:    container.Resources.Requests.Cpu().String(),
		MemoryRequest: container.Resources.Requests.Memory().String(),
		CPULimit:      container.Resources.Limits.Cpu().String(),
		MemoryLimit:   container.Resources.Limits.Memory().String(),
	}
}

func statusFromPhase(pod corev1.Pod) string {
	switch pod.Status.Phase {
	case corev1.PodRunning:
		return "RUNNING"
	case corev1.PodSucceeded:
		return "COMPLETED"
	case corev1.PodFailed:
		return "FAILED"
	default:
		return "CREATING"
	}
}
