package k8s

import (
	"bytes"
	"context"
	"errors"
	"io"
	"net/url"
	"strings"
	"testing"

	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/remotecommand"
)

type fakeExecStreamer struct {
	err     error
	options remotecommand.StreamOptions
}

func (f *fakeExecStreamer) StreamWithContext(_ context.Context, options remotecommand.StreamOptions) error {
	f.options = options
	return f.err
}

func TestDefaultBuildExecURL(t *testing.T) {
	t.Parallel()

	execURL, err := defaultBuildExecURL(&rest.Config{Host: "https://cluster.example"}, "platform-execution", "sandbox-1", []string{"python3", "-c", "print(1)"}, true)
	if err != nil {
		t.Fatalf("defaultBuildExecURL() error = %v", err)
	}
	if got := execURL.Path; got != "/api/v1/namespaces/platform-execution/pods/sandbox-1/exec" {
		t.Fatalf("defaultBuildExecURL() path = %q", got)
	}
	query := execURL.Query()
	if query.Get("stdin") != "true" || query.Get("stdout") != "true" || query.Get("stderr") != "true" {
		t.Fatalf("defaultBuildExecURL() query = %q", execURL.RawQuery)
	}
}

func TestDefaultBuildExecURLRequiresHost(t *testing.T) {
	t.Parallel()

	if _, err := defaultBuildExecURL(&rest.Config{Host: "://bad host"}, "ns", "pod", []string{"python3"}, false); err == nil {
		t.Fatal("expected defaultBuildExecURL() to fail without host")
	}
}

func TestExecInPodPropagatesBuildURLError(t *testing.T) {
	originalBuild := buildExecURL
	originalExecutor := newExecutor
	t.Cleanup(func() {
		buildExecURL = originalBuild
		newExecutor = originalExecutor
	})

	expectedErr := errors.New("url boom")
	buildExecURL = func(*rest.Config, string, string, []string, bool) (*url.URL, error) {
		return nil, expectedErr
	}

	if err := ExecInPod(context.Background(), &rest.Config{Host: "https://cluster.example"}, "ns", "pod", []string{"python3"}, nil, nil, nil); !errors.Is(err, expectedErr) {
		t.Fatalf("ExecInPod() error = %v, want %v", err, expectedErr)
	}
}

func TestExecInPodPropagatesExecutorCreationError(t *testing.T) {
	originalBuild := buildExecURL
	originalExecutor := newExecutor
	t.Cleanup(func() {
		buildExecURL = originalBuild
		newExecutor = originalExecutor
	})

	expectedErr := errors.New("spdy boom")
	buildExecURL = func(*rest.Config, string, string, []string, bool) (*url.URL, error) {
		return &url.URL{Scheme: "https", Host: "cluster.example"}, nil
	}
	newExecutor = func(*rest.Config, string, *url.URL) (execStreamer, error) {
		return nil, expectedErr
	}

	if err := ExecInPod(context.Background(), &rest.Config{Host: "https://cluster.example"}, "ns", "pod", []string{"python3"}, nil, nil, nil); err == nil || !strings.Contains(err.Error(), expectedErr.Error()) {
		t.Fatalf("ExecInPod() error = %v", err)
	}
}

func TestExecInPodPropagatesStreamError(t *testing.T) {
	originalBuild := buildExecURL
	originalExecutor := newExecutor
	t.Cleanup(func() {
		buildExecURL = originalBuild
		newExecutor = originalExecutor
	})

	expectedErr := errors.New("stream boom")
	streamer := &fakeExecStreamer{err: expectedErr}
	buildExecURL = func(*rest.Config, string, string, []string, bool) (*url.URL, error) {
		return &url.URL{Scheme: "https", Host: "cluster.example"}, nil
	}
	newExecutor = func(*rest.Config, string, *url.URL) (execStreamer, error) {
		return streamer, nil
	}

	var stdout bytes.Buffer
	var stderr bytes.Buffer
	if err := ExecInPod(context.Background(), &rest.Config{Host: "https://cluster.example"}, "ns", "pod", []string{"python3"}, nil, &stdout, &stderr); !errors.Is(err, expectedErr) {
		t.Fatalf("ExecInPod() error = %v, want %v", err, expectedErr)
	}
}

func TestExecInPodStreamsWithProvidedIO(t *testing.T) {
	originalBuild := buildExecURL
	originalExecutor := newExecutor
	t.Cleanup(func() {
		buildExecURL = originalBuild
		newExecutor = originalExecutor
	})

	streamer := &fakeExecStreamer{}
	buildExecURL = func(*rest.Config, string, string, []string, bool) (*url.URL, error) {
		return &url.URL{Scheme: "https", Host: "cluster.example"}, nil
	}
	newExecutor = func(*rest.Config, string, *url.URL) (execStreamer, error) {
		return streamer, nil
	}

	stdin := io.NopCloser(strings.NewReader("print(1)"))
	var stdout bytes.Buffer
	if err := ExecInPod(context.Background(), &rest.Config{Host: "https://cluster.example"}, "ns", "pod", []string{"python3"}, stdin, &stdout, nil); err != nil {
		t.Fatalf("ExecInPod() error = %v", err)
	}
	if streamer.options.Stdin == nil || streamer.options.Stdout == nil || streamer.options.Stderr == nil {
		t.Fatalf("expected stream options to be populated: %+v", streamer.options)
	}
}
