package artifacts

import (
	"bytes"
	"context"
	"fmt"
	"path"
	"strings"
	"time"

	runtimev1 "github.com/andrea-mucci/musematic/services/runtime-controller/api/grpc/v1"
	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/state"
	"google.golang.org/protobuf/types/known/timestamppb"
)

type RuntimeLookup interface {
	GetRuntimeByExecutionID(context.Context, string) (state.RuntimeRecord, error)
}

type PodArtifactClient interface {
	GetPodLogs(context.Context, string) ([]byte, error)
	ExecInPod(context.Context, string, []string) ([]byte, error)
}

type ObjectUploader interface {
	Upload(ctx context.Context, key string, body []byte, contentType string) error
}

type Collector struct {
	Store    RuntimeLookup
	Pods     PodArtifactClient
	Uploader ObjectUploader
}

func (c *Collector) Collect(ctx context.Context, executionID string) ([]*runtimev1.ArtifactEntry, bool, error) {
	runtimeRecord, err := c.Store.GetRuntimeByExecutionID(ctx, executionID)
	if err != nil {
		return nil, false, err
	}
	var entries []*runtimev1.ArtifactEntry
	complete := true

	logs, err := c.Pods.GetPodLogs(ctx, runtimeRecord.PodName)
	if err == nil {
		key := path.Join("artifacts", executionID, "runtime.log")
		if uploadErr := c.Uploader.Upload(ctx, key, logs, "text/plain"); uploadErr == nil {
			entries = append(entries, entryFromBytes(key, "runtime.log", "text/plain", logs))
		} else {
			complete = false
		}
	} else {
		complete = false
	}

	files, err := c.Pods.ExecInPod(ctx, runtimeRecord.PodName, []string{"sh", "-c", "ls -1 /agent/outputs 2>/dev/null || true"})
	if err == nil {
		for _, file := range strings.Fields(string(files)) {
			content, readErr := c.Pods.ExecInPod(ctx, runtimeRecord.PodName, []string{"sh", "-c", fmt.Sprintf("cat /agent/outputs/%s", file)})
			if readErr != nil {
				complete = false
				continue
			}
			key := path.Join("artifacts", executionID, file)
			if uploadErr := c.Uploader.Upload(ctx, key, content, "application/octet-stream"); uploadErr == nil {
				entries = append(entries, entryFromBytes(key, file, "application/octet-stream", content))
			} else {
				complete = false
			}
		}
	}

	return entries, complete, nil
}

type BytesUploader struct {
	Files map[string][]byte
}

func (b *BytesUploader) Upload(_ context.Context, key string, body []byte, _ string) error {
	if b.Files == nil {
		b.Files = map[string][]byte{}
	}
	b.Files[key] = bytes.Clone(body)
	return nil
}

func entryFromBytes(key string, filename string, contentType string, body []byte) *runtimev1.ArtifactEntry {
	return &runtimev1.ArtifactEntry{
		ObjectKey:   key,
		Filename:    filename,
		SizeBytes:   int64(len(body)),
		ContentType: contentType,
		CollectedAt: timestamppb.New(time.Now().UTC()),
	}
}
