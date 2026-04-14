package k8s

import (
	"context"
	"errors"
	"io"
	"strings"
	"testing"

	v1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/client-go/kubernetes/fake"
	"k8s.io/client-go/rest"
	k8stesting "k8s.io/client-go/testing"
)

func TestPodClientCRUDPropagatesErrors(t *testing.T) {
	t.Parallel()

	expectedErr := errors.New("k8s boom")
	clientset := fake.NewSimpleClientset()
	clientset.PrependReactor("create", "pods", func(k8stesting.Action) (bool, runtime.Object, error) {
		return true, nil, expectedErr
	})
	clientset.PrependReactor("get", "pods", func(k8stesting.Action) (bool, runtime.Object, error) {
		return true, nil, expectedErr
	})
	clientset.PrependReactor("list", "pods", func(k8stesting.Action) (bool, runtime.Object, error) {
		return true, nil, expectedErr
	})
	clientset.PrependReactor("delete", "pods", func(k8stesting.Action) (bool, runtime.Object, error) {
		return true, nil, expectedErr
	})

	client := &PodClient{Client: clientset, Namespace: "platform-execution"}
	if _, err := client.CreatePod(context.Background(), &v1.Pod{}); !errors.Is(err, expectedErr) {
		t.Fatalf("CreatePod() error = %v, want %v", err, expectedErr)
	}
	if _, err := client.GetPod(context.Background(), "sandbox-1"); !errors.Is(err, expectedErr) {
		t.Fatalf("GetPod() error = %v, want %v", err, expectedErr)
	}
	if _, err := client.ListPodsByLabel(context.Background(), "app=sandbox"); !errors.Is(err, expectedErr) {
		t.Fatalf("ListPodsByLabel() error = %v, want %v", err, expectedErr)
	}
	if err := client.DeletePod(context.Background(), "sandbox-1", 5); !errors.Is(err, expectedErr) {
		t.Fatalf("DeletePod() error = %v, want %v", err, expectedErr)
	}
}

func TestPodClientGetPodLogs(t *testing.T) {
	t.Parallel()

	originalStream := streamPodLogs
	t.Cleanup(func() { streamPodLogs = originalStream })

	streamPodLogs = func(context.Context, *rest.Request) (io.ReadCloser, error) {
		return io.NopCloser(strings.NewReader("log line")), nil
	}

	client := &PodClient{Client: fake.NewSimpleClientset(), Namespace: "platform-execution"}
	stream, err := client.GetPodLogs(context.Background(), "sandbox-1", true)
	if err != nil {
		t.Fatalf("GetPodLogs() error = %v", err)
	}
	defer stream.Close()

	body, err := io.ReadAll(stream)
	if err != nil {
		t.Fatalf("ReadAll() error = %v", err)
	}
	if string(body) != "log line" {
		t.Fatalf("unexpected log body %q", string(body))
	}
}
