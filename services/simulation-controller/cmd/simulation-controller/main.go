package main

import (
	"context"
	"fmt"
	"log/slog"
	"net"
	"os"
	"os/signal"
	"path/filepath"
	"strconv"
	"syscall"
	"time"

	grpcserver "github.com/musematic/simulation-controller/api/grpc"
	simulationv1 "github.com/musematic/simulation-controller/api/grpc/v1"
	"github.com/musematic/simulation-controller/internal/artifact_collector"
	"github.com/musematic/simulation-controller/internal/ate_runner"
	"github.com/musematic/simulation-controller/internal/event_streamer"
	"github.com/musematic/simulation-controller/internal/sim_manager"
	"github.com/musematic/simulation-controller/pkg/metrics"
	"github.com/musematic/simulation-controller/pkg/persistence"
	"google.golang.org/grpc"
	"google.golang.org/grpc/health"
	healthpb "google.golang.org/grpc/health/grpc_health_v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
)

type config struct {
	grpcPort            int
	postgresDSN         string
	kafkaBrokers        string
	minioEndpoint       string
	simulationBucket    string
	simulationNamespace string
	orphanScanInterval  time.Duration
	defaultMaxDuration  int32
	kubeconfig          string
}

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

	if cfg.postgresDSN == "" || cfg.kafkaBrokers == "" || cfg.minioEndpoint == "" {
		return fmt.Errorf("POSTGRES_DSN, KAFKA_BROKERS, and MINIO_ENDPOINT are required")
	}

	pool := persistence.NewPostgresPool(cfg.postgresDSN)
	if pool == nil {
		return fmt.Errorf("POSTGRES_DSN is required")
	}
	defer pool.Close()
	store := persistence.NewStore(pool)

	producer := persistence.NewKafkaProducer(cfg.kafkaBrokers)
	if producer == nil {
		return fmt.Errorf("KAFKA_BROKERS is required")
	}
	defer producer.Close()

	minio := persistence.NewMinIOClient(cfg.minioEndpoint, cfg.simulationBucket)
	if minio == nil {
		return fmt.Errorf("MINIO_ENDPOINT is required")
	}

	clientset, restCfg, err := newKubernetesClient(cfg.kubeconfig)
	if err != nil {
		return err
	}

	telemetry := metrics.New()
	registry := sim_manager.NewStateRegistry()
	if err := registry.RebuildFromPodList(ctx, clientset, cfg.simulationNamespace); err != nil {
		return err
	}

	podManager := sim_manager.NewPodManager(clientset, cfg.simulationNamespace, cfg.simulationBucket, cfg.defaultMaxDuration)
	if err := podManager.EnsureNetworkPolicy(ctx); err != nil {
		return err
	}

	fanout := event_streamer.NewFanoutRegistry(64)
	watcher := &event_streamer.PodWatcher{
		Client:    clientset,
		Namespace: cfg.simulationNamespace,
		Fanout:    fanout,
		Producer:  producer,
		Logger:    logger,
	}
	streamer := event_streamer.NewStreamer(fanout, watcher)
	collector := artifact_collector.NewExecCollector(cfg.simulationNamespace, restCfg, minio, store)
	aggregator := &ate_runner.ResultsAggregator{
		Fanout:   fanout,
		Store:    store,
		Uploader: minio,
		Metrics:  telemetry,
	}
	runner := &ate_runner.Runner{
		Client:     clientset,
		Namespace:  cfg.simulationNamespace,
		Bucket:     cfg.simulationBucket,
		Manager:    podManager,
		Store:      store,
		Registry:   registry,
		Aggregator: aggregator,
		Logger:     logger,
	}

	handler := grpcserver.NewHandler(grpcserver.HandlerDependencies{
		SimManager:        podManager,
		StateRegistry:     registry,
		Store:             store,
		ArtifactCollector: collector,
		ATERunner:         runner,
		EventStreamer:     streamer,
		Fanout:            fanout,
		Producer:          producer,
		Metrics:           telemetry,
		Logger:            logger,
	})

	healthServer := health.NewServer()
	healthServer.SetServingStatus("", healthpb.HealthCheckResponse_SERVING)

	grpcServer := grpc.NewServer(
		grpc.UnaryInterceptor(grpcserver.UnaryInterceptor(logger)),
		grpc.StreamInterceptor(grpcserver.StreamInterceptor(logger)),
	)
	simulationv1.RegisterSimulationControlServiceServer(grpcServer, handler)
	healthpb.RegisterHealthServer(grpcServer, healthServer)

	go func() {
		_ = (&sim_manager.OrphanScanner{
			Client:    clientset,
			Namespace: cfg.simulationNamespace,
			Registry:  registry,
			Pods:      podManager,
			Interval:  cfg.orphanScanInterval,
			Logger:    logger,
		}).Run(ctx)
	}()

	listener, err := net.Listen("tcp", fmt.Sprintf(":%d", cfg.grpcPort))
	if err != nil {
		return err
	}

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
	return grpcServer.Serve(listener)
}

func loadConfig() config {
	return config{
		grpcPort:            envInt("GRPC_PORT", 50055),
		postgresDSN:         os.Getenv("POSTGRES_DSN"),
		kafkaBrokers:        os.Getenv("KAFKA_BROKERS"),
		minioEndpoint:       os.Getenv("MINIO_ENDPOINT"),
		simulationBucket:    envString("SIMULATION_BUCKET", sim_manager.DefaultBucket),
		simulationNamespace: envString("SIMULATION_NAMESPACE", sim_manager.DefaultNamespace),
		orphanScanInterval:  time.Duration(envInt("ORPHAN_SCAN_INTERVAL_SECONDS", 60)) * time.Second,
		defaultMaxDuration:  int32(envInt("DEFAULT_MAX_DURATION_SECONDS", int(sim_manager.DefaultMaxDurationSec))),
		kubeconfig:          os.Getenv("KUBECONFIG"),
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
