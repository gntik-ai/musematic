package artifact_collector

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/musematic/simulation-controller/pkg/persistence"
	"github.com/stretchr/testify/require"
	"k8s.io/client-go/rest"
)

type recordingUploader struct {
	key      string
	payload  []byte
	metadata map[string]string
	err      error
}

func (r *recordingUploader) Upload(_ context.Context, key string, data []byte, metadata map[string]string) error {
	if r.err != nil {
		return r.err
	}
	r.key = key
	r.payload = append([]byte(nil), data...)
	r.metadata = metadata
	return nil
}

type recordingStore struct {
	records []persistence.SimulationArtifactRecord
	err     error
}

func (r *recordingStore) InsertSimulationArtifact(_ context.Context, record persistence.SimulationArtifactRecord) error {
	if r.err != nil {
		return r.err
	}
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

func TestCollectPropagatesOperationalErrors(t *testing.T) {
	t.Parallel()

	collector := &ExecCollector{
		Namespace: "platform-simulation",
		exec: func(context.Context, string, string, []string) ([]byte, error) {
			return nil, errors.New("permission denied")
		},
	}
	_, _, err := collector.Collect(context.Background(), "sim-1", "pod-1", []string{"/output"})
	require.Error(t, err)

	collector.exec = func(context.Context, string, string, []string) ([]byte, error) {
		return []byte("archive-bytes"), nil
	}
	collector.uploader = &recordingUploader{err: errors.New("upload failed")}
	_, _, err = collector.Collect(context.Background(), "sim-1", "pod-1", []string{"/output"})
	require.Error(t, err)

	collector.uploader = nil
	collector.store = &recordingStore{err: errors.New("store failed")}
	_, _, err = collector.Collect(context.Background(), "sim-1", "pod-1", []string{"/output"})
	require.Error(t, err)
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
	require.True(t, isPartialCollectionError(errors.New("unable to upgrade connection")))
	require.True(t, isPartialCollectionError(errors.New("not found")))
	require.Nil(t, remoteExec(nil))

	exec := remoteExec(&rest.Config{Host: "://bad-host"})
	require.NotNil(t, exec)
	_, err = exec(context.Background(), "ns", "pod", []string{"true"})
	require.Error(t, err)

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte("exec failed"))
	}))
	defer server.Close()

	exec = remoteExec(&rest.Config{Host: server.URL})
	require.NotNil(t, exec)
	_, err = exec(context.Background(), "ns", "pod", []string{"true"})
	require.Error(t, err)
}
