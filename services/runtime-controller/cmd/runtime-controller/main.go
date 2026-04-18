package main

import (
	"context"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	grpcserver "github.com/andrea-mucci/musematic/services/runtime-controller/api/grpc"
	runtimev1 "github.com/andrea-mucci/musematic/services/runtime-controller/api/grpc/v1"
	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/artifacts"
	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/events"
	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/heartbeat"
	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/launcher"
	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/reconciler"
	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/state"
	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/warmpool"
	"github.com/andrea-mucci/musematic/services/runtime-controller/pkg/config"
	"github.com/andrea-mucci/musematic/services/runtime-controller/pkg/health"
	k8spkg "github.com/andrea-mucci/musematic/services/runtime-controller/pkg/k8s"
	runtimemetrics "github.com/andrea-mucci/musematic/services/runtime-controller/pkg/metrics"
	"github.com/andrea-mucci/musematic/services/runtime-controller/pkg/telemetry"
	"github.com/aws/aws-sdk-go-v2/aws"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/confluentinc/confluent-kafka-go/v2/kafka"
	"github.com/redis/go-redis/v9"
	"google.golang.org/grpc"
)

type redisPinger struct{ client *redis.Client }

func (r redisPinger) Ping(ctx context.Context) error { return r.client.Ping(ctx).Err() }

type restHealth struct{}

func (restHealth) DoRaw(context.Context, string) ([]byte, error) { return []byte("ok"), nil }

func main() {
	if err := run(); err != nil {
		slog.Error("runtime controller failed", "error", err)
		os.Exit(1)
	}
}

func run() error {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	cfg, err := config.Load()
	if err != nil {
		return err
	}
	serviceName := os.Getenv("OTEL_SERVICE_NAME")
	if serviceName == "" {
		serviceName = "runtime-controller"
	}
	telemetryShutdown, err := telemetry.Setup(context.Background(), serviceName, cfg.OTLPExporterEndpoint)
	if err != nil {
		return err
	}
	defer func() { _ = telemetryShutdown(context.Background()) }()

	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	store, err := state.NewStore(ctx, cfg.PostgresDSN)
	if err != nil {
		return err
	}
	defer store.Close()
	if err := state.RunMigrations(ctx, store.Pool()); err != nil {
		return err
	}
	for targetKey, targetSize := range cfg.WarmPoolTargets {
		workspaceID, agentType := splitTargetKey(targetKey)
		if workspaceID == "" || agentType == "" {
			continue
		}
		if err := store.EnsureWarmPoolTarget(ctx, workspaceID, agentType, targetSize); err != nil {
			return err
		}
	}
	awsCfg, err := awsconfig.LoadDefaultConfig(ctx)
	if err != nil {
		return err
	}
	s3Client := s3.NewFromConfig(awsCfg, func(o *s3.Options) {
		o.BaseEndpoint = aws.String(cfg.MinIOEndpoint)
		o.UsePathStyle = true
	})
	store.TaskPlanUploader = state.S3TaskPlanUploader{Client: s3Client, Bucket: cfg.MinIOBucket}

	redisClient := redis.NewClient(&redis.Options{Addr: cfg.RedisAddr})
	defer func() {
		if closeErr := redisClient.Close(); closeErr != nil {
			logger.Warn("failed to close redis client", "error", closeErr)
		}
	}()

	var kafkaProducer *kafka.Producer
	if producer, err := events.NewKafkaProducer(cfg.KafkaBrokers); err == nil {
		kafkaProducer = producer.(*kafka.Producer)
		defer kafkaProducer.Close()
	}

	clientset, restConfig, err := k8spkg.NewClient()
	if err != nil && !cfg.K8sDryRun {
		return err
	}
	podClient := &k8spkg.PodClient{Client: clientset, RestConfig: restConfig, Namespace: cfg.K8sNamespace, DryRun: cfg.K8sDryRun}
	fanout := events.NewFanoutRegistry()
	metricRegistry := runtimemetrics.NewRegistry()
	var emitter *events.EventEmitter
	if kafkaProducer != nil {
		emitter = events.NewEventEmitter(kafkaProducer)
	} else {
		emitter = events.NewEventEmitter(nil)
	}
	warmPoolManager := warmpool.NewManager(store)
	_ = warmPoolManager.LoadFromDB(ctx, store)
	var kafkaHealth health.KafkaMetadataChecker
	if kafkaProducer != nil {
		kafkaHealth = kafkaProducer
	}

	launchService := &launcher.Launcher{
		Namespace:  cfg.K8sNamespace,
		PresignTTL: cfg.AgentPackagePresignTTL,
		Store:      store,
		Pods:       podClient,
		Secrets:    launcher.KubernetesSecretResolver{Client: clientset, Namespace: cfg.K8sNamespace},
		Emitter:    emitter,
		Fanout:     fanout,
		WarmPool:   warmPoolManager,
	}
	collector := &artifacts.Collector{
		Store:    store,
		Pods:     podClient,
		Uploader: &artifacts.BytesUploader{},
	}

	httpMux := http.NewServeMux()
	httpMux.HandleFunc("/healthz", health.LivezHandler)
	httpMux.Handle("/readyz", health.ReadyzHandler(health.Dependencies{
		Postgres: store.Pool(),
		Redis:    redisPinger{client: redisClient},
		Kafka:    kafkaHealth,
		K8s:      restHealth{},
	}))
	httpMux.HandleFunc("/metrics", metricRegistry.Handler())
	httpServer := &http.Server{
		Addr:              net.JoinHostPort("", toPort(cfg.HTTPPort)),
		Handler:           httpMux,
		ReadHeaderTimeout: 5 * time.Second,
	}

	grpcServer := grpc.NewServer(
		grpc.ChainUnaryInterceptor(grpcserver.UnaryTracingInterceptor(), grpcserver.UnaryLoggingInterceptor(logger)),
		grpc.ChainStreamInterceptor(grpcserver.StreamTracingInterceptor(), grpcserver.StreamLoggingInterceptor(logger)),
	)
	runtimev1.RegisterRuntimeControlServiceServer(grpcServer, &grpcserver.RuntimeControlServiceServer{
		Launcher:  launchService,
		Store:     store,
		Pods:      podClient,
		Collector: collector,
		Fanout:    fanout,
		Logger:    logger,
		Metrics:   metricRegistry,
	})

	reconcileLoop := &reconciler.Reconciler{
		Interval: cfg.ReconcileInterval,
		Store:    store,
		Pods:     podClient,
		Emitter:  emitter,
		Fanout:   fanout,
		Logger:   logger,
		Metrics:  metricRegistry,
	}
	heartbeatLoop := &heartbeat.Scanner{
		Redis:    redisClient,
		Store:    store,
		Interval: cfg.HeartbeatCheckInterval,
		Emitter:  emitter,
		Fanout:   fanout,
		Logger:   logger,
		Metrics:  metricRegistry,
	}
	replenisher := &warmpool.Replenisher{Interval: cfg.WarmPoolReplenishInterval, Logger: logger, Store: store, Manager: warmPoolManager, Pods: podClient, Namespace: cfg.K8sNamespace}
	idleScanner := &warmpool.IdleScanner{Interval: cfg.WarmPoolReplenishInterval, IdleTimeout: cfg.WarmPoolIdleTimeout, Logger: logger, Store: store, Pods: podClient, Manager: warmPoolManager}

	go func() { _ = reconcileLoop.Run(ctx) }()
	go func() { _ = heartbeatLoop.Run(ctx) }()
	go func() { _ = replenisher.Run(ctx, cfg.WarmPoolTargets) }()
	go func() { _ = idleScanner.Run(ctx) }()

	go func() {
		<-ctx.Done()
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		_ = httpServer.Shutdown(shutdownCtx)
		grpcServer.GracefulStop()
	}()

	go func() {
		if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.Error("http server failed", "error", err)
			cancel()
		}
	}()

	listener, err := net.Listen("tcp", net.JoinHostPort("", toPort(cfg.GRPCPort)))
	if err != nil {
		return err
	}
	logger.Info("runtime controller starting", "grpc_port", cfg.GRPCPort, "http_port", cfg.HTTPPort)
	return grpcServer.Serve(listener)
}

func toPort(port int) string {
	return strconv.Itoa(port)
}

func splitTargetKey(value string) (string, string) {
	for i := 0; i < len(value); i++ {
		if value[i] == '/' {
			return value[:i], value[i+1:]
		}
	}
	return value, ""
}
