package artifacts

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"strings"

	k8spkg "github.com/andrea-mucci/musematic/services/sandbox-manager/pkg/k8s"
	"k8s.io/client-go/rest"
)

type ExecArchiveFunc func(context.Context, *rest.Config, string, string, []string, io.Reader, io.Writer, io.Writer) error

type ExecArchiveStreamer struct {
	RestConfig *rest.Config
	Exec       ExecArchiveFunc
}

func NewExecArchiveStreamer(cfg *rest.Config) *ExecArchiveStreamer {
	return &ExecArchiveStreamer{
		RestConfig: cfg,
		Exec:       k8spkg.ExecInPod,
	}
}

func (s *ExecArchiveStreamer) StreamArchive(ctx context.Context, namespace string, podName string) (io.ReadCloser, error) {
	if s == nil || s.Exec == nil {
		return nil, fmt.Errorf("archive exec streamer is not configured")
	}

	var stdout bytes.Buffer
	var stderr bytes.Buffer
	command := []string{"sh", "-lc", "tar -czf - -C /output ."}
	if err := s.Exec(ctx, s.RestConfig, namespace, podName, command, nil, &stdout, &stderr); err != nil {
		if message := strings.TrimSpace(stderr.String()); message != "" {
			return nil, fmt.Errorf("stream archive from pod: %w: %s", err, message)
		}
		return nil, fmt.Errorf("stream archive from pod: %w", err)
	}

	return io.NopCloser(bytes.NewReader(stdout.Bytes())), nil
}
