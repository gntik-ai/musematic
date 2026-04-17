package main

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"math"
	"net"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/musematic/simulation-controller/pkg/persistence"
	"github.com/stretchr/testify/require"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/kubernetes/fake"
	"k8s.io/client-go/rest"
)

type fakeRuntimeStore struct{}

func (fakeRuntimeStore) InsertSimulation(context.Context, persistence.SimulationRecord) error {
	return nil
}

func (fakeRuntimeStore) UpdateSimulationStatus(context.Context, string, persistence.SimulationStatusUpdate) error {
	return nil
}

func (fakeRuntimeStore) FindATESessionIDBySimulation(context.Context, string) (string, error) {
	return "", persistence.ErrNotFound
}

func (fakeRuntimeStore) InsertSimulationArtifact(context.Context, persistence.SimulationArtifactRecord) error {
	return nil
}

func (fakeRuntimeStore) InsertATESession(context.Context, persistence.ATESessionRecord) error {
	return nil
}

func (fakeRuntimeStore) InsertATEResult(context.Context, persistence.ATEResultRecord) error {
	return nil
}

func (fakeRuntimeStore) UpdateATEReport(context.Context, string, string, time.Time) error {
	return nil
}

type fakeRuntimeProducer struct {
	closed bool
}

func (f *fakeRuntimeProducer) Produce(string, string, []byte) error { return nil }
func (f *fakeRuntimeProducer) Close()                               { f.closed = true }

type fakeRuntimeUploader struct{}

func (fakeRuntimeUploader) Upload(context.Context, string, []byte, map[string]string) error {
	return nil
}

func TestLoadConfigUsesEnvOverrides(t *testing.T) {
	t.Setenv("GRPC_PORT", "50099")
	t.Setenv("SIMULATION_BUCKET", "custom-bucket")
	t.Setenv("SIMULATION_NAMESPACE", "custom-namespace")
	t.Setenv("ORPHAN_SCAN_INTERVAL_SECONDS", "10")
	t.Setenv("DEFAULT_MAX_DURATION_SECONDS", "90")

	cfg := loadConfig()
	require.Equal(t, 50099, cfg.grpcPort)
	require.Equal(t, "custom-bucket", cfg.simulationBucket)
	require.Equal(t, "custom-namespace", cfg.simulationNamespace)
	require.EqualValues(t, 90, cfg.defaultMaxDuration)
}

func TestHelperFunctionsCoverFallbackPaths(t *testing.T) {
	t.Setenv("STRING_KEY", "")
	t.Setenv("INT_KEY", "not-an-int")

	require.Equal(t, "fallback", envString("STRING_KEY", "fallback"))
	require.Equal(t, 12, envInt("INT_KEY", 12))
	require.EqualValues(t, math.MaxInt32, safeInt32(1<<62))
	require.EqualValues(t, math.MinInt32, safeInt32(-1<<62))
}

func TestRunReturnsErrorWhenRequiredEnvironmentMissing(t *testing.T) {
	t.Setenv("POSTGRES_DSN", "")
	t.Setenv("KAFKA_BROKERS", "")
	t.Setenv("MINIO_ENDPOINT", "")

	err := run()
	require.Error(t, err)
	require.Contains(t, err.Error(), "POSTGRES_DSN")
}

func TestBuildRuntimeComponentsPanicsOnInvalidPostgresDSN(t *testing.T) {
	require.Panics(t, func() {
		_, _ = buildRuntimeComponents(context.Background(), config{
			postgresDSN:      "://bad-dsn",
			kafkaBrokers:     "localhost:9092",
			minioEndpoint:    "localhost:9000",
			simulationBucket: "bucket",
		})
	})
}

func TestBuildRuntimeComponentsUsesFactories(t *testing.T) {
	originalPool := newPostgresPoolFunc
	originalStore := newPostgresStoreFunc
	originalClosePool := closePostgresPoolFunc
	originalProducer := newRuntimeProducerFunc
	originalUploader := newRuntimeUploaderFunc
	originalKubernetes := newKubernetesClientFunc
	originalListen := listenTCPFunc
	t.Cleanup(func() {
		newPostgresPoolFunc = originalPool
		newPostgresStoreFunc = originalStore
		closePostgresPoolFunc = originalClosePool
		newRuntimeProducerFunc = originalProducer
		newRuntimeUploaderFunc = originalUploader
		newKubernetesClientFunc = originalKubernetes
		listenTCPFunc = originalListen
	})

	newPostgresPoolFunc = func(string) *pgxpool.Pool {
		return &pgxpool.Pool{}
	}
	newPostgresStoreFunc = func(*pgxpool.Pool) runtimeStore {
		return fakeRuntimeStore{}
	}
	closePostgresPoolFunc = func(*pgxpool.Pool) {}
	newRuntimeProducerFunc = func(string) persistence.Producer {
		return &fakeRuntimeProducer{}
	}
	newRuntimeUploaderFunc = func(string, string) runtimeUploader {
		return fakeRuntimeUploader{}
	}
	newKubernetesClientFunc = func(string) (kubernetes.Interface, *rest.Config, error) {
		return fake.NewSimpleClientset(), &rest.Config{Host: "https://127.0.0.1:6443"}, nil
	}
	newListener, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	newListener.Close()
	listenTCPFunc = func(string, string) (net.Listener, error) {
		return newListener, nil
	}

	components, err := buildRuntimeComponents(context.Background(), config{
		grpcPort:            0,
		postgresDSN:         "postgres://test",
		kafkaBrokers:        "localhost:9092",
		minioEndpoint:       "localhost:9000",
		simulationBucket:    "bucket",
		simulationNamespace: "platform-simulation",
	})
	require.NoError(t, err)
	require.NotNil(t, components.store)
	require.NotNil(t, components.producer)
	require.NotNil(t, components.uploader)
	require.NotNil(t, components.clientset)

	newPostgresPoolFunc = func(string) *pgxpool.Pool {
		return nil
	}
	_, err = buildRuntimeComponents(context.Background(), config{
		grpcPort:            0,
		postgresDSN:         "postgres://test",
		kafkaBrokers:        "localhost:9092",
		minioEndpoint:       "localhost:9000",
		simulationBucket:    "bucket",
		simulationNamespace: "platform-simulation",
	})
	require.ErrorContains(t, err, "POSTGRES_DSN")

	newPostgresPoolFunc = func(string) *pgxpool.Pool {
		return &pgxpool.Pool{}
	}
	newRuntimeProducerFunc = func(string) persistence.Producer {
		return nil
	}
	_, err = buildRuntimeComponents(context.Background(), config{
		grpcPort:            0,
		postgresDSN:         "postgres://test",
		kafkaBrokers:        "localhost:9092",
		minioEndpoint:       "localhost:9000",
		simulationBucket:    "bucket",
		simulationNamespace: "platform-simulation",
	})
	require.ErrorContains(t, err, "KAFKA_BROKERS")

	newRuntimeProducerFunc = func(string) persistence.Producer {
		return &fakeRuntimeProducer{}
	}
	newRuntimeUploaderFunc = func(string, string) runtimeUploader {
		return nil
	}
	_, err = buildRuntimeComponents(context.Background(), config{
		grpcPort:            0,
		postgresDSN:         "postgres://test",
		kafkaBrokers:        "localhost:9092",
		minioEndpoint:       "localhost:9000",
		simulationBucket:    "bucket",
		simulationNamespace: "platform-simulation",
	})
	require.ErrorContains(t, err, "MINIO_ENDPOINT")

	kubernetesErr := errors.New("kubernetes failed")
	newRuntimeUploaderFunc = func(string, string) runtimeUploader {
		return fakeRuntimeUploader{}
	}
	newKubernetesClientFunc = func(string) (kubernetes.Interface, *rest.Config, error) {
		return nil, nil, kubernetesErr
	}
	_, err = buildRuntimeComponents(context.Background(), config{
		grpcPort:            0,
		postgresDSN:         "postgres://test",
		kafkaBrokers:        "localhost:9092",
		minioEndpoint:       "localhost:9000",
		simulationBucket:    "bucket",
		simulationNamespace: "platform-simulation",
	})
	require.ErrorIs(t, err, kubernetesErr)

	newKubernetesClientFunc = func(string) (kubernetes.Interface, *rest.Config, error) {
		return fake.NewSimpleClientset(), &rest.Config{Host: "https://127.0.0.1:6443"}, nil
	}
	listenErr := errors.New("listen failed")
	listenTCPFunc = func(string, string) (net.Listener, error) {
		return nil, listenErr
	}
	_, err = buildRuntimeComponents(context.Background(), config{
		grpcPort:            0,
		postgresDSN:         "postgres://test",
		kafkaBrokers:        "localhost:9092",
		minioEndpoint:       "localhost:9000",
		simulationBucket:    "bucket",
		simulationNamespace: "platform-simulation",
	})
	require.ErrorIs(t, err, listenErr)
}

func TestRunWithComponentsBuildsServerAndReturnsListenerError(t *testing.T) {
	t.Parallel()

	listener, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	require.NoError(t, listener.Close())

	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	err = runWithComponents(ctx, config{
		grpcPort:            50055,
		simulationBucket:    "bucket",
		simulationNamespace: "platform-simulation",
		orphanScanInterval:  time.Nanosecond,
		defaultMaxDuration:  30,
	}, runtimeComponents{
		store:     fakeRuntimeStore{},
		producer:  &fakeRuntimeProducer{},
		uploader:  fakeRuntimeUploader{},
		clientset: fake.NewSimpleClientset(),
		restCfg:   &rest.Config{Host: "https://127.0.0.1:6443"},
		listener:  listener,
		close:     func() {},
	}, slog.New(slog.NewTextHandler(io.Discard, nil)))
	if err != nil {
		require.True(
			t,
			strings.Contains(err.Error(), "use of closed network connection") ||
				strings.Contains(err.Error(), "grpc: the server has been stopped"),
			"unexpected listener shutdown error: %v",
			err,
		)
	}
}

func TestNewKubernetesClientReturnsErrorForMissingConfig(t *testing.T) {
	t.Parallel()

	_, _, err := newKubernetesClient("/definitely/missing/kubeconfig")
	require.Error(t, err)
}

func TestNewKubernetesClientLoadsExplicitKubeconfig(t *testing.T) {
	t.Parallel()

	dir := t.TempDir()
	kubeconfig := filepath.Join(dir, "config")
	require.NoError(t, os.WriteFile(kubeconfig, []byte(`
apiVersion: v1
kind: Config
clusters:
- name: local
  cluster:
    server: https://127.0.0.1:6443
contexts:
- name: local
  context:
    cluster: local
    user: local
current-context: local
users:
- name: local
  user:
    token: token
`), 0o600))

	clientset, cfg, err := newKubernetesClient(kubeconfig)
	require.NoError(t, err)
	require.NotNil(t, clientset)
	require.Equal(t, "https://127.0.0.1:6443", cfg.Host)
}
