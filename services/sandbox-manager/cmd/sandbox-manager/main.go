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

	grpcserver "github.com/andrea-mucci/musematic/services/sandbox-manager/api/grpc"
	sandboxv1 "github.com/andrea-mucci/musematic/services/sandbox-manager/api/grpc/v1"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/artifacts"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/cleanup"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/events"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/executor"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/logs"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/sandbox"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/state"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/pkg/config"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/pkg/health"
	k8spkg "github.com/andrea-mucci/musematic/services/sandbox-manager/pkg/k8s"
	"github.com/confluentinc/confluent-kafka-go/v2/kafka"
	"google.golang.org/grpc"
)

type postgresPinger struct{ store *state.Store }

func (p postgresPinger) Ping(ctx context.Context) error { return p.store.Pool().Ping(ctx) }

type kafkaHealth struct{ producer *kafka.Producer }

func (k kafkaHealth) GetMetadata(topic *string, allTopics bool, timeoutMs int) (*struct{}, error) {
	if k.producer == nil {
		return &struct{}{}, nil
	}
	_, err := k.producer.GetMetadata(topic, allTopics, timeoutMs)
	return &struct{}{}, err
}

type k8sHealth struct{}

func (k8sHealth) DoRaw(context.Context, string) ([]byte, error) { return []byte("ok"), nil }

func main() {
	if err := run(); err != nil {
		slog.Error("sandbox manager failed", "error", err)
		os.Exit(1)
	}
}

func run() error {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	cfg, err := config.Load()
	if err != nil {
		return err
	}
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

	clientset, restCfg, err := k8spkg.NewClient()
	if err != nil && !cfg.K8sDryRun {
		return err
	}
	podClient := &k8spkg.PodClient{Client: clientset, Namespace: cfg.K8sNamespace, DryRun: cfg.K8sDryRun}

	var producer *kafka.Producer
	if created, err := events.NewKafkaProducer(cfg.KafkaBrokers); err == nil {
		producer = created.(*kafka.Producer)
		defer producer.Close()
	}
	emitter := events.NewEventEmitter(producer)
	fanout := logs.NewFanoutRegistry(100)
	streamer := &logs.Streamer{Client: podClient, Fanout: fanout}
	manager := sandbox.NewManager(sandbox.ManagerConfig{
		Namespace:      cfg.K8sNamespace,
		DefaultTimeout: cfg.DefaultTimeout,
		MaxTimeout:     cfg.MaxTimeout,
		MaxConcurrent:  cfg.MaxConcurrentSandboxes,
		Store:          store,
		Pods:           podClient,
		Emitter:        emitter,
		ReadyCallback: func(entry sandbox.Entry) {
			go func() { _ = streamer.StreamPodLogs(ctx, entry.SandboxID, entry.PodName) }()
		},
	})
	execSvc := executor.New(manager, podClient, restCfg, cfg.MaxOutputSize)
	collector := artifacts.NewCollector(manager, nil, artifacts.NoopUploader{}, cfg.MinIOBucket)

	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", health.LivezHandler)
	mux.Handle("/readyz", health.ReadyzHandler(health.Dependencies{
		Postgres: postgresPinger{store: store},
		Kafka:    kafkaHealth{producer: producer},
		K8s:      k8sHealth{},
	}))
	httpServer := &http.Server{
		Addr:              net.JoinHostPort("", strconv.Itoa(cfg.HTTPPort)),
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
	}

	grpcServer := grpc.NewServer(
		grpc.UnaryInterceptor(grpcserver.UnaryLoggingInterceptor(logger)),
		grpc.StreamInterceptor(grpcserver.StreamLoggingInterceptor(logger)),
	)
	sandboxv1.RegisterSandboxServiceServer(grpcServer, &grpcserver.SandboxServiceServer{
		Manager:   manager,
		Executor:  execSvc,
		Collector: collector,
		Fanout:    fanout,
		Logger:    logger,
	})

	go func() {
		_ = (&cleanup.OrphanScanner{Pods: podClient, Manager: manager, Interval: cfg.OrphanScanInterval}).Run(ctx)
	}()
	go func() {
		_ = (&cleanup.IdleScanner{Manager: manager, IdleTimeout: cfg.IdleTimeout, Interval: 30 * time.Second}).Run(ctx)
	}()
	go func() {
		<-ctx.Done()
		shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer shutdownCancel()
		_ = httpServer.Shutdown(shutdownCtx)
		grpcServer.GracefulStop()
	}()
	go func() {
		if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.Error("http server failed", "error", err)
			cancel()
		}
	}()

	listener, err := net.Listen("tcp", net.JoinHostPort("", strconv.Itoa(cfg.GRPCPort)))
	if err != nil {
		return err
	}
	logger.Info("sandbox manager starting", "grpc_port", cfg.GRPCPort, "http_port", cfg.HTTPPort)
	return grpcServer.Serve(listener)
}
