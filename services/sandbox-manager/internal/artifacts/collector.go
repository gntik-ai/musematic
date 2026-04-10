package artifacts

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"context"
	"fmt"
	"io"

	sandboxv1 "github.com/andrea-mucci/musematic/services/sandbox-manager/api/grpc/v1"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/sandbox"
)

type ArchiveStreamer interface {
	StreamArchive(context.Context, string, string) (io.ReadCloser, error)
}

type Uploader interface {
	Upload(ctx context.Context, key string, body io.Reader, contentType string) error
}

type Collector struct {
	Manager  *sandbox.Manager
	Streamer ArchiveStreamer
	Uploader Uploader
	Bucket   string
}

func NewCollector(manager *sandbox.Manager, streamer ArchiveStreamer, uploader Uploader, bucket string) *Collector {
	return &Collector{Manager: manager, Streamer: streamer, Uploader: uploader, Bucket: bucket}
}

func (c *Collector) CollectBySandboxID(ctx context.Context, sandboxID string) ([]*sandboxv1.ArtifactEntry, bool, error) {
	if c.Manager == nil {
		return nil, false, fmt.Errorf("sandbox manager is required")
	}
	entry, err := c.Manager.Get(sandboxID)
	if err != nil {
		return nil, false, err
	}
	return c.Collect(ctx, *entry)
}

func (c *Collector) Collect(ctx context.Context, entry sandbox.Entry) ([]*sandboxv1.ArtifactEntry, bool, error) {
	if c.Streamer == nil || c.Uploader == nil {
		return []*sandboxv1.ArtifactEntry{}, true, nil
	}
	stream, err := c.Streamer.StreamArchive(ctx, entry.PodNamespace, entry.PodName)
	if err != nil {
		return nil, false, err
	}
	defer stream.Close()
	gz, err := gzip.NewReader(stream)
	if err != nil {
		return nil, false, err
	}
	defer gz.Close()
	reader := tar.NewReader(gz)
	var files []FileInfo
	type upload struct {
		entry *sandboxv1.ArtifactEntry
		body  []byte
	}
	var uploads []upload
	for {
		header, err := reader.Next()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, false, err
		}
		if !header.FileInfo().Mode().IsRegular() {
			continue
		}
		body, err := io.ReadAll(reader)
		if err != nil {
			return nil, false, err
		}
		files = append(files, FileInfo{Name: header.Name, SizeBytes: header.Size})
		uploads = append(uploads, upload{body: body})
	}
	entries := BuildManifest(entry.ExecutionID, entry.SandboxID, files)
	complete := true
	for index, artifact := range entries {
		uploads[index].entry = artifact
		if err := c.Uploader.Upload(ctx, artifact.ObjectKey, bytesReader(uploads[index].body), artifact.ContentType); err != nil {
			complete = false
		}
	}
	return entries, complete, nil
}

type NoopUploader struct{}

func (NoopUploader) Upload(context.Context, string, io.Reader, string) error { return nil }

type MemoryUploader struct {
	Files map[string][]byte
}

func (m *MemoryUploader) Upload(_ context.Context, key string, body io.Reader, _ string) error {
	if m.Files == nil {
		m.Files = map[string][]byte{}
	}
	content, err := io.ReadAll(body)
	if err != nil {
		return err
	}
	m.Files[key] = content
	return nil
}

func bytesReader(body []byte) io.Reader {
	return bytes.NewReader(body)
}
