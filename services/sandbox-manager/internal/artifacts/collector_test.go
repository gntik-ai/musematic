package artifacts

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"context"
	"errors"
	"io"
	"testing"

	sandboxv1 "github.com/andrea-mucci/musematic/services/sandbox-manager/api/grpc/v1"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/sandbox"
)

type archiveStreamerStub struct {
	reader io.ReadCloser
	err    error
}

func (s archiveStreamerStub) StreamArchive(context.Context, string, string) (io.ReadCloser, error) {
	if s.err != nil {
		return nil, s.err
	}
	return s.reader, nil
}

func archiveBytes(t *testing.T, files map[string]string) io.ReadCloser {
	t.Helper()

	var raw bytes.Buffer
	gz := gzip.NewWriter(&raw)
	tw := tar.NewWriter(gz)
	for name, contents := range files {
		payload := []byte(contents)
		if err := tw.WriteHeader(&tar.Header{Name: name, Mode: 0o644, Size: int64(len(payload))}); err != nil {
			t.Fatalf("WriteHeader() error = %v", err)
		}
		if _, err := tw.Write(payload); err != nil {
			t.Fatalf("Write() error = %v", err)
		}
	}
	if err := tw.Close(); err != nil {
		t.Fatalf("Close tar writer: %v", err)
	}
	if err := gz.Close(); err != nil {
		t.Fatalf("Close gzip writer: %v", err)
	}
	return io.NopCloser(bytes.NewReader(raw.Bytes()))
}

func TestCollectorUploadsManifestEntries(t *testing.T) {
	t.Parallel()

	uploader := &MemoryUploader{}
	collector := NewCollector(nil, archiveStreamerStub{reader: archiveBytes(t, map[string]string{
		"result.txt":    "ok",
		"./report.json": `{"status":"ok"}`,
	})}, uploader, "bucket")

	entries, complete, err := collector.Collect(context.Background(), sandbox.Entry{
		SandboxID:    "sandbox-1",
		ExecutionID:  "exec-1",
		PodName:      "pod-1",
		PodNamespace: "platform-execution",
	})
	if err != nil {
		t.Fatalf("Collect() error = %v", err)
	}
	if !complete {
		t.Fatal("expected complete upload")
	}
	if len(entries) != 2 {
		t.Fatalf("expected 2 artifact entries, got %d", len(entries))
	}
	if len(uploader.Files) != 2 {
		t.Fatalf("expected 2 uploaded files, got %d", len(uploader.Files))
	}
}

func TestCollectorHandlesEmptyArchiveGracefully(t *testing.T) {
	t.Parallel()

	collector := NewCollector(nil, archiveStreamerStub{reader: archiveBytes(t, map[string]string{})}, NoopUploader{}, "bucket")
	entries, complete, err := collector.Collect(context.Background(), sandbox.Entry{SandboxID: "sandbox-1", ExecutionID: "exec-1"})
	if err != nil {
		t.Fatalf("Collect() error = %v", err)
	}
	if !complete {
		t.Fatal("expected empty archive to still be complete")
	}
	if len(entries) != 0 {
		t.Fatalf("expected no artifacts, got %d", len(entries))
	}
}

func TestCollectorNoopWithoutStreamerOrUploader(t *testing.T) {
	t.Parallel()

	collector := NewCollector(nil, nil, nil, "bucket")
	entries, complete, err := collector.Collect(context.Background(), sandbox.Entry{SandboxID: "sandbox-1", ExecutionID: "exec-1"})
	if err != nil {
		t.Fatalf("Collect() error = %v", err)
	}
	if !complete {
		t.Fatal("expected noop collector to be complete")
	}
	if len(entries) != 0 {
		t.Fatalf("expected no entries, got %d", len(entries))
	}

	collector = &Collector{}
	if _, _, err := collector.CollectBySandboxID(context.Background(), "sandbox-1"); err == nil {
		t.Fatal("expected nil manager error")
	}
}

func TestCollectorBuildsProtoEntries(t *testing.T) {
	t.Parallel()

	entry := BuildManifest("exec-1", "sandbox-1", []FileInfo{{Name: "result.txt", SizeBytes: 2}})[0]
	if _, ok := any(entry).(*sandboxv1.ArtifactEntry); !ok {
		t.Fatal("expected manifest entry to be proto artifact entry")
	}
	noExt := BuildManifest("exec-1", "sandbox-1", []FileInfo{{Name: "./result", SizeBytes: 2}})[0]
	if noExt.ContentType != "application/octet-stream" || noExt.Filename != "result" {
		t.Fatalf("unexpected no-extension manifest entry %+v", noExt)
	}
}

type failingReader struct{}

func (failingReader) Read([]byte) (int, error) { return 0, errors.New("read boom") }

func TestCollectorPropagatesArchiveAndManagerErrors(t *testing.T) {
	t.Parallel()

	collector := NewCollector(nil, archiveStreamerStub{err: errors.New("stream boom")}, NoopUploader{}, "bucket")
	if _, _, err := collector.Collect(context.Background(), sandbox.Entry{SandboxID: "sandbox-1"}); err == nil {
		t.Fatal("expected Collect() to propagate archive streamer error")
	}

	manager := sandbox.NewManager(sandbox.ManagerConfig{Namespace: "platform-execution"})
	collector = NewCollector(manager, nil, nil, "bucket")
	if _, _, err := collector.CollectBySandboxID(context.Background(), "missing"); err == nil {
		t.Fatal("expected CollectBySandboxID() to fail for missing sandbox")
	}
}

func TestCollectorMarksIncompleteUploadsAndHelpers(t *testing.T) {
	t.Parallel()

	collector := NewCollector(nil, archiveStreamerStub{reader: archiveBytes(t, map[string]string{"result.txt": "ok"})}, uploaderFunc(func(context.Context, string, io.Reader, string) error {
		return errors.New("upload boom")
	}), "bucket")
	entries, complete, err := collector.Collect(context.Background(), sandbox.Entry{
		SandboxID:    "sandbox-1",
		ExecutionID:  "exec-1",
		PodName:      "pod-1",
		PodNamespace: "platform-execution",
	})
	if err != nil {
		t.Fatalf("Collect() error = %v", err)
	}
	if complete {
		t.Fatal("expected upload failure to mark collection incomplete")
	}
	if len(entries) != 1 {
		t.Fatalf("expected 1 artifact entry, got %d", len(entries))
	}
	if err := (NoopUploader{}).Upload(context.Background(), "object", bytes.NewBufferString("ok"), "text/plain"); err != nil {
		t.Fatalf("NoopUploader.Upload() error = %v", err)
	}
	if err := (&MemoryUploader{}).Upload(context.Background(), "object", failingReader{}, "text/plain"); err == nil {
		t.Fatal("expected MemoryUploader.Upload() to propagate read error")
	}
}

type uploaderFunc func(context.Context, string, io.Reader, string) error

func (fn uploaderFunc) Upload(ctx context.Context, key string, body io.Reader, contentType string) error {
	return fn(ctx, key, body, contentType)
}

func TestCollectorHandlesInvalidArchivesAndNonRegularFiles(t *testing.T) {
	t.Parallel()

	collector := NewCollector(nil, archiveStreamerStub{reader: io.NopCloser(bytes.NewBufferString("not-gzip"))}, NoopUploader{}, "bucket")
	if _, _, err := collector.Collect(context.Background(), sandbox.Entry{SandboxID: "sandbox-1"}); err == nil {
		t.Fatal("expected Collect() to fail for invalid gzip stream")
	}

	var raw bytes.Buffer
	gz := gzip.NewWriter(&raw)
	tw := tar.NewWriter(gz)
	if err := tw.WriteHeader(&tar.Header{Name: "nested", Mode: 0o755, Typeflag: tar.TypeDir}); err != nil {
		t.Fatalf("WriteHeader(dir) error = %v", err)
	}
	if err := tw.WriteHeader(&tar.Header{Name: "nested/result", Mode: 0o644, Size: 2}); err != nil {
		t.Fatalf("WriteHeader(file) error = %v", err)
	}
	if _, err := tw.Write([]byte("ok")); err != nil {
		t.Fatalf("Write() error = %v", err)
	}
	if err := tw.Close(); err != nil {
		t.Fatalf("Close tar writer: %v", err)
	}
	if err := gz.Close(); err != nil {
		t.Fatalf("Close gzip writer: %v", err)
	}

	collector = NewCollector(nil, archiveStreamerStub{reader: io.NopCloser(bytes.NewReader(raw.Bytes()))}, &MemoryUploader{}, "bucket")
	entries, complete, err := collector.Collect(context.Background(), sandbox.Entry{
		SandboxID:    "sandbox-1",
		ExecutionID:  "exec-1",
		PodName:      "pod-1",
		PodNamespace: "platform-execution",
	})
	if err != nil {
		t.Fatalf("Collect() error = %v", err)
	}
	if !complete || len(entries) != 1 || entries[0].Filename != "nested/result" {
		t.Fatalf("unexpected non-regular archive result complete=%v entries=%+v", complete, entries)
	}
}
