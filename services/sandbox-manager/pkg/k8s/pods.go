package k8s

import (
	"context"
	"io"

	v1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
)

type PodClient struct {
	Client    kubernetes.Interface
	Namespace string
	DryRun    bool
}

func (p *PodClient) CreatePod(ctx context.Context, pod *v1.Pod) (*v1.Pod, error) {
	if p.DryRun {
		copy := pod.DeepCopy()
		copy.Status.Phase = v1.PodRunning
		return copy, nil
	}
	return p.Client.CoreV1().Pods(p.Namespace).Create(ctx, pod, metav1.CreateOptions{})
}

func (p *PodClient) GetPod(ctx context.Context, name string) (*v1.Pod, error) {
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

func (p *PodClient) GetPodLogs(ctx context.Context, name string, follow bool) (io.ReadCloser, error) {
	req := p.Client.CoreV1().Pods(p.Namespace).GetLogs(name, &v1.PodLogOptions{Follow: follow})
	return req.Stream(ctx)
}
