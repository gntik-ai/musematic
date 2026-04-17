package main

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"net"
	"net/http"
	"sync/atomic"
	"testing"
	"time"

	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/events"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/state"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/pkg/config"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/pkg/telemetry"
	"github.com/confluentinc/confluent-kafka-go/v2/kafka"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
)

type fakeDB struct {
	err error
}

func (d fakeDB) Ping(context.Context) error { return d.err }

type fakeMetadataProducer struct {
	err error
}

func (p fakeMetadataProducer) GetMetadata(*string, bool, int) (*kafka.Metadata, error) {
	return &kafka.Metadata{}, p.err
}

type fakeRuntimeStore struct {
	pingErr      error
	migrationErr error
	closeCount   int
}

func (*fakeRuntimeStore) InsertSandbox(context.Context, state.SandboxRecord) error { return nil }

func (*fakeRuntimeStore) UpdateSandboxState(context.Context, string, string, string, int32, *int64) error {
	return nil
}

func (*fakeRuntimeStore) InsertSandboxEvent(context.Context, state.SandboxEventRecord) error {
	return nil
}

func (s *fakeRuntimeStore) Ping(context.Context) error { return s.pingErr }

func (s *fakeRuntimeStore) RunMigrations(context.Context) error { return s.migrationErr }

func (s *fakeRuntimeStore) Close() { s.closeCount++ }

type fakeProducer struct {
	closeCount int
	metaErr    error
}

func (*fakeProducer) Produce(*kafka.Message, chan kafka.Event) error { return nil }

func (p *fakeProducer) Close() { p.closeCount++ }

func (p *fakeProducer) GetMetadata(*string, bool, int) (*kafka.Metadata, error) {
	return &kafka.Metadata{}, p.metaErr
}

type fakeHTTPServer struct {
	listenErr     error
	listenCalls   int
	shutdownCount int
}

func (s *fakeHTTPServer) ListenAndServe() error {
	s.listenCalls++
	return s.listenErr
}

func (s *fakeHTTPServer) Shutdown(context.Context) error {
	s.shutdownCount++
	return nil
}

type fakeGRPCServer struct {
	serveErr   error
	serveCalls int
	stopCount  int
	stopCh     chan struct{}
}

func (s *fakeGRPCServer) Serve(net.Listener) error {
	s.serveCalls++
	if s.stopCh != nil {
		<-s.stopCh
	}
	return s.serveErr
}

func (s *fakeGRPCServer) GracefulStop() {
	s.stopCount++
	if s.stopCh != nil {
		select {
		case <-s.stopCh:
		default:
			close(s.stopCh)
		}
	}
}

type fakeScanner struct {
	runCount atomic.Int32
	err      error
}

func (s *fakeScanner) Run(ctx context.Context) error {
	s.runCount.Add(1)
	<-ctx.Done()
	if s.err != nil {
		return s.err
	}
	return ctx.Err()
}

func (s *fakeScanner) count() int {
	return int(s.runCount.Load())
}

func waitForScannerRuns(t *testing.T, scanners ...*fakeScanner) {
	t.Helper()

	deadline := time.Now().Add(250 * time.Millisecond)
	for time.Now().Before(deadline) {
		allStarted := true
		for _, scanner := range scanners {
			if scanner.count() == 0 {
				allStarted = false
				break
			}
		}
		if allStarted {
			return
		}
		time.Sleep(5 * time.Millisecond)
	}
}

type fakeListener struct {
	closeCount int
}

func (*fakeListener) Accept() (net.Conn, error) { return nil, errors.New("not implemented") }

func (l *fakeListener) Close() error {
	l.closeCount++
	return nil
}

func (*fakeListener) Addr() net.Addr { return fakeAddr("tcp") }

type fakeAddr string

func (a fakeAddr) Network() string { return string(a) }

func (a fakeAddr) String() string { return string(a) }

func testConfig() config.Config {
	return config.Config{
		GRPCPort:               50053,
		HTTPPort:               8080,
		PostgresDSN:            "postgres://sandbox:test@localhost:5432/musematic",
		KafkaBrokers:           []string{"broker:9092"},
		MinIOEndpoint:          "http://minio:9000",
		MinIOBucket:            "musematic-artifacts",
		K8sNamespace:           "platform-execution",
		DefaultTimeout:         30 * time.Second,
		MaxTimeout:             300 * time.Second,
		MaxOutputSize:          1024,
		OrphanScanInterval:     time.Second,
		IdleTimeout:            time.Second,
		MaxConcurrentSandboxes: 2,
		K8sDryRun:              true,
	}
}

func restoreMainGlobals(t *testing.T) {
	t.Helper()

	originalLoadConfig := loadConfigFn
	originalNotifyContext := notifyContextFn
	originalSetupTelemetry := setupTelemetryFn
	originalNewRuntimeStore := newRuntimeStore
	originalNewK8sClient := newK8sClientFn
	originalNewKafkaProducer := newKafkaProducerFn
	originalListen := listenFn
	originalBuildRuntimeDeps := buildRuntimeDepsFn
	originalRun := runFn
	originalExit := exitFn

	t.Cleanup(func() {
		loadConfigFn = originalLoadConfig
		notifyContextFn = originalNotifyContext
		setupTelemetryFn = originalSetupTelemetry
		newRuntimeStore = originalNewRuntimeStore
		newK8sClientFn = originalNewK8sClient
		newKafkaProducerFn = originalNewKafkaProducer
		listenFn = originalListen
		buildRuntimeDepsFn = originalBuildRuntimeDeps
		runFn = originalRun
		exitFn = originalExit
	})
}

func TestRunRequiresPostgresDSN(t *testing.T) {
	restoreMainGlobals(t)

	t.Setenv("POSTGRES_DSN", "")
	if err := run(); err == nil || err.Error() != "POSTGRES_DSN is required" {
		t.Fatalf("run() error = %v", err)
	}
}

func TestHealthHelpers(t *testing.T) {
	restoreMainGlobals(t)

	expectedErr := errors.New("metadata boom")
	if err := (postgresPinger{}).Ping(context.Background()); err != nil {
		t.Fatalf("nil Ping() error = %v", err)
	}
	if err := (postgresPinger{db: fakeDB{}}).Ping(context.Background()); err != nil {
		t.Fatalf("success Ping() error = %v", err)
	}
	if err := (postgresPinger{db: fakeDB{err: expectedErr}}).Ping(context.Background()); !errors.Is(err, expectedErr) {
		t.Fatalf("Ping() error = %v, want %v", err, expectedErr)
	}
	if _, err := (kafkaHealth{}).GetMetadata(nil, false, 1000); err != nil {
		t.Fatalf("GetMetadata() error = %v", err)
	}
	if _, err := (kafkaHealth{producer: fakeMetadataProducer{err: expectedErr}}).GetMetadata(nil, false, 1000); !errors.Is(err, expectedErr) {
		t.Fatalf("GetMetadata() error = %v, want %v", err, expectedErr)
	}
	body, err := (k8sHealth{}).DoRaw(context.Background(), "/readyz")
	if err != nil {
		t.Fatalf("DoRaw() error = %v", err)
	}
	if string(body) != "ok" {
		t.Fatalf("unexpected DoRaw() body %q", body)
	}
	if err := (liveRuntimeStore{}).Ping(context.Background()); err != nil {
		t.Fatalf("liveRuntimeStore.Ping() error = %v", err)
	}
	if err := (liveRuntimeStore{}).RunMigrations(context.Background()); err != nil {
		t.Fatalf("liveRuntimeStore.RunMigrations() error = %v", err)
	}
	(*runtimeDeps)(nil).close()
}

func TestDefaultBuildRuntimeDeps(t *testing.T) {
	restoreMainGlobals(t)

	cfg := testConfig()
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))

	t.Run("setup telemetry failure", func(t *testing.T) {
		expectedErr := errors.New("otel boom")
		setupTelemetryFn = func(context.Context, string, string) (telemetry.Shutdown, error) {
			return nil, expectedErr
		}
		if _, err := defaultBuildRuntimeDeps(context.Background(), logger, cfg); !errors.Is(err, expectedErr) {
			t.Fatalf("defaultBuildRuntimeDeps() error = %v, want %v", err, expectedErr)
		}
	})

	t.Run("store failure", func(t *testing.T) {
		setupTelemetryFn = func(context.Context, string, string) (telemetry.Shutdown, error) {
			return func(context.Context) error { return nil }, nil
		}
		expectedErr := errors.New("store boom")
		newRuntimeStore = func(context.Context, string) (runtimeStore, error) {
			return nil, expectedErr
		}
		if _, err := defaultBuildRuntimeDeps(context.Background(), logger, cfg); !errors.Is(err, expectedErr) {
			t.Fatalf("defaultBuildRuntimeDeps() error = %v, want %v", err, expectedErr)
		}
	})

	t.Run("migration failure", func(t *testing.T) {
		store := &fakeRuntimeStore{migrationErr: errors.New("migration boom")}
		setupTelemetryFn = func(context.Context, string, string) (telemetry.Shutdown, error) {
			return func(context.Context) error { return nil }, nil
		}
		newRuntimeStore = func(context.Context, string) (runtimeStore, error) {
			return store, nil
		}
		if _, err := defaultBuildRuntimeDeps(context.Background(), logger, cfg); !errors.Is(err, store.migrationErr) {
			t.Fatalf("defaultBuildRuntimeDeps() error = %v, want %v", err, store.migrationErr)
		}
		if store.closeCount == 0 {
			t.Fatal("expected migration failure to close the store")
		}
	})

	t.Run("k8s error when not dry run", func(t *testing.T) {
		localCfg := cfg
		localCfg.K8sDryRun = false
		setupTelemetryFn = func(context.Context, string, string) (telemetry.Shutdown, error) {
			return func(context.Context) error { return nil }, nil
		}
		newRuntimeStore = func(context.Context, string) (runtimeStore, error) {
			return &fakeRuntimeStore{}, nil
		}
		expectedErr := errors.New("k8s boom")
		newK8sClientFn = func() (*kubernetes.Clientset, *rest.Config, error) {
			return nil, nil, expectedErr
		}
		if _, err := defaultBuildRuntimeDeps(context.Background(), logger, localCfg); !errors.Is(err, expectedErr) {
			t.Fatalf("defaultBuildRuntimeDeps() error = %v, want %v", err, expectedErr)
		}
	})

	t.Run("success in dry run despite k8s and kafka init errors", func(t *testing.T) {
		store := &fakeRuntimeStore{}
		listener := &fakeListener{}
		shutdownCount := 0
		setupTelemetryFn = func(context.Context, string, string) (telemetry.Shutdown, error) {
			return func(context.Context) error {
				shutdownCount++
				return nil
			}, nil
		}
		newRuntimeStore = func(context.Context, string) (runtimeStore, error) {
			return store, nil
		}
		newK8sClientFn = func() (*kubernetes.Clientset, *rest.Config, error) {
			return nil, nil, errors.New("ignored k8s boom")
		}
		newKafkaProducerFn = func([]string) (events.Producer, error) {
			return nil, errors.New("ignored kafka boom")
		}
		listenFn = func(string, string) (net.Listener, error) {
			return listener, nil
		}

		deps, err := defaultBuildRuntimeDeps(context.Background(), logger, cfg)
		if err != nil {
			t.Fatalf("defaultBuildRuntimeDeps() error = %v", err)
		}
		if deps.httpServer == nil || deps.grpcServer == nil || deps.listener == nil || deps.orphanScanner == nil || deps.idleScanner == nil {
			t.Fatalf("expected runtime dependencies to be fully populated: %+v", deps)
		}
		deps.close()
		if store.closeCount == 0 || listener.closeCount == 0 || shutdownCount == 0 {
			t.Fatalf("expected close hooks to run, got store=%d listener=%d shutdown=%d", store.closeCount, listener.closeCount, shutdownCount)
		}
	})

	t.Run("listener failure closes producer and store", func(t *testing.T) {
		store := &fakeRuntimeStore{}
		producer := &fakeProducer{}
		shutdownCount := 0
		setupTelemetryFn = func(context.Context, string, string) (telemetry.Shutdown, error) {
			return func(context.Context) error {
				shutdownCount++
				return nil
			}, nil
		}
		newRuntimeStore = func(context.Context, string) (runtimeStore, error) {
			return store, nil
		}
		newK8sClientFn = func() (*kubernetes.Clientset, *rest.Config, error) {
			return nil, &rest.Config{Host: "https://cluster.example"}, nil
		}
		newKafkaProducerFn = func([]string) (events.Producer, error) {
			return producer, nil
		}
		expectedErr := errors.New("listen boom")
		listenFn = func(string, string) (net.Listener, error) {
			return nil, expectedErr
		}

		if _, err := defaultBuildRuntimeDeps(context.Background(), logger, cfg); !errors.Is(err, expectedErr) {
			t.Fatalf("defaultBuildRuntimeDeps() error = %v, want %v", err, expectedErr)
		}
		if store.closeCount == 0 || producer.closeCount == 0 || shutdownCount == 0 {
			t.Fatalf("expected cleanup on listener failure, got store=%d producer=%d shutdown=%d", store.closeCount, producer.closeCount, shutdownCount)
		}
	})
}

func TestRunLifecycle(t *testing.T) {
	restoreMainGlobals(t)

	cfg := testConfig()
	loadConfigFn = func() (config.Config, error) { return cfg, nil }

	t.Run("http failure cancels and shuts down", func(t *testing.T) {
		httpServer := &fakeHTTPServer{listenErr: errors.New("http boom")}
		grpcServer := &fakeGRPCServer{stopCh: make(chan struct{})}
		orphanScanner := &fakeScanner{}
		idleScanner := &fakeScanner{}
		listener := &fakeListener{}

		buildRuntimeDepsFn = func(context.Context, *slog.Logger, config.Config) (*runtimeDeps, error) {
			return &runtimeDeps{
				cfg:           cfg,
				httpServer:    httpServer,
				grpcServer:    grpcServer,
				listener:      listener,
				orphanScanner: orphanScanner,
				idleScanner:   idleScanner,
			}, nil
		}

		if err := run(); err != nil {
			t.Fatalf("run() error = %v", err)
		}
		if httpServer.shutdownCount == 0 || grpcServer.stopCount == 0 {
			t.Fatalf("expected shutdown hooks to run, got http=%d grpc=%d", httpServer.shutdownCount, grpcServer.stopCount)
		}
		waitForScannerRuns(t, orphanScanner, idleScanner)
		if orphanScanner.count() == 0 || idleScanner.count() == 0 {
			t.Fatalf("expected scanners to run, got orphan=%d idle=%d", orphanScanner.count(), idleScanner.count())
		}
		if listener.closeCount == 0 {
			t.Fatal("expected listener to be closed")
		}
	})

	t.Run("serve error is returned", func(t *testing.T) {
		expectedErr := errors.New("serve boom")
		buildRuntimeDepsFn = func(context.Context, *slog.Logger, config.Config) (*runtimeDeps, error) {
			return &runtimeDeps{
				cfg:        cfg,
				httpServer: &fakeHTTPServer{listenErr: http.ErrServerClosed},
				grpcServer: &fakeGRPCServer{serveErr: expectedErr},
				listener:   &fakeListener{},
			}, nil
		}
		if err := run(); !errors.Is(err, expectedErr) {
			t.Fatalf("run() error = %v, want %v", err, expectedErr)
		}
	})
}

func TestMainDelegatesExitCode(t *testing.T) {
	restoreMainGlobals(t)

	t.Run("error exits with code 1", func(t *testing.T) {
		runFn = func() error { return errors.New("boom") }
		exitCode := -1
		exitFn = func(code int) { exitCode = code }
		main()
		if exitCode != 1 {
			t.Fatalf("main() exit code = %d, want 1", exitCode)
		}
	})

	t.Run("success does not exit", func(t *testing.T) {
		runFn = func() error { return nil }
		exitCode := -1
		exitFn = func(code int) { exitCode = code }
		main()
		if exitCode != -1 {
			t.Fatalf("main() unexpected exit code %d", exitCode)
		}
	})
}
