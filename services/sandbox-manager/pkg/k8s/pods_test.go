package k8s

import (
	"context"
	"testing"

	v1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes/fake"
)

func TestPodClientCRUD(t *testing.T) {
	t.Parallel()

	client := &PodClient{
		Client:    fake.NewSimpleClientset(),
		Namespace: "platform-execution",
	}
	created, err := client.CreatePod(context.Background(), &v1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name:   "sandbox-1",
			Labels: map[string]string{"app": "sandbox"},
		},
	})
	if err != nil {
		t.Fatalf("CreatePod() error = %v", err)
	}
	if created.GetName() != "sandbox-1" {
		t.Fatalf("unexpected pod name %q", created.GetName())
	}

	got, err := client.GetPod(context.Background(), "sandbox-1")
	if err != nil {
		t.Fatalf("GetPod() error = %v", err)
	}
	if got.GetName() != "sandbox-1" {
		t.Fatalf("unexpected pod %q", got.GetName())
	}

	items, err := client.ListPodsByLabel(context.Background(), "app=sandbox")
	if err != nil {
		t.Fatalf("ListPodsByLabel() error = %v", err)
	}
	if len(items) != 1 {
		t.Fatalf("expected 1 pod, got %d", len(items))
	}

	if err := client.DeletePod(context.Background(), "sandbox-1", 0); err != nil {
		t.Fatalf("DeletePod() error = %v", err)
	}
}

func TestPodClientDryRunAndExecRequiresConfig(t *testing.T) {
	t.Parallel()

	client := &PodClient{
		Namespace: "platform-execution",
		DryRun:    true,
	}
	pod, err := client.CreatePod(context.Background(), &v1.Pod{ObjectMeta: metav1.ObjectMeta{Name: "sandbox-dry-run"}})
	if err != nil {
		t.Fatalf("CreatePod() error = %v", err)
	}
	if pod.Status.Phase != v1.PodRunning {
		t.Fatalf("unexpected dry-run phase %s", pod.Status.Phase)
	}
	if err := client.DeletePod(context.Background(), "sandbox-dry-run", 5); err != nil {
		t.Fatalf("DeletePod() error = %v", err)
	}

	if err := ExecInPod(context.Background(), nil, "platform-execution", "sandbox-dry-run", []string{"python3"}, nil, nil, nil); err == nil {
		t.Fatal("expected ExecInPod() to reject nil rest config")
	}
}
