package main

import (
	"context"
	"errors"
	"net"
	"os"
	"testing"
	"time"

	reasoningv1 "github.com/musematic/reasoning-engine/api/grpc/v1"
	"github.com/musematic/reasoning-engine/pkg/metrics"
	"github.com/musematic/reasoning-engine/pkg/telemetry"
	"github.com/redis/go-redis/v9"
	"google.golang.org/grpc"
)

type fakeGRPCServer struct {
	registered     int
	serveErr       error
	serveFn        func(net.Listener) error
	gracefulStop   bool
	gracefulStopFn func()
	stopped        bool
}

func (s *fakeGRPCServer) RegisterService(*grpc.ServiceDesc, any) {
	s.registered++
}

func (s *fakeGRPCServer) Serve(listener net.Listener) error {
	if s.serveFn != nil {
		return s.serveFn(listener)
	}
	return s.serveErr
}

func (s *fakeGRPCServer) GracefulStop() {
	s.gracefulStop = true
	if s.gracefulStopFn != nil {
		s.gracefulStopFn()
	}
}

func (s *fakeGRPCServer) Stop() {
	s.stopped = true
}

type fakeListener struct{}

func (fakeListener) Accept() (net.Conn, error) { return nil, errors.New("unused") }
func (fakeListener) Close() error              { return nil }
func (fakeListener) Addr() net.Addr            { return &net.TCPAddr{IP: net.IPv4zero, Port: 50052} }

func TestEnvHelpersAndLoadConfig(t *testing.T) {
	t.Setenv("GRPC_PORT", "60000")
	t.Setenv("MINIO_BUCKET", "custom-bucket")
	t.Setenv("MAX_TOT_CONCURRENCY", "12")
	t.Setenv("TRACE_BUFFER_SIZE", "200")
	t.Setenv("TRACE_PAYLOAD_THRESHOLD", "1234")
	t.Setenv("BUDGET_DEFAULT_TTL_SECONDS", "99")
	t.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "otel-collector:4317")
	t.Setenv("STARTUP_DEPENDENCY_TIMEOUT_SECONDS", "42")
	t.Setenv("STARTUP_DEPENDENCY_RETRY_INTERVAL_SECONDS", "3")

	cfg, err := loadConfig()
	if err != nil {
		t.Fatalf("loadConfig() error = %v", err)
	}
	if cfg.grpcPort != 60000 || cfg.minioBucket != "custom-bucket" || cfg.maxToTConcurrency != 12 {
		t.Fatalf("unexpected config: %+v", cfg)
	}
	if cfg.otlpExporterEndpoint != "otel-collector:4317" {
		t.Fatalf("unexpected otlp endpoint: %q", cfg.otlpExporterEndpoint)
	}
	if cfg.startupDependencyTimeout != 42*time.Second || cfg.startupDependencyRetry != 3*time.Second {
		t.Fatalf("unexpected startup dependency retry config: %+v", cfg)
	}
	if envString("MISSING_STRING", "fallback") != "fallback" {
		t.Fatal("envString() did not return fallback")
	}
	if envInt("MISSING_INT", 7) != 7 {
		t.Fatal("envInt() did not return fallback")
	}
	if envInt64("MISSING_INT64", 9) != 9 {
		t.Fatal("envInt64() did not return fallback")
	}

	t.Setenv("GRPC_PORT", "invalid")
	t.Setenv("BUDGET_DEFAULT_TTL_SECONDS", "invalid")
	if envInt("GRPC_PORT", 50052) != 50052 {
		t.Fatal("envInt() should return fallback for invalid values")
	}
	if envInt64("BUDGET_DEFAULT_TTL_SECONDS", 3600) != 3600 {
		t.Fatal("envInt64() should return fallback for invalid values")
	}
}

func TestRunReturnsMissingRedisError(t *testing.T) {
	t.Setenv("REDIS_ADDR", "")
	t.Setenv("POSTGRES_DSN", "")
	t.Setenv("KAFKA_BROKERS", "")
	t.Setenv("MINIO_ENDPOINT", "")
	t.Setenv("MINIO_BUCKET", "")

	if err := run(); err == nil || err.Error() != "REDIS_ADDR is required" {
		t.Fatalf("run() error = %v, want REDIS_ADDR is required", err)
	}
}

func TestRunValidatesDependenciesInOrder(t *testing.T) {
	t.Setenv("REDIS_TEST_MODE", "standalone")
	t.Setenv("REDIS_ADDR", "127.0.0.1:6379")
	t.Setenv("POSTGRES_DSN", "")
	t.Setenv("KAFKA_BROKERS", "")
	t.Setenv("MINIO_ENDPOINT", "")
	t.Setenv("MINIO_BUCKET", "")

	if err := run(); err == nil || err.Error() != "POSTGRES_DSN is required" {
		t.Fatalf("run() error = %v, want POSTGRES_DSN is required", err)
	}

	t.Setenv("POSTGRES_DSN", "postgres://user:pass@127.0.0.1:5432/musematic?sslmode=disable")
	if err := run(); err == nil || err.Error() != "KAFKA_BROKERS is required" {
		t.Fatalf("run() error = %v, want KAFKA_BROKERS is required", err)
	}

	t.Setenv("KAFKA_BROKERS", "127.0.0.1:9092")
	if err := run(); err == nil || err.Error() != "MINIO_ENDPOINT and MINIO_BUCKET are required" {
		t.Fatalf("run() error = %v, want MINIO_ENDPOINT and MINIO_BUCKET are required", err)
	}
}

func TestRunReturnsLuaLoadErrorAfterDependencies(t *testing.T) {
	t.Setenv("REDIS_TEST_MODE", "standalone")
	t.Setenv("REDIS_ADDR", "127.0.0.1:6379")
	t.Setenv("POSTGRES_DSN", "postgres://user:pass@127.0.0.1:5432/musematic?sslmode=disable")
	t.Setenv("KAFKA_BROKERS", "127.0.0.1:9092")
	t.Setenv("MINIO_ENDPOINT", "http://127.0.0.1:9000")
	t.Setenv("MINIO_BUCKET", "reasoning-traces")
	t.Setenv("STARTUP_DEPENDENCY_TIMEOUT_SECONDS", "0")

	if err := run(); err == nil {
		t.Fatal("expected lua load error without a live redis instance")
	}
}

func TestDefaultBuildRuntimeDepsSuccessPath(t *testing.T) {
	originalLoadLua := loadLuaFn
	defer func() {
		loadLuaFn = originalLoadLua
	}()

	loadLuaFn = func(context.Context, redis.Scripter) (map[string]string, error) {
		return map[string]string{
			"budget_decrement":  "sha-budget",
			"convergence_check": "sha-convergence",
		}, nil
	}

	deps, err := defaultBuildRuntimeDeps(context.Background(), config{
		redisAddr:               "127.0.0.1:6379",
		postgresDSN:             "postgres://user:pass@127.0.0.1:5432/musematic?sslmode=disable",
		kafkaBrokers:            "127.0.0.1:9092",
		minioEndpoint:           "http://127.0.0.1:9000",
		minioBucket:             "reasoning-traces",
		maxToTConcurrency:       4,
		traceBufferSize:         16,
		tracePayloadThreshold:   128,
		budgetDefaultTTLSeconds: 90,
	})
	if err != nil {
		t.Fatalf("defaultBuildRuntimeDeps() error = %v", err)
	}
	if deps.handler.ModeSelector == nil || deps.handler.BudgetTracker == nil || deps.handler.EventRegistry == nil || deps.handler.CoTCoordinator == nil || deps.handler.ToTManager == nil || deps.handler.DebateService == nil || deps.handler.CorrectionLoop == nil || deps.handler.TraceStore == nil || deps.handler.TraceUploader == nil || deps.handler.ReasoningEvents == nil || deps.handler.Metrics == nil {
		t.Fatalf("unexpected handler deps: %+v", deps.handler)
	}
	deps.cleanup()
}

func TestDefaultBuildRuntimeDepsRetriesLuaLoad(t *testing.T) {
	originalLoadLua := loadLuaFn
	originalAfter := dependencyRetryAfterFn
	defer func() {
		loadLuaFn = originalLoadLua
		dependencyRetryAfterFn = originalAfter
	}()

	attempts := 0
	loadLuaFn = func(context.Context, redis.Scripter) (map[string]string, error) {
		attempts++
		if attempts == 1 {
			return nil, errors.New("redis not ready")
		}
		return map[string]string{
			"budget_decrement":  "sha-budget",
			"convergence_check": "sha-convergence",
		}, nil
	}
	dependencyRetryAfterFn = func(time.Duration) <-chan time.Time {
		ch := make(chan time.Time, 1)
		ch <- time.Now()
		return ch
	}

	deps, err := defaultBuildRuntimeDeps(context.Background(), config{
		redisAddr:                "127.0.0.1:6379",
		postgresDSN:              "postgres://user:pass@127.0.0.1:5432/musematic?sslmode=disable",
		kafkaBrokers:             "127.0.0.1:9092",
		minioEndpoint:            "http://127.0.0.1:9000",
		minioBucket:              "reasoning-traces",
		maxToTConcurrency:        4,
		traceBufferSize:          16,
		tracePayloadThreshold:    128,
		budgetDefaultTTLSeconds:  90,
		startupDependencyTimeout: time.Second,
		startupDependencyRetry:   time.Millisecond,
	})
	if err != nil {
		t.Fatalf("defaultBuildRuntimeDeps() error = %v", err)
	}
	if attempts != 2 {
		t.Fatalf("loadLuaFn attempts = %d, want 2", attempts)
	}
	deps.cleanup()
}

func TestRunServesAndStopsWithInjectedDeps(t *testing.T) {
	originalBuild := buildRuntimeDeps
	originalNotify := notifyContextFn
	originalNewGRPC := newGRPCServerFn
	originalListen := listenFn
	originalAfter := afterFn
	originalSetupTelemetry := setupTelemetryFn
	defer func() {
		buildRuntimeDeps = originalBuild
		notifyContextFn = originalNotify
		newGRPCServerFn = originalNewGRPC
		listenFn = originalListen
		afterFn = originalAfter
		setupTelemetryFn = originalSetupTelemetry
	}()

	cleaned := false
	buildRuntimeDeps = func(context.Context, config) (runtimeDeps, error) {
		return runtimeDeps{
			handler: reasoningv1.HandlerDependencies{Metrics: metrics.New()},
			cleanup: func() { cleaned = true },
		}, nil
	}

	ctx, cancel := context.WithCancel(context.Background())
	notifyContextFn = func(context.Context, ...os.Signal) (context.Context, context.CancelFunc) {
		return ctx, cancel
	}

	server := &fakeGRPCServer{}
	done := make(chan struct{})
	server.serveFn = func(net.Listener) error {
		cancel()
		select {
		case <-done:
		case <-time.After(100 * time.Millisecond):
			t.Fatal("timed out waiting for graceful stop")
		}
		return nil
	}
	server.gracefulStopFn = func() {
		server.gracefulStop = true
		close(done)
	}
	newGRPCServerFn = func(...grpc.ServerOption) grpcServer { return server }
	listenFn = func(string, string) (net.Listener, error) { return fakeListener{}, nil }
	afterFn = func(time.Duration) <-chan time.Time { return make(chan time.Time) }
	setupTelemetryFn = func(context.Context, string, string) (telemetry.Shutdown, error) {
		return func(context.Context) error { return nil }, nil
	}

	if err := run(); err != nil {
		t.Fatalf("run() error = %v", err)
	}
	if !server.gracefulStop {
		t.Fatal("expected GracefulStop() to be invoked")
	}
	if server.registered == 0 {
		t.Fatal("expected services to be registered")
	}
	if !cleaned {
		t.Fatal("expected cleanup to run")
	}
}

func TestRunReturnsListenErrorWithInjectedDeps(t *testing.T) {
	originalBuild := buildRuntimeDeps
	originalListen := listenFn
	defer func() {
		buildRuntimeDeps = originalBuild
		listenFn = originalListen
	}()

	cleaned := false
	buildRuntimeDeps = func(context.Context, config) (runtimeDeps, error) {
		return runtimeDeps{
			handler: reasoningv1.HandlerDependencies{Metrics: metrics.New()},
			cleanup: func() { cleaned = true },
		}, nil
	}
	listenFn = func(string, string) (net.Listener, error) { return nil, errors.New("listen failed") }

	if err := run(); err == nil || err.Error() != "listen failed" {
		t.Fatalf("run() error = %v, want listen failed", err)
	}
	if !cleaned {
		t.Fatal("expected cleanup to run on listen error")
	}
}

func TestMainExitPaths(t *testing.T) {
	originalRun := runFn
	originalExit := exitFn
	defer func() {
		runFn = originalRun
		exitFn = originalExit
	}()

	runFn = func() error { return nil }
	called := false
	exitFn = func(int) { called = true }
	main()
	if called {
		t.Fatal("exitFn should not be called on successful run")
	}

	runFn = func() error { return errors.New("boom") }
	exitCode := 0
	exitFn = func(code int) { exitCode = code }
	main()
	if exitCode != 1 {
		t.Fatalf("exit code = %d, want 1", exitCode)
	}
}
