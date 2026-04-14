package k8s

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"net/url"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	otelcodes "go.opentelemetry.io/otel/codes"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/client-go/kubernetes/scheme"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/remotecommand"
)

var execTracer = otel.Tracer("sandbox-manager/pkg/k8s")

type execStreamer interface {
	StreamWithContext(context.Context, remotecommand.StreamOptions) error
}

var (
	buildExecURL = defaultBuildExecURL
	newExecutor  = func(cfg *rest.Config, method string, execURL *url.URL) (execStreamer, error) {
		return remotecommand.NewSPDYExecutor(cfg, method, execURL)
	}
)

func ExecInPod(
	ctx context.Context,
	cfg *rest.Config,
	namespace string,
	podName string,
	command []string,
	stdin io.Reader,
	stdout io.Writer,
	stderr io.Writer,
) error {
	ctx, span := execTracer.Start(ctx, "ExecInPod")
	span.SetAttributes(
		attribute.String("k8s.namespace", namespace),
		attribute.String("k8s.pod.name", podName),
		attribute.Int("command.arg_count", len(command)),
	)
	if len(command) > 0 {
		span.SetAttributes(attribute.String("command.entrypoint", command[0]))
	}
	defer span.End()

	if cfg == nil {
		err := fmt.Errorf("rest config is required")
		span.RecordError(err)
		span.SetStatus(otelcodes.Error, err.Error())
		return err
	}
	if stdout == nil {
		stdout = &bytes.Buffer{}
	}
	if stderr == nil {
		stderr = &bytes.Buffer{}
	}
	execURL, err := buildExecURL(cfg, namespace, podName, command, stdin != nil)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(otelcodes.Error, err.Error())
		return err
	}
	executor, err := newExecutor(cfg, "POST", execURL)
	if err != nil {
		err = fmt.Errorf("create spdy executor: %w", err)
		span.RecordError(err)
		span.SetStatus(otelcodes.Error, err.Error())
		return err
	}
	if err := executor.StreamWithContext(ctx, remotecommand.StreamOptions{
		Stdin:  stdin,
		Stdout: stdout,
		Stderr: stderr,
		Tty:    false,
	}); err != nil {
		span.RecordError(err)
		span.SetStatus(otelcodes.Error, err.Error())
		return err
	}
	return nil
}

func defaultBuildExecURL(cfg *rest.Config, namespace string, podName string, command []string, hasStdin bool) (*url.URL, error) {
	coreCfg := rest.CopyConfig(cfg)
	coreCfg.APIPath = "/api"
	coreCfg.GroupVersion = &corev1.SchemeGroupVersion
	coreCfg.NegotiatedSerializer = scheme.Codecs.WithoutConversion()
	restClient, err := rest.RESTClientFor(coreCfg)
	if err != nil {
		return nil, fmt.Errorf("build rest client: %w", err)
	}
	return restClient.
		Post().
		Namespace(namespace).
		Resource("pods").
		Name(podName).
		SubResource("exec").
		VersionedParams(&corev1.PodExecOptions{
			Command: command,
			Stdin:   hasStdin,
			Stdout:  true,
			Stderr:  true,
			TTY:     false,
		}, scheme.ParameterCodec).
		URL(), nil
}
