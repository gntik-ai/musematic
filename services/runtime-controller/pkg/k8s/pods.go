package k8s

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"

	runtimev1 "github.com/andrea-mucci/musematic/services/runtime-controller/api/grpc/v1"
	v1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/kubernetes/scheme"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/remotecommand"
)

type PodClient struct {
	Client     kubernetes.Interface
	RestConfig *rest.Config
	Namespace  string
	DryRun     bool
}

func (p *PodClient) CreatePod(ctx context.Context, pod *v1.Pod) (*v1.Pod, error) {
	if p.DryRun {
		return pod.DeepCopy(), nil
	}
	return p.Client.CoreV1().Pods(p.Namespace).Create(ctx, pod, metav1.CreateOptions{})
}

func (p *PodClient) GetPod(ctx context.Context, name string) (*v1.Pod, error) {
	if p.DryRun {
		return &v1.Pod{ObjectMeta: metav1.ObjectMeta{Name: name, Namespace: p.Namespace}, Status: v1.PodStatus{Phase: v1.PodRunning}}, nil
	}
	return p.Client.CoreV1().Pods(p.Namespace).Get(ctx, name, metav1.GetOptions{})
}

func (p *PodClient) ListPodsByLabel(ctx context.Context, selector string) ([]v1.Pod, error) {
	list, err := p.Client.CoreV1().Pods(p.Namespace).List(ctx, metav1.ListOptions{LabelSelector: selector})
	if err != nil {
		return nil, err
	}
	return list.Items, nil
}

func (p *PodClient) DeletePod(ctx context.Context, name string, gracePeriodSeconds int64) error {
	if p.DryRun {
		return nil
	}
	return p.Client.CoreV1().Pods(p.Namespace).Delete(ctx, name, metav1.DeleteOptions{GracePeriodSeconds: &gracePeriodSeconds})
}

func (p *PodClient) GetPodLogs(ctx context.Context, name string) ([]byte, error) {
	if p.DryRun {
		return []byte("dry-run pod logs for " + name), nil
	}
	req := p.Client.CoreV1().Pods(p.Namespace).GetLogs(name, &v1.PodLogOptions{})
	stream, err := req.Stream(ctx)
	if err != nil {
		return nil, err
	}
	defer stream.Close()
	return io.ReadAll(stream)
}

func (p *PodClient) ExecInPod(ctx context.Context, name string, command []string) ([]byte, error) {
	if p.DryRun {
		return nil, nil
	}
	req := p.Client.CoreV1().RESTClient().
		Post().
		Resource("pods").
		Name(name).
		Namespace(p.Namespace).
		SubResource("exec").
		VersionedParams(&v1.PodExecOptions{
			Container: "agent-runtime",
			Command:   command,
			Stdout:    true,
			Stderr:    true,
		}, scheme.ParameterCodec)
	executor, err := remotecommand.NewSPDYExecutor(p.RestConfig, "POST", req.URL())
	if err != nil {
		return nil, err
	}
	var stdout, stderr bytes.Buffer
	if err := executor.StreamWithContext(ctx, remotecommand.StreamOptions{Stdout: &stdout, Stderr: &stderr}); err != nil {
		if stderr.Len() > 0 {
			return nil, fmt.Errorf("%w: %s", err, stderr.String())
		}
		return nil, err
	}
	return stdout.Bytes(), nil
}

func (p *PodClient) PrepareWarmPod(ctx context.Context, name string, contract *runtimev1.RuntimeContract) error {
	if p.DryRun {
		return nil
	}
	correlation := contract.GetCorrelationContext()
	patch := map[string]any{
		"metadata": map[string]any{
			"labels": map[string]string{
				"execution_id": correlation.GetExecutionId(),
				"workspace_id": correlation.GetWorkspaceId(),
				"agent_fqn":    contract.GetAgentRevision(),
				"warm_pool":    "dispatched",
				"managed_by":   "runtime-controller",
			},
		},
		"spec": map[string]any{
			"containers": []map[string]any{{
				"name": "agent-runtime",
				"env": []map[string]string{
					{"name": "EXECUTION_ID", "value": correlation.GetExecutionId()},
					{"name": "WORKSPACE_ID", "value": correlation.GetWorkspaceId()},
				},
			}},
		},
	}
	body, err := json.Marshal(patch)
	if err != nil {
		return err
	}
	_, err = p.Client.CoreV1().Pods(p.Namespace).Patch(ctx, name, types.StrategicMergePatchType, body, metav1.PatchOptions{})
	return err
}
