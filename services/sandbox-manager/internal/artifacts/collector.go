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
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	otelcodes "go.opentelemetry.io/otel/codes"
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

var collectorTracer = otel.Tracer("sandbox-manager/internal/artifacts")

func NewCollector(manager *sandbox.Manager, streamer ArchiveStreamer, uploader Uploader, bucket string) *Collector {
	return &Collector{Manager: manager, Streamer: streamer, Uploader: uploader, Bucket: bucket}
}

func (c *Collector) CollectBySandboxID(ctx context.Context, sandboxID string) ([]*sandboxv1.ArtifactEntry, bool, error) {
	ctx, span := collectorTracer.Start(ctx, "Collector/CollectBySandboxID")
	span.SetAttributes(attribute.String("sandbox.id", sandboxID))
	defer span.End()

	if c.Manager == nil {
		err := fmt.Errorf("sandbox manager is required")
		span.RecordError(err)
		span.SetStatus(otelcodes.Error, err.Error())
		return nil, false, err
	}
	entry, err := c.Manager.Get(sandboxID)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(otelcodes.Error, err.Error())
		return nil, false, err
	}
	return c.Collect(ctx, *entry)
}

func (c *Collector) Collect(ctx context.Context, entry sandbox.Entry) ([]*sandboxv1.ArtifactEntry, bool, error) {
	ctx, span := collectorTracer.Start(ctx, "Collector/Collect")
	span.SetAttributes(
		attribute.String("sandbox.id", entry.SandboxID),
		attribute.String("execution.id", entry.ExecutionID),
		attribute.String("pod.name", entry.PodName),
		attribute.String("pod.namespace", entry.PodNamespace),
	)
	defer span.End()

	if c.Streamer == nil || c.Uploader == nil {
		span.SetAttributes(attribute.Bool("collector.noop", true))
		return []*sandboxv1.ArtifactEntry{}, true, nil
	}
	stream, err := c.Streamer.StreamArchive(ctx, entry.PodNamespace, entry.PodName)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(otelcodes.Error, err.Error())
		return nil, false, err
	}
	defer func() {
		_ = stream.Close()
	}()
	gz, err := gzip.NewReader(stream)
	if err != nil {
		return nil, false, err
	}
	defer func() {
		_ = gz.Close()
	}()
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
			span.RecordError(err)
			span.SetStatus(otelcodes.Error, err.Error())
			return nil, false, err
		}
		if !header.FileInfo().Mode().IsRegular() {
			continue
		}
		body, err := io.ReadAll(reader)
		if err != nil {
			span.RecordError(err)
			span.SetStatus(otelcodes.Error, err.Error())
			return nil, false, err
		}
		files = append(files, FileInfo{Name: header.Name, SizeBytes: header.Size})
		uploads = append(uploads, upload{body: body})
	}
	entries := BuildManifest(entry.ExecutionID, entry.SandboxID, files)
	span.SetAttributes(attribute.Int("artifact.count", len(entries)))
	complete := true
	for index, artifact := range entries {
		uploads[index].entry = artifact
		uploadCtx, uploadSpan := collectorTracer.Start(ctx, "Collector/UploadArtifact")
		uploadSpan.SetAttributes(
			attribute.String("artifact.object_key", artifact.ObjectKey),
			attribute.String("artifact.filename", artifact.Filename),
			attribute.String("artifact.content_type", artifact.ContentType),
			attribute.Int64("artifact.size_bytes", artifact.SizeBytes),
		)
		if err := c.Uploader.Upload(uploadCtx, artifact.ObjectKey, bytesReader(uploads[index].body), artifact.ContentType); err != nil {
			complete = false
			uploadSpan.RecordError(err)
			uploadSpan.SetStatus(otelcodes.Error, err.Error())
		}
		uploadSpan.End()
	}
	span.SetAttributes(attribute.Bool("artifact.complete", complete))
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
