package artifact_collector

import (
	"context"
	"errors"
	"testing"

	"github.com/musematic/simulation-controller/pkg/persistence"
	"github.com/stretchr/testify/require"
)

type recordingUploader struct {
	key      string
	payload  []byte
	metadata map[string]string
}

func (r *recordingUploader) Upload(_ context.Context, key string, data []byte, metadata map[string]string) error {
	r.key = key
	r.payload = append([]byte(nil), data...)
	r.metadata = metadata
	return nil
}

type recordingStore struct {
	records []persistence.SimulationArtifactRecord
}

func (r *recordingStore) InsertSimulationArtifact(_ context.Context, record persistence.SimulationArtifactRecord) error {
	r.records = append(r.records, record)
	return nil
}

func TestCollectUploadsArtifactsWithMetadata(t *testing.T) {
	t.Parallel()

	uploader := &recordingUploader{}
	store := &recordingStore{}
	collector := &ExecCollector{
		Namespace: "platform-simulation",
		exec: func(context.Context, string, string, []string) ([]byte, error) {
			return []byte("archive-bytes"), nil
		},
		uploader: uploader,
		store:    store,
	}

	refs, partial, err := collector.Collect(context.Background(), "sim-1", "pod-1", []string{"/output"})
	require.NoError(t, err)
	require.False(t, partial)
	require.Len(t, refs, 1)
	require.Equal(t, "sim-1/output.tar.gz", refs[0].GetObjectKey())
	require.Equal(t, "true", uploader.metadata["x-amz-meta-simulation"])
	require.Equal(t, "sim-1", uploader.metadata["x-amz-meta-simulation-id"])
	require.Len(t, store.records, 1)
	require.Equal(t, "output.tar.gz", store.records[0].Filename)
}

func TestCollectMarksPartialWhenPodIsGone(t *testing.T) {
	t.Parallel()

	collector := &ExecCollector{
		Namespace: "platform-simulation",
		exec: func(context.Context, string, string, []string) ([]byte, error) {
			return nil, errors.New("container not found")
		},
	}

	refs, partial, err := collector.Collect(context.Background(), "sim-1", "pod-1", []string{"/output"})
	require.NoError(t, err)
	require.True(t, partial)
	require.Empty(t, refs)
}

func TestCollectHelpersCoverFallbackBranches(t *testing.T) {
	t.Parallel()

	collector := NewExecCollector("platform-simulation", nil, nil, nil)
	require.NotNil(t, collector)

	refs, partial, err := collector.Collect(context.Background(), "sim-1", "pod-1", []string{"/output"})
	require.NoError(t, err)
	require.False(t, partial)
	require.Empty(t, refs)

	require.Equal(t, "artifacts.tar.gz", artifactFilename("/"))
	require.Equal(t, "output.tar.gz", artifactFilename("/output/"))
	require.False(t, isPartialCollectionError(nil))
	require.False(t, isPartialCollectionError(errors.New("permission denied")))
}
