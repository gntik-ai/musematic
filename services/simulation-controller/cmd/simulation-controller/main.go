package main

import (
	"context"
	"fmt"
	"log/slog"
	"math"
	"net"
	"os"
	"os/signal"
	"path/filepath"
	"strconv"
	"syscall"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	grpcserver "github.com/musematic/simulation-controller/api/grpc"
	simulationv1 "github.com/musematic/simulation-controller/api/grpc/v1"
	"github.com/musematic/simulation-controller/internal/artifact_collector"
	"github.com/musematic/simulation-controller/internal/ate_runner"
	"github.com/musematic/simulation-controller/internal/event_streamer"
	"github.com/musematic/simulation-controller/internal/sim_manager"
	"github.com/musematic/simulation-controller/pkg/metrics"
	"github.com/musematic/simulation-controller/pkg/persistence"
	"github.com/musematic/simulation-controller/pkg/telemetry"
	"go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc"
	"google.golang.org/grpc"
	"google.golang.org/grpc/health"
	healthpb "google.golang.org/grpc/health/grpc_health_v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
)

type config struct {
	grpcPort             int
	postgresDSN          string
	kafkaBrokers         string
	minioEndpoint        string
	simulationBucket     string
	simulationNamespace  string
	orphanScanInterval   time.Duration
	defaultMaxDuration   int32
	kubeconfig           string
	otlpExporterEndpoint string
}

type runtimeStore interface {
	InsertSimulation(ctx context.Context, record persistence.SimulationRecord) error
	UpdateSimulationStatus(ctx context.Context, simulationID string, update persistence.SimulationStatusUpdate) error
	FindATESessionIDBySimulation(ctx context.Context, simulationID string) (string, error)
	InsertSimulationArtifact(ctx context.Context, record persistence.SimulationArtifactRecord) error
	InsertATESession(ctx context.Context, record persistence.ATESessionRecord) error
	InsertATEResult(ctx context.Context, record persistence.ATEResultRecord) error
	UpdateATEReport(ctx context.Context, sessionID, objectKey string, completedAt time.Time) error
}

type runtimeUploader interface {
	Upload(ctx context.Context, key string, data []byte, metadata map[string]string) error
}

type runtimeComponents struct {
	store     runtimeStore
	producer  persistence.Producer
	uploader  runtimeUploader
	clientset kubernetes.Interface
	restCfg   *rest.Config
	listener  net.Listener
	close     func()
}

var (
	newPostgresPoolFunc  = persistence.NewPostgresPool
	newPostgresStoreFunc = func(pool *pgxpool.Pool) runtimeStore {
		return persistence.NewStore(pool)
	}
	closePostgresPoolFunc = func(pool *pgxpool.Pool) {
		if pool != nil {
			pool.Close()
		}
	}
	newRuntimeProducerFunc = func(brokers string) persistence.Producer {
		producer := persistence.NewKafkaProducer(brokers)
		if producer == nil {
			return nil
		}
		return producer
	}
	newRuntimeUploaderFunc = func(endpoint, bucket string) runtimeUploader {
		uploader := persistence.NewMinIOClient(endpoint, bucket)
		if uploader == nil {
			return nil
		}
		return uploader
	}
	newKubernetesClientFunc = func(kubeconfig string) (kubernetes.Interface, *rest.Config, error) {
		return newKubernetesClient(kubeconfig)
	}
	listenTCPFunc    = net.Listen
	setupTelemetryFn = telemetry.Setup
)

func main() {
	if err := run(); err != nil {
		slog.Error("simulation controller failed", "error", err)
		os.Exit(1)
	}
}

func run() error {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	cfg := loadConfig()
	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	serviceName := envString("OTEL_SERVICE_NAME", "simulation-controller")
	telemetryShutdown, err := setupTelemetryFn(ctx, serviceName, cfg.otlpExporterEndpoint)
	if err != nil {
		return err
	}
	defer func() {
		shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer shutdownCancel()
		_ = telemetryShutdown(shutdownCtx)
	}()

	components, err := buildRuntimeComponents(ctx, cfg)
	if err != nil {
		return err
	}
	defer components.close()
	return runWithComponents(ctx, cfg, components, logger)
}

func buildRuntimeComponents(ctx context.Context, cfg config) (runtimeComponents, error) {
	if cfg.postgresDSN == "" || cfg.kafkaBrokers == "" || cfg.minioEndpoint == "" {
		return runtimeComponents{}, fmt.Errorf("POSTGRES_DSN, KAFKA_BROKERS, and MINIO_ENDPOINT are required")
	}

	pool := newPostgresPoolFunc(cfg.postgresDSN)
	if pool == nil {
		return runtimeComponents{}, fmt.Errorf("POSTGRES_DSN is required")
	}
	store := newPostgresStoreFunc(pool)

	producer := newRuntimeProducerFunc(cfg.kafkaBrokers)
	if producer == nil {
		closePostgresPoolFunc(pool)
		return runtimeComponents{}, fmt.Errorf("KAFKA_BROKERS is required")
	}

	minio := newRuntimeUploaderFunc(cfg.minioEndpoint, cfg.simulationBucket)
	if minio == nil {
		closePostgresPoolFunc(pool)
		producer.Close()
		return runtimeComponents{}, fmt.Errorf("MINIO_ENDPOINT is required")
	}

	clientset, restCfg, err := newKubernetesClientFunc(cfg.kubeconfig)
	if err != nil {
		closePostgresPoolFunc(pool)
		producer.Close()
		return runtimeComponents{}, err
	}

	listener, err := listenTCPFunc("tcp", fmt.Sprintf(":%d", cfg.grpcPort))
	if err != nil {
		closePostgresPoolFunc(pool)
		producer.Close()
		return runtimeComponents{}, err
	}

	return runtimeComponents{
		store:     store,
		producer:  producer,
		uploader:  minio,
		clientset: clientset,
		restCfg:   restCfg,
		listener:  listener,
		close: func() {
			closePostgresPoolFunc(pool)
			producer.Close()
		},
	}, nil
}

func runWithComponents(ctx context.Context, cfg config, components runtimeComponents, logger *slog.Logger) error {
	if logger == nil {
		logger = slog.New(slog.NewJSONHandler(os.Stdout, nil))
	}

	telemetry := metrics.New()
	registry := sim_manager.NewStateRegistry()
	if err := registry.RebuildFromPodList(ctx, components.clientset, cfg.simulationNamespace); err != nil {
		return err
	}

	podManager := sim_manager.NewPodManager(components.clientset, cfg.simulationNamespace, cfg.simulationBucket, cfg.defaultMaxDuration)
	if err := podManager.EnsureNetworkPolicy(ctx); err != nil {
		return err
	}

	fanout := event_streamer.NewFanoutRegistry(64)
	watcher := &event_streamer.PodWatcher{
		Client:    components.clientset,
		Namespace: cfg.simulationNamespace,
		Fanout:    fanout,
		Producer:  components.producer,
		Logger:    logger,
	}
	streamer := event_streamer.NewStreamer(fanout, watcher)
	collector := artifact_collector.NewExecCollector(cfg.simulationNamespace, components.restCfg, components.uploader, components.store)
	aggregator := &ate_runner.ResultsAggregator{
		Fanout:   fanout,
		Store:    components.store,
		Uploader: components.uploader,
		Metrics:  telemetry,
	}
	runner := &ate_runner.Runner{
		Client:     components.clientset,
		Namespace:  cfg.simulationNamespace,
		Bucket:     cfg.simulationBucket,
		Manager:    podManager,
		Store:      components.store,
		Registry:   registry,
		Aggregator: aggregator,
		Logger:     logger,
	}

	handler := grpcserver.NewHandler(grpcserver.HandlerDependencies{
		SimManager:        podManager,
		StateRegistry:     registry,
		Store:             components.store,
		ArtifactCollector: collector,
		ATERunner:         runner,
		EventStreamer:     streamer,
		Fanout:            fanout,
		Producer:          components.producer,
		Metrics:           telemetry,
		Logger:            logger,
	})

	healthServer := health.NewServer()
	healthServer.SetServingStatus("", healthpb.HealthCheckResponse_SERVING)

	grpcServer := grpc.NewServer(
		grpc.StatsHandler(otelgrpc.NewServerHandler()),
		grpc.UnaryInterceptor(grpcserver.UnaryInterceptor(logger)),
		grpc.StreamInterceptor(grpcserver.StreamInterceptor(logger)),
	)
	simulationv1.RegisterSimulationControlServiceServer(grpcServer, handler)
	healthpb.RegisterHealthServer(grpcServer, healthServer)

	go func() {
		_ = (&sim_manager.OrphanScanner{
			Client:    components.clientset,
			Namespace: cfg.simulationNamespace,
			Registry:  registry,
			Pods:      podManager,
			Interval:  cfg.orphanScanInterval,
			Logger:    logger,
		}).Run(ctx)
	}()

	go func() {
		<-ctx.Done()
		stopped := make(chan struct{})
		go func() {
			grpcServer.GracefulStop()
			close(stopped)
		}()

		select {
		case <-stopped:
		case <-time.After(10 * time.Second):
			grpcServer.Stop()
		}
	}()

	logger.Info("simulation controller starting", "grpc_port", cfg.grpcPort)
	return grpcServer.Serve(components.listener)
}

func loadConfig() config {
	return config{
		grpcPort:             envInt("GRPC_PORT", 50055),
		postgresDSN:          os.Getenv("POSTGRES_DSN"),
		kafkaBrokers:         os.Getenv("KAFKA_BROKERS"),
		minioEndpoint:        os.Getenv("MINIO_ENDPOINT"),
		simulationBucket:     envString("SIMULATION_BUCKET", sim_manager.DefaultBucket),
		simulationNamespace:  envString("SIMULATION_NAMESPACE", sim_manager.DefaultNamespace),
		orphanScanInterval:   time.Duration(envInt("ORPHAN_SCAN_INTERVAL_SECONDS", 60)) * time.Second,
		defaultMaxDuration:   safeInt32(envInt("DEFAULT_MAX_DURATION_SECONDS", int(sim_manager.DefaultMaxDurationSec))),
		kubeconfig:           os.Getenv("KUBECONFIG"),
		otlpExporterEndpoint: os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
	}
}

func newKubernetesClient(kubeconfig string) (*kubernetes.Clientset, *rest.Config, error) {
	var (
		cfg *rest.Config
		err error
	)
	if kubeconfig != "" {
		cfg, err = clientcmd.BuildConfigFromFlags("", kubeconfig)
	} else {
		cfg, err = rest.InClusterConfig()
		if err != nil {
			defaultPath := filepath.Join(os.Getenv("HOME"), ".kube", "config")
			cfg, err = clientcmd.BuildConfigFromFlags("", defaultPath)
		}
	}
	if err != nil {
		return nil, nil, err
	}

	clientset, err := kubernetes.NewForConfig(cfg)
	if err != nil {
		return nil, nil, err
	}
	return clientset, cfg, nil
}

func envString(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func envInt(key string, fallback int) int {
	if value := os.Getenv(key); value != "" {
		parsed, err := strconv.Atoi(value)
		if err == nil {
			return parsed
		}
	}
	return fallback
}

func safeInt32(value int) int32 {
	if value > math.MaxInt32 {
		return math.MaxInt32
	}
	if value < math.MinInt32 {
		return math.MinInt32
	}
	return int32(value)
}
