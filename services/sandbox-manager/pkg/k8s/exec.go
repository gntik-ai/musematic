package k8s

import (
	"bytes"
	"context"
	"fmt"
	"io"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/client-go/kubernetes/scheme"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/remotecommand"
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
	if cfg == nil {
		return fmt.Errorf("rest config is required")
	}
	if stdout == nil {
		stdout = &bytes.Buffer{}
	}
	if stderr == nil {
		stderr = &bytes.Buffer{}
	}
	coreCfg := rest.CopyConfig(cfg)
	coreCfg.APIPath = "/api"
	coreCfg.GroupVersion = &corev1.SchemeGroupVersion
	coreCfg.NegotiatedSerializer = scheme.Codecs.WithoutConversion()
	restClient, err := rest.RESTClientFor(coreCfg)
	if err != nil {
		return fmt.Errorf("build rest client: %w", err)
	}
	execURL := restClient.
		Post().
		Namespace(namespace).
		Resource("pods").
		Name(podName).
		SubResource("exec").
		VersionedParams(&corev1.PodExecOptions{
			Command: command,
			Stdin:   stdin != nil,
			Stdout:  true,
			Stderr:  true,
			TTY:     false,
		}, scheme.ParameterCodec).
		URL()
	executor, err := remotecommand.NewSPDYExecutor(cfg, "POST", execURL)
	if err != nil {
		return fmt.Errorf("create spdy executor: %w", err)
	}
	return executor.StreamWithContext(ctx, remotecommand.StreamOptions{
		Stdin:  stdin,
		Stdout: stdout,
		Stderr: stderr,
		Tty:    false,
	})
}
