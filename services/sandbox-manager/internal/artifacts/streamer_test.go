package artifacts

import (
	"context"
	"fmt"
	"io"
	"strings"
	"testing"

	"k8s.io/client-go/rest"
)

func TestExecArchiveStreamerStreamsArchiveBytes(t *testing.T) {
	t.Parallel()

	streamer := NewExecArchiveStreamer(nil)
	streamer.Exec = func(_ context.Context, _ *rest.Config, namespace string, podName string, command []string, _ io.Reader, stdout io.Writer, _ io.Writer) error {
		if namespace != "platform-execution" || podName != "sandbox-pod" {
			t.Fatalf("unexpected exec target: %s/%s", namespace, podName)
		}
		if strings.Join(command, " ") != "sh -lc tar -czf - -C /output ." {
			t.Fatalf("unexpected command: %v", command)
		}
		_, _ = stdout.Write([]byte("archive-bytes"))
		return nil
	}

	stream, err := streamer.StreamArchive(context.Background(), "platform-execution", "sandbox-pod")
	if err != nil {
		t.Fatalf("StreamArchive() error = %v", err)
	}
	defer stream.Close()

	body, err := io.ReadAll(stream)
	if err != nil {
		t.Fatalf("ReadAll() error = %v", err)
	}
	if string(body) != "archive-bytes" {
		t.Fatalf("unexpected archive body %q", string(body))
	}
}

func TestExecArchiveStreamerReturnsExecStderr(t *testing.T) {
	t.Parallel()

	streamer := NewExecArchiveStreamer(nil)
	streamer.Exec = func(_ context.Context, _ *rest.Config, _, _ string, _ []string, _ io.Reader, _ io.Writer, stderr io.Writer) error {
		_, _ = stderr.Write([]byte("tar failed"))
		return fmt.Errorf("boom")
	}

	if _, err := streamer.StreamArchive(context.Background(), "platform-execution", "sandbox-pod"); err == nil || !strings.Contains(err.Error(), "tar failed") {
		t.Fatalf("StreamArchive() error = %v, want stderr context", err)
	}
}

func TestExecArchiveStreamerNilAndPlainExecErrors(t *testing.T) {
	t.Parallel()

	if _, err := (&ExecArchiveStreamer{}).StreamArchive(context.Background(), "platform-execution", "sandbox-pod"); err == nil {
		t.Fatal("expected nil exec streamer to fail")
	}

	streamer := NewExecArchiveStreamer(nil)
	streamer.Exec = func(_ context.Context, _ *rest.Config, _, _ string, _ []string, _ io.Reader, _ io.Writer, _ io.Writer) error {
		return fmt.Errorf("boom")
	}
	if _, err := streamer.StreamArchive(context.Background(), "platform-execution", "sandbox-pod"); err == nil || strings.Contains(err.Error(), ": ") && strings.Contains(err.Error(), "tar failed") {
		t.Fatalf("StreamArchive() error = %v", err)
	}
}
