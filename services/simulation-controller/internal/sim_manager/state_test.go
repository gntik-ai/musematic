package sim_manager

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"testing"
	"time"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/client-go/kubernetes/fake"
	k8stesting "k8s.io/client-go/testing"

	"github.com/stretchr/testify/require"
)

type recordingDeleter struct {
	names []string
	err   error
}

func (r *recordingDeleter) DeletePod(_ context.Context, podName string) error {
	if r.err != nil {
		return r.err
	}
	r.names = append(r.names, podName)
	return nil
}

func TestRebuildFromPodListRegistersSimulationPods(t *testing.T) {
	t.Parallel()

	start := metav1.NewTime(time.Now().Add(-1 * time.Minute))
	client := fake.NewSimpleClientset(&corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "sim-pod",
			Namespace: DefaultNamespace,
			Labels: map[string]string{
				SimulationLabelKey:   "true",
				SimulationIDLabelKey: "sim-1",
			},
		},
		Spec: corev1.PodSpec{
			Containers: []corev1.Container{{
				Resources: corev1.ResourceRequirements{
					Requests: corev1.ResourceList{
						corev1.ResourceCPU:    mustQuantity("250m"),
						corev1.ResourceMemory: mustQuantity("256Mi"),
					},
					Limits: corev1.ResourceList{
						corev1.ResourceCPU:    mustQuantity("250m"),
						corev1.ResourceMemory: mustQuantity("256Mi"),
					},
				},
			}},
		},
		Status: corev1.PodStatus{
			Phase:     corev1.PodRunning,
			StartTime: &start,
		},
	})

	registry := NewStateRegistry()
	require.NoError(t, registry.RebuildFromPodList(context.Background(), client, DefaultNamespace))

	state, ok := registry.Get("sim-1")
	require.True(t, ok)
	require.Equal(t, "RUNNING", state.Status)
	require.Equal(t, "sim-pod", state.PodName)
	require.Equal(t, "250m", state.ResourceUsage.CPURequest)
}

func TestOrphanScannerDeletesPodsMissingFromRegistry(t *testing.T) {
	t.Parallel()

	client := fake.NewSimpleClientset(
		&corev1.Pod{
			ObjectMeta: metav1.ObjectMeta{
				Name:      "orphan-pod",
				Namespace: DefaultNamespace,
				Labels: map[string]string{
					SimulationLabelKey:   "true",
					SimulationIDLabelKey: "sim-orphan",
				},
			},
		},
		&corev1.Pod{
			ObjectMeta: metav1.ObjectMeta{
				Name:      "tracked-pod",
				Namespace: DefaultNamespace,
				Labels: map[string]string{
					SimulationLabelKey:   "true",
					SimulationIDLabelKey: "sim-tracked",
				},
			},
		},
	)
	registry := NewStateRegistry()
	registry.Register(SimulationState{SimulationID: "sim-tracked"})
	deleter := &recordingDeleter{}
	scanner := &OrphanScanner{
		Client:    client,
		Namespace: DefaultNamespace,
		Registry:  registry,
		Pods:      deleter,
	}

	require.NoError(t, scanner.scan(context.Background()))
	require.Equal(t, []string{"orphan-pod"}, deleter.names)
}

func TestOrphanScannerRunAndErrorBranches(t *testing.T) {
	t.Parallel()

	require.NoError(t, (*OrphanScanner)(nil).Run(context.Background()))
	require.NoError(t, (&OrphanScanner{}).Run(context.Background()))

	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	err := (&OrphanScanner{
		Client:    fake.NewSimpleClientset(),
		Namespace: DefaultNamespace,
		Registry:  NewStateRegistry(),
		Interval:  time.Nanosecond,
		Logger:    slog.New(slog.NewTextHandler(io.Discard, nil)),
	}).Run(ctx)
	require.ErrorIs(t, err, context.Canceled)

	listErrClient := fake.NewSimpleClientset()
	listErrClient.PrependReactor("list", "pods", func(k8stesting.Action) (bool, runtime.Object, error) {
		return true, nil, errors.New("list failed")
	})
	require.EqualError(t, (&OrphanScanner{
		Client:    listErrClient,
		Namespace: DefaultNamespace,
		Registry:  NewStateRegistry(),
	}).scan(context.Background()), "list failed")

	deleteErr := errors.New("delete failed")
	scanner := &OrphanScanner{
		Client: fake.NewSimpleClientset(&corev1.Pod{ObjectMeta: metav1.ObjectMeta{
			Name:      "orphan-pod",
			Namespace: DefaultNamespace,
			Labels: map[string]string{
				SimulationLabelKey:   "true",
				SimulationIDLabelKey: "sim-orphan",
			},
		}}),
		Namespace: DefaultNamespace,
		Registry:  NewStateRegistry(),
		Pods:      &recordingDeleter{err: deleteErr},
		Logger:    slog.New(slog.NewTextHandler(io.Discard, nil)),
	}
	require.ErrorIs(t, scanner.scan(context.Background()), deleteErr)
}

func TestStateRegistryLifecycleHelpers(t *testing.T) {
	t.Parallel()

	registry := NewStateRegistry()
	registry.Register(SimulationState{})
	require.Empty(t, registry.List())

	registry.Register(SimulationState{SimulationID: "sim-1", Status: "CREATING"})
	require.True(t, registry.UpdateStatus("sim-1", "COMPLETED"))

	state, ok := registry.Get("sim-1")
	require.True(t, ok)
	require.Equal(t, "COMPLETED", state.Status)
	require.NotNil(t, state.CompletedAt)
	require.Len(t, registry.List(), 1)

	registry.Delete("sim-1")
	_, ok = registry.Get("sim-1")
	require.False(t, ok)
	require.False(t, registry.UpdateStatus("missing", "FAILED"))

	var nilRegistry *StateRegistry
	nilRegistry.Register(SimulationState{SimulationID: "ignored"})
	nilRegistry.Delete("ignored")
	require.Nil(t, nilRegistry.List())
	_, ok = nilRegistry.Get("ignored")
	require.False(t, ok)
}

func TestStateHelpersCoverFallbackBranches(t *testing.T) {
	t.Parallel()

	require.Equal(t, ResourceUsage{}, resourceUsageFromPod(corev1.Pod{}))

	succeeded := corev1.Pod{Status: corev1.PodStatus{Phase: corev1.PodSucceeded}}
	failed := corev1.Pod{Status: corev1.PodStatus{Phase: corev1.PodFailed}}
	pending := corev1.Pod{Status: corev1.PodStatus{Phase: corev1.PodPending}}

	require.Equal(t, "COMPLETED", statusFromPhase(succeeded))
	require.Equal(t, "FAILED", statusFromPhase(failed))
	require.Equal(t, "CREATING", statusFromPhase(pending))

	require.NoError(t, (*StateRegistry)(nil).RebuildFromPodList(context.Background(), fake.NewSimpleClientset(), DefaultNamespace))
	require.NoError(t, NewStateRegistry().RebuildFromPodList(context.Background(), nil, DefaultNamespace))

	client := fake.NewSimpleClientset(&corev1.Pod{ObjectMeta: metav1.ObjectMeta{
		Name:      "missing-id",
		Namespace: DefaultNamespace,
		Labels:    map[string]string{SimulationLabelKey: "true"},
	}})
	registry := NewStateRegistry()
	require.NoError(t, registry.RebuildFromPodList(context.Background(), client, DefaultNamespace))
	require.Empty(t, registry.List())
}

func mustQuantity(value string) resource.Quantity {
	return resource.MustParse(value)
}
