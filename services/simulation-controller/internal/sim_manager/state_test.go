package sim_manager

import (
	"context"
	"testing"
	"time"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes/fake"

	"github.com/stretchr/testify/require"
)

type recordingDeleter struct {
	names []string
}

func (r *recordingDeleter) DeletePod(_ context.Context, podName string) error {
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

func mustQuantity(value string) resource.Quantity {
	return resource.MustParse(value)
}
