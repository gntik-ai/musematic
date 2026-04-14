package k8s

import (
	"context"
	"io"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	otelcodes "go.opentelemetry.io/otel/codes"
	v1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
)

type PodClient struct {
	Client    kubernetes.Interface
	Namespace string
	DryRun    bool
}

var podTracer = otel.Tracer("sandbox-manager/pkg/k8s")

var streamPodLogs = func(ctx context.Context, request *rest.Request) (io.ReadCloser, error) {
	return request.Stream(ctx)
}

func (p *PodClient) CreatePod(ctx context.Context, pod *v1.Pod) (*v1.Pod, error) {
	ctx, span := podTracer.Start(ctx, "PodClient/CreatePod")
	span.SetAttributes(
		attribute.String("k8s.namespace", p.Namespace),
		attribute.String("k8s.pod.name", pod.GetName()),
		attribute.Bool("k8s.dry_run", p.DryRun),
	)
	defer span.End()

	if p.DryRun {
		copy := pod.DeepCopy()
		copy.Status.Phase = v1.PodRunning
		return copy, nil
	}
	created, err := p.Client.CoreV1().Pods(p.Namespace).Create(ctx, pod, metav1.CreateOptions{})
	if err != nil {
		span.RecordError(err)
		span.SetStatus(otelcodes.Error, err.Error())
		return nil, err
	}
	return created, nil
}

func (p *PodClient) GetPod(ctx context.Context, name string) (*v1.Pod, error) {
	ctx, span := podTracer.Start(ctx, "PodClient/GetPod")
	span.SetAttributes(attribute.String("k8s.namespace", p.Namespace), attribute.String("k8s.pod.name", name))
	defer span.End()

	pod, err := p.Client.CoreV1().Pods(p.Namespace).Get(ctx, name, metav1.GetOptions{})
	if err != nil {
		span.RecordError(err)
		span.SetStatus(otelcodes.Error, err.Error())
		return nil, err
	}
	return pod, nil
}

func (p *PodClient) ListPodsByLabel(ctx context.Context, selector string) ([]v1.Pod, error) {
	ctx, span := podTracer.Start(ctx, "PodClient/ListPodsByLabel")
	span.SetAttributes(attribute.String("k8s.namespace", p.Namespace), attribute.String("k8s.selector", selector))
	defer span.End()

	list, err := p.Client.CoreV1().Pods(p.Namespace).List(ctx, metav1.ListOptions{LabelSelector: selector})
	if err != nil {
		span.RecordError(err)
		span.SetStatus(otelcodes.Error, err.Error())
		return nil, err
	}
	return list.Items, nil
}

func (p *PodClient) DeletePod(ctx context.Context, name string, gracePeriodSeconds int64) error {
	ctx, span := podTracer.Start(ctx, "PodClient/DeletePod")
	span.SetAttributes(
		attribute.String("k8s.namespace", p.Namespace),
		attribute.String("k8s.pod.name", name),
		attribute.Int64("k8s.grace_period_seconds", gracePeriodSeconds),
		attribute.Bool("k8s.dry_run", p.DryRun),
	)
	defer span.End()

	if p.DryRun {
		return nil
	}
	if err := p.Client.CoreV1().Pods(p.Namespace).Delete(ctx, name, metav1.DeleteOptions{GracePeriodSeconds: &gracePeriodSeconds}); err != nil {
		span.RecordError(err)
		span.SetStatus(otelcodes.Error, err.Error())
		return err
	}
	return nil
}

func (p *PodClient) GetPodLogs(ctx context.Context, name string, follow bool) (io.ReadCloser, error) {
	req := p.Client.CoreV1().Pods(p.Namespace).GetLogs(name, &v1.PodLogOptions{Follow: follow})
	return streamPodLogs(ctx, req)
}
