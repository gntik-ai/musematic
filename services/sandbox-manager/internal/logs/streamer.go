package logs

import (
	"bufio"
	"context"
	"io"

	sandboxv1 "github.com/andrea-mucci/musematic/services/sandbox-manager/api/grpc/v1"
	"google.golang.org/protobuf/types/known/timestamppb"
)

type LogClient interface {
	GetPodLogs(context.Context, string, bool) (io.ReadCloser, error)
}

type Streamer struct {
	Client LogClient
	Fanout *FanoutRegistry
}

func (s *Streamer) StreamPodLogs(ctx context.Context, sandboxID string, podName string) error {
	if s == nil || s.Client == nil || s.Fanout == nil {
		return nil
	}
	stream, err := s.Client.GetPodLogs(ctx, podName, true)
	if err != nil {
		return err
	}
	defer func() {
		_ = stream.Close()
	}()
	scanner := bufio.NewScanner(stream)
	for scanner.Scan() {
		s.Fanout.Publish(sandboxID, &sandboxv1.SandboxLogLine{
			Line:      scanner.Text(),
			Stream:    "stdout",
			Timestamp: timestamppb.Now(),
		})
	}
	return scanner.Err()
}
