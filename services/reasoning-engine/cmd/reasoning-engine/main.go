package main

import (
	"context"
	"fmt"
	"log/slog"
	"net"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	reasoningv1 "github.com/musematic/reasoning-engine/api/grpc/v1"
	"github.com/musematic/reasoning-engine/internal/budget_tracker"
	"github.com/musematic/reasoning-engine/internal/correction_loop"
	"github.com/musematic/reasoning-engine/internal/cot_coordinator"
	"github.com/musematic/reasoning-engine/internal/escalation"
	"github.com/musematic/reasoning-engine/internal/mode_selector"
	"github.com/musematic/reasoning-engine/internal/quality_evaluator"
	"github.com/musematic/reasoning-engine/internal/tot_manager"
	"github.com/musematic/reasoning-engine/pkg/lua"
	"github.com/musematic/reasoning-engine/pkg/metrics"
	"github.com/musematic/reasoning-engine/pkg/persistence"
	"github.com/musematic/reasoning-engine/pkg/telemetry"
	"go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc"
	"google.golang.org/grpc"
	"google.golang.org/grpc/health"
	healthpb "google.golang.org/grpc/health/grpc_health_v1"
)

type config struct {
	grpcPort                int
	redisAddr               string
	postgresDSN             string
	kafkaBrokers            string
	minioEndpoint           string
	minioBucket             string
	maxToTConcurrency       int
	traceBufferSize         int
	tracePayloadThreshold   int
	budgetDefaultTTLSeconds int64
	otlpExporterEndpoint    string
}

type grpcServer interface {
	RegisterService(*grpc.ServiceDesc, any)
	Serve(net.Listener) error
	GracefulStop()
	Stop()
}

type runtimeDeps struct {
	handler reasoningv1.HandlerDependencies
	cleanup func()
}

var (
	buildRuntimeDeps           = defaultBuildRuntimeDeps
	notifyContextFn            = signal.NotifyContext
	newGRPCServerFn            = func(opts ...grpc.ServerOption) grpcServer { return grpc.NewServer(opts...) }
	registerReasoningServiceFn = reasoningv1.RegisterReasoningEngineServiceServer
	registerHealthServiceFn    = healthpb.RegisterHealthServer
	listenFn                   = net.Listen
	afterFn                    = time.After
	runFn                      = run
	exitFn                     = os.Exit
	loadLuaFn                  = lua.Load
	setupTelemetryFn           = telemetry.Setup
)

func main() {
	if err := runFn(); err != nil {
		slog.Error("reasoning engine failed", "error", err)
		exitFn(1)
	}
}

func run() error {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	cfg, err := loadConfig()
	if err != nil {
		return err
	}

	ctx, cancel := notifyContextFn(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	serviceName := envString("OTEL_SERVICE_NAME", "reasoning-engine")
	telemetryShutdown, err := setupTelemetryFn(ctx, serviceName, cfg.otlpExporterEndpoint)
	if err != nil {
		return err
	}
	defer func() {
		shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer shutdownCancel()
		_ = telemetryShutdown(shutdownCtx)
	}()

	deps, err := buildRuntimeDeps(ctx, cfg)
	if err != nil {
		return err
	}
	defer deps.cleanup()

	healthServer := health.NewServer()
	healthServer.SetServingStatus("", healthpb.HealthCheckResponse_SERVING)

	grpcServer := newGRPCServerFn(
		grpc.StatsHandler(otelgrpc.NewServerHandler()),
		grpc.UnaryInterceptor(reasoningv1.UnaryInterceptor(logger)),
		grpc.StreamInterceptor(reasoningv1.StreamInterceptor(logger)),
	)
	registerReasoningServiceFn(grpcServer, reasoningv1.NewHandler(deps.handler))
	registerHealthServiceFn(grpcServer, healthServer)

	listener, err := listenFn("tcp", fmt.Sprintf(":%d", cfg.grpcPort))
	if err != nil {
		return err
	}

	go func() {
		shutdownAfter := afterFn
		<-ctx.Done()
		stopped := make(chan struct{})
		go func() {
			grpcServer.GracefulStop()
			close(stopped)
		}()

		select {
		case <-stopped:
		case <-shutdownAfter(10 * time.Second):
			grpcServer.Stop()
		}
	}()

	logger.Info("reasoning engine starting", "grpc_port", cfg.grpcPort)
	return grpcServer.Serve(listener)
}

func defaultBuildRuntimeDeps(ctx context.Context, cfg config) (runtimeDeps, error) {
	redisClient := persistence.NewRedisClient(cfg.redisAddr)
	if redisClient == nil {
		return runtimeDeps{}, fmt.Errorf("REDIS_ADDR is required")
	}

	pgPool := persistence.NewPostgresPool(cfg.postgresDSN)
	if pgPool == nil {
		_ = redisClient.Close()
		return runtimeDeps{}, fmt.Errorf("POSTGRES_DSN is required")
	}

	kafkaProducer := persistence.NewKafkaProducer(cfg.kafkaBrokers)
	if kafkaProducer == nil {
		pgPool.Close()
		_ = redisClient.Close()
		return runtimeDeps{}, fmt.Errorf("KAFKA_BROKERS is required")
	}

	minioClient := persistence.NewMinIOClient(cfg.minioEndpoint, cfg.minioBucket)
	if minioClient == nil {
		kafkaProducer.Close()
		pgPool.Close()
		_ = redisClient.Close()
		return runtimeDeps{}, fmt.Errorf("MINIO_ENDPOINT and MINIO_BUCKET are required")
	}

	telemetry := metrics.New()
	scripts, err := loadLuaFn(ctx, redisClient)
	if err != nil {
		kafkaProducer.Close()
		pgPool.Close()
		_ = redisClient.Close()
		return runtimeDeps{}, err
	}

	eventRegistry := budget_tracker.NewEventRegistry()
	modeSelector := mode_selector.NewRuleBasedSelector()
	budgetTracker := budget_tracker.NewRedisTracker(redisClient, scripts, eventRegistry, telemetry, cfg.budgetDefaultTTLSeconds)
	traceRepository := cot_coordinator.NewPGTraceRepository(pgPool)
	traceCoordinator := cot_coordinator.NewPipeline(traceRepository, kafkaProducer, minioClient, telemetry, cfg.traceBufferSize, cfg.tracePayloadThreshold)
	escalationRouter := escalation.NewRouter(kafkaProducer)
	correctionLoop := correction_loop.NewLoopService(redisClient, scripts, kafkaProducer, escalationRouter, pgPool)
	totManager := tot_manager.NewManager(budgetTracker, quality_evaluator.StaticEvaluator{}, telemetry, cfg.maxToTConcurrency)

	return runtimeDeps{
		handler: reasoningv1.HandlerDependencies{
			ModeSelector:   modeSelector,
			BudgetTracker:  budgetTracker,
			EventRegistry:  eventRegistry,
			CoTCoordinator: traceCoordinator,
			ToTManager:     totManager,
			CorrectionLoop: correctionLoop,
			Metrics:        telemetry,
		},
		cleanup: func() {
			kafkaProducer.Close()
			pgPool.Close()
			_ = redisClient.Close()
		},
	}, nil
}

func loadConfig() (config, error) {
	return config{
		grpcPort:                envInt("GRPC_PORT", 50052),
		redisAddr:               os.Getenv("REDIS_ADDR"),
		postgresDSN:             os.Getenv("POSTGRES_DSN"),
		kafkaBrokers:            os.Getenv("KAFKA_BROKERS"),
		minioEndpoint:           os.Getenv("MINIO_ENDPOINT"),
		minioBucket:             envString("MINIO_BUCKET", "reasoning-traces"),
		maxToTConcurrency:       envInt("MAX_TOT_CONCURRENCY", 10),
		traceBufferSize:         envInt("TRACE_BUFFER_SIZE", 10000),
		tracePayloadThreshold:   envInt("TRACE_PAYLOAD_THRESHOLD", 65536),
		budgetDefaultTTLSeconds: envInt64("BUDGET_DEFAULT_TTL_SECONDS", 3600),
		otlpExporterEndpoint:    os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
	}, nil
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

func envInt64(key string, fallback int64) int64 {
	if value := os.Getenv(key); value != "" {
		parsed, err := strconv.ParseInt(value, 10, 64)
		if err == nil {
			return parsed
		}
	}
	return fallback
}
