package artifacts

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"

	runtimev1 "github.com/andrea-mucci/musematic/services/runtime-controller/api/grpc/v1"
	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/state"
	"github.com/google/uuid"
)

type fakeRuntimeLookup struct {
	record state.RuntimeRecord
	err    error
}

func (f fakeRuntimeLookup) GetRuntimeByExecutionID(context.Context, string) (state.RuntimeRecord, error) {
	return f.record, f.err
}

type fakePodArtifacts struct {
	logs       []byte
	logsErr    error
	listing    string
	listErr    error
	fileBodies map[string][]byte
	fileErrs   map[string]error
}

func (f fakePodArtifacts) GetPodLogs(context.Context, string) ([]byte, error) {
	return f.logs, f.logsErr
}

func (f fakePodArtifacts) ExecInPod(_ context.Context, _ string, cmd []string) ([]byte, error) {
	script := cmd[len(cmd)-1]
	switch {
	case strings.Contains(script, "ls -1 /agent/outputs"):
		return []byte(f.listing), f.listErr
	case strings.HasPrefix(script, "cat /agent/outputs/"):
		name := strings.TrimPrefix(script, "cat /agent/outputs/")
		if err := f.fileErrs[name]; err != nil {
			return nil, err
		}
		return f.fileBodies[name], nil
	default:
		return nil, nil
	}
}

type fakeUploader struct {
	uploads map[string][]byte
	failFor map[string]error
}

func (f *fakeUploader) Upload(_ context.Context, key string, body []byte, _ string) error {
	if err := f.failFor[key]; err != nil {
		return err
	}
	if f.uploads == nil {
		f.uploads = map[string][]byte{}
	}
	f.uploads[key] = append([]byte(nil), body...)
	return nil
}

func TestCollectUploadsLogsAndArtifacts(t *testing.T) {
	collector := &Collector{
		Store: fakeRuntimeLookup{record: state.RuntimeRecord{RuntimeID: uuid.New(), ExecutionID: "exec-1", PodName: "pod-1"}},
		Pods: fakePodArtifacts{
			logs:       []byte("runtime logs"),
			listing:    "a.txt\nb.txt\n",
			fileBodies: map[string][]byte{"a.txt": []byte("A"), "b.txt": []byte("B")},
		},
		Uploader: &fakeUploader{},
	}

	entries, complete, err := collector.Collect(context.Background(), "exec-1")
	if err != nil {
		t.Fatalf("Collect returned error: %v", err)
	}
	if !complete || len(entries) != 3 {
		t.Fatalf("unexpected collection result: complete=%v entries=%d", complete, len(entries))
	}
	if entries[0].ObjectKey != "artifacts/exec-1/runtime.log" {
		t.Fatalf("unexpected first entry: %+v", entries[0])
	}
}

func TestCollectMarksIncompleteOnUploadAndReadFailures(t *testing.T) {
	collector := &Collector{
		Store: fakeRuntimeLookup{record: state.RuntimeRecord{RuntimeID: uuid.New(), ExecutionID: "exec-1", PodName: "pod-1"}},
		Pods: fakePodArtifacts{
			logs:       []byte("runtime logs"),
			listing:    "a.txt\nb.txt\n",
			fileBodies: map[string][]byte{"a.txt": []byte("A")},
			fileErrs:   map[string]error{"b.txt": errors.New("read failed")},
		},
		Uploader: &fakeUploader{failFor: map[string]error{"artifacts/exec-1/runtime.log": errors.New("upload failed")}},
	}

	entries, complete, err := collector.Collect(context.Background(), "exec-1")
	if err != nil {
		t.Fatalf("Collect returned error: %v", err)
	}
	if complete {
		t.Fatalf("expected incomplete collection")
	}
	if len(entries) != 1 || entries[0].Filename != "a.txt" {
		t.Fatalf("unexpected entries: %+v", entries)
	}
}

func TestCollectReturnsLookupError(t *testing.T) {
	collector := &Collector{Store: fakeRuntimeLookup{err: errors.New("lookup failed")}}

	if _, _, err := collector.Collect(context.Background(), "exec-1"); err == nil {
		t.Fatalf("expected lookup error")
	}
}

func TestBytesUploaderClonesBody(t *testing.T) {
	uploader := &BytesUploader{}
	body := []byte("payload")

	if err := uploader.Upload(context.Background(), "k", body, "text/plain"); err != nil {
		t.Fatalf("Upload returned error: %v", err)
	}
	body[0] = 'X'
	if string(uploader.Files["k"]) != "payload" {
		t.Fatalf("expected cloned upload body, got %q", uploader.Files["k"])
	}
}

func TestBuildManifestReturnsArtifactCollectedEvent(t *testing.T) {
	event, err := BuildManifest("rt-1", "exec-1", []*runtimev1.ArtifactEntry{{Filename: "runtime.log"}}, true)
	if err != nil {
		t.Fatalf("BuildManifest returned error: %v", err)
	}
	if event.EventType != runtimev1.RuntimeEventType_RUNTIME_EVENT_ARTIFACT_COLLECTED || event.DetailsJson == "" {
		t.Fatalf("unexpected manifest event: %+v", event)
	}
	var details map[string]any
	if err := json.Unmarshal([]byte(event.DetailsJson), &details); err != nil {
		t.Fatalf("unmarshal failed: %v", err)
	}
	if details["complete"] != true {
		t.Fatalf("unexpected details payload: %+v", details)
	}
}
