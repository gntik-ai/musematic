package artifacts

import (
	"mime"
	"path"
	"strings"
	"time"

	sandboxv1 "github.com/andrea-mucci/musematic/services/sandbox-manager/api/grpc/v1"
	"google.golang.org/protobuf/types/known/timestamppb"
)

type FileInfo struct {
	Name      string
	SizeBytes int64
}

func BuildManifest(executionID string, sandboxID string, files []FileInfo) []*sandboxv1.ArtifactEntry {
	entries := make([]*sandboxv1.ArtifactEntry, 0, len(files))
	now := timestamppb.New(time.Now().UTC())
	for _, file := range files {
		contentType := mime.TypeByExtension(path.Ext(file.Name))
		if contentType == "" {
			contentType = "application/octet-stream"
		}
		entries = append(entries, &sandboxv1.ArtifactEntry{
			ObjectKey:   path.Join("sandbox-artifacts", executionID, sandboxID, strings.TrimPrefix(file.Name, "./")),
			Filename:    strings.TrimPrefix(file.Name, "./"),
			SizeBytes:   file.SizeBytes,
			ContentType: contentType,
			CollectedAt: now,
		})
	}
	return entries
}
