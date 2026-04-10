package reconciler

import (
	"context"

	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/state"
	v1 "k8s.io/api/core/v1"
)

type DriftItem struct {
	Runtime state.RuntimeRecord
	Pod     *v1.Pod
	Reason  string
}

type DriftReport struct {
	Orphans    []v1.Pod
	Missing    []DriftItem
	Mismatches []DriftItem
}

type RuntimeLister interface {
	ListActiveRuntimes(context.Context) ([]state.RuntimeRecord, error)
	UpdateRuntimeState(context.Context, string, string, string) error
}

type PodLister interface {
	ListPodsByLabel(context.Context, string) ([]v1.Pod, error)
	DeletePod(context.Context, string, int64) error
}

func DetectDrift(ctx context.Context, store RuntimeLister, pods PodLister) (DriftReport, error) {
	runtimes, err := store.ListActiveRuntimes(ctx)
	if err != nil {
		return DriftReport{}, err
	}
	podList, err := pods.ListPodsByLabel(ctx, "managed_by=runtime-controller")
	if err != nil {
		return DriftReport{}, err
	}
	report := DriftReport{}
	byExecution := map[string]state.RuntimeRecord{}
	byPodName := map[string]v1.Pod{}
	for _, runtime := range runtimes {
		byExecution[runtime.ExecutionID] = runtime
	}
	for _, pod := range podList {
		byPodName[pod.Labels["execution_id"]] = pod
		if _, ok := byExecution[pod.Labels["execution_id"]]; !ok {
			report.Orphans = append(report.Orphans, pod)
		}
	}
	for _, runtime := range runtimes {
		pod, ok := byPodName[runtime.ExecutionID]
		if !ok {
			report.Missing = append(report.Missing, DriftItem{Runtime: runtime, Reason: "pod_disappeared"})
			continue
		}
		derived := stateFromPodPhase(pod.Status.Phase)
		if derived != "" && derived != runtime.State {
			podCopy := pod.DeepCopy()
			report.Mismatches = append(report.Mismatches, DriftItem{Runtime: runtime, Pod: podCopy, Reason: derived})
		}
	}
	return report, nil
}

func stateFromPodPhase(phase v1.PodPhase) string {
	switch phase {
	case v1.PodPending:
		return "pending"
	case v1.PodRunning:
		return "running"
	case v1.PodSucceeded:
		return "stopped"
	case v1.PodFailed:
		return "failed"
	default:
		return ""
	}
}
