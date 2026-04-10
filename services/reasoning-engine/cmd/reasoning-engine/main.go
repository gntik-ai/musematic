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
}

func main() {
	if err := run(); err != nil {
		slog.Error("reasoning engine failed", "error", err)
		os.Exit(1)
	}
}

func run() error {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	cfg, err := loadConfig()
	if err != nil {
		return err
	}

	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	redisClient := persistence.NewRedisClient(cfg.redisAddr)
	if redisClient == nil {
		return fmt.Errorf("REDIS_ADDR is required")
	}
	defer redisClient.Close()

	pgPool := persistence.NewPostgresPool(cfg.postgresDSN)
	if pgPool == nil {
		return fmt.Errorf("POSTGRES_DSN is required")
	}
	defer pgPool.Close()

	kafkaProducer := persistence.NewKafkaProducer(cfg.kafkaBrokers)
	if kafkaProducer == nil {
		return fmt.Errorf("KAFKA_BROKERS is required")
	}
	defer kafkaProducer.Close()

	minioClient := persistence.NewMinIOClient(cfg.minioEndpoint, cfg.minioBucket)
	if minioClient == nil {
		return fmt.Errorf("MINIO_ENDPOINT and MINIO_BUCKET are required")
	}

	telemetry := metrics.New()
	scripts, err := lua.Load(ctx, redisClient)
	if err != nil {
		return err
	}

	eventRegistry := budget_tracker.NewEventRegistry()
	modeSelector := mode_selector.NewRuleBasedSelector()
	budgetTracker := budget_tracker.NewRedisTracker(redisClient, scripts, eventRegistry, telemetry, cfg.budgetDefaultTTLSeconds)
	traceRepository := cot_coordinator.NewPGTraceRepository(pgPool)
	traceCoordinator := cot_coordinator.NewPipeline(traceRepository, kafkaProducer, minioClient, telemetry, cfg.traceBufferSize, cfg.tracePayloadThreshold)
	escalationRouter := escalation.NewRouter(kafkaProducer)
	correctionLoop := correction_loop.NewLoopService(redisClient, scripts, kafkaProducer, escalationRouter, pgPool)
	totManager := tot_manager.NewManager(budgetTracker, quality_evaluator.StaticEvaluator{}, telemetry, cfg.maxToTConcurrency)

	healthServer := health.NewServer()
	healthServer.SetServingStatus("", healthpb.HealthCheckResponse_SERVING)

	grpcServer := grpc.NewServer(
		grpc.UnaryInterceptor(reasoningv1.UnaryInterceptor(logger)),
		grpc.StreamInterceptor(reasoningv1.StreamInterceptor(logger)),
	)
	reasoningv1.RegisterReasoningEngineServiceServer(grpcServer, reasoningv1.NewHandler(reasoningv1.HandlerDependencies{
		ModeSelector:   modeSelector,
		BudgetTracker:  budgetTracker,
		EventRegistry:  eventRegistry,
		CoTCoordinator: traceCoordinator,
		ToTManager:     totManager,
		CorrectionLoop: correctionLoop,
		Metrics:        telemetry,
	}))
	healthpb.RegisterHealthServer(grpcServer, healthServer)

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

	logger.Info("reasoning engine starting", "grpc_port", cfg.grpcPort)
	return grpcServer.Serve(listener)
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
