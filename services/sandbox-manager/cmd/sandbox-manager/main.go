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
	"github.com/andrea-mucci/musematic/services/sandbox-manager/pkg/telemetry"
	"github.com/confluentinc/confluent-kafka-go/v2/kafka"
	"go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc"
	"google.golang.org/grpc"
)

type postgresDB interface {
	Ping(context.Context) error
}

type postgresPinger struct{ db postgresDB }

type metadataProducer interface {
	GetMetadata(*string, bool, int) (*kafka.Metadata, error)
}

func (p postgresPinger) Ping(ctx context.Context) error {
	if p.db == nil {
		return nil
	}
	return p.db.Ping(ctx)
}

type kafkaHealth struct{ producer metadataProducer }

func (k kafkaHealth) GetMetadata(topic *string, allTopics bool, timeoutMs int) (*struct{}, error) {
	if k.producer == nil {
		return &struct{}{}, nil
	}
	_, err := k.producer.GetMetadata(topic, allTopics, timeoutMs)
	return &struct{}{}, err
}

type k8sHealth struct{}

func (k8sHealth) DoRaw(context.Context, string) ([]byte, error) { return []byte("ok"), nil }

type runtimeStore interface {
	sandbox.Store
	Ping(context.Context) error
	RunMigrations(context.Context) error
	Close()
}

type liveRuntimeStore struct {
	*state.Store
}

func (s liveRuntimeStore) Ping(ctx context.Context) error {
	if s.Store == nil || s.Pool() == nil {
		return nil
	}
	return s.Pool().Ping(ctx)
}

func (s liveRuntimeStore) RunMigrations(ctx context.Context) error {
	if s.Store == nil || s.Pool() == nil {
		return nil
	}
	return state.RunMigrations(ctx, s.Pool())
}

type httpServer interface {
	ListenAndServe() error
	Shutdown(context.Context) error
}

type grpcServer interface {
	Serve(net.Listener) error
	GracefulStop()
}

type scanner interface {
	Run(context.Context) error
}

type runtimeDeps struct {
	cfg               config.Config
	telemetryShutdown telemetry.Shutdown
	store             runtimeStore
	producer          events.Producer
	httpServer        httpServer
	grpcServer        grpcServer
	listener          net.Listener
	orphanScanner     scanner
	idleScanner       scanner
}

func (d *runtimeDeps) close() {
	if d == nil {
		return
	}
	if d.listener != nil {
		_ = d.listener.Close()
	}
	if d.producer != nil {
		d.producer.Close()
	}
	if d.store != nil {
		d.store.Close()
	}
	if d.telemetryShutdown != nil {
		shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer shutdownCancel()
		_ = d.telemetryShutdown(shutdownCtx)
	}
}

var (
	loadConfigFn     = config.Load
	notifyContextFn  = signal.NotifyContext
	setupTelemetryFn = telemetry.Setup
	newRuntimeStore  = func(ctx context.Context, dsn string) (runtimeStore, error) {
		store, err := state.NewStore(ctx, dsn)
		if err != nil {
			return nil, err
		}
		return liveRuntimeStore{Store: store}, nil
	}
	newK8sClientFn     = k8spkg.NewClient
	newKafkaProducerFn = events.NewKafkaProducer
	listenFn           = net.Listen
	buildRuntimeDepsFn = defaultBuildRuntimeDeps
	runFn              = run
	exitFn             = os.Exit
)

func main() {
	if err := runFn(); err != nil {
		slog.Error("sandbox manager failed", "error", err)
		exitFn(1)
	}
}

func run() error {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	cfg, err := loadConfigFn()
	if err != nil {
		return err
	}
	ctx, cancel := notifyContextFn(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()
	deps, err := buildRuntimeDepsFn(ctx, logger, cfg)
	if err != nil {
		return err
	}
	defer deps.close()

	if deps.orphanScanner != nil {
		go func() {
			_ = deps.orphanScanner.Run(ctx)
		}()
	}
	if deps.idleScanner != nil {
		go func() {
			_ = deps.idleScanner.Run(ctx)
		}()
	}
	go func() {
		<-ctx.Done()
		shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer shutdownCancel()
		_ = deps.httpServer.Shutdown(shutdownCtx)
		deps.grpcServer.GracefulStop()
	}()
	go func() {
		if err := deps.httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.Error("http server failed", "error", err)
			cancel()
		}
	}()
	logger.Info("sandbox manager starting", "grpc_port", cfg.GRPCPort, "http_port", cfg.HTTPPort)
	return deps.grpcServer.Serve(deps.listener)
}

func defaultBuildRuntimeDeps(ctx context.Context, logger *slog.Logger, cfg config.Config) (*runtimeDeps, error) {
	deps := &runtimeDeps{cfg: cfg}

	telemetryShutdown, err := setupTelemetryFn(ctx, "sandbox-manager", cfg.OTLPExporterEndpoint)
	if err != nil {
		return nil, err
	}
	deps.telemetryShutdown = telemetryShutdown

	store, err := newRuntimeStore(ctx, cfg.PostgresDSN)
	if err != nil {
		deps.close()
		return nil, err
	}
	deps.store = store
	if err := store.RunMigrations(ctx); err != nil {
		deps.close()
		return nil, err
	}

	clientset, restCfg, err := newK8sClientFn()
	if err != nil && !cfg.K8sDryRun {
		deps.close()
		return nil, err
	}
	podClient := &k8spkg.PodClient{Client: clientset, Namespace: cfg.K8sNamespace, DryRun: cfg.K8sDryRun}

	var healthProducer metadataProducer
	if producer, producerErr := newKafkaProducerFn(cfg.KafkaBrokers); producerErr == nil {
		deps.producer = producer
		if typed, ok := producer.(metadataProducer); ok {
			healthProducer = typed
		}
	}
	emitter := events.NewEventEmitter(deps.producer)
	fanout := logs.NewFanoutRegistry(100)
	streamer := &logs.Streamer{Client: podClient, Fanout: fanout}
	archiveStreamer := artifacts.NewExecArchiveStreamer(restCfg)
	uploader := artifacts.NewMinIOUploader(cfg.MinIOEndpoint, cfg.MinIOBucket)
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
	collector := artifacts.NewCollector(manager, archiveStreamer, uploader, cfg.MinIOBucket)

	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", health.LivezHandler)
	mux.Handle("/readyz", health.ReadyzHandler(health.Dependencies{
		Postgres: postgresPinger{db: store},
		Kafka:    kafkaHealth{producer: healthProducer},
		K8s:      k8sHealth{},
	}))
	deps.httpServer = &http.Server{
		Addr:              net.JoinHostPort("", strconv.Itoa(cfg.HTTPPort)),
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
	}

	grpcSrv := grpc.NewServer(
		grpc.StatsHandler(otelgrpc.NewServerHandler()),
		grpc.UnaryInterceptor(grpcserver.UnaryLoggingInterceptor(logger)),
		grpc.StreamInterceptor(grpcserver.StreamLoggingInterceptor(logger)),
	)
	sandboxv1.RegisterSandboxServiceServer(grpcSrv, &grpcserver.SandboxServiceServer{
		Manager:   manager,
		Executor:  execSvc,
		Collector: collector,
		Fanout:    fanout,
		Logger:    logger,
	})
	deps.grpcServer = grpcSrv

	listener, err := listenFn("tcp", net.JoinHostPort("", strconv.Itoa(cfg.GRPCPort)))
	if err != nil {
		deps.close()
		return nil, err
	}
	deps.listener = listener
	deps.orphanScanner = &cleanup.OrphanScanner{Pods: podClient, Manager: manager, Interval: cfg.OrphanScanInterval}
	deps.idleScanner = &cleanup.IdleScanner{Manager: manager, IdleTimeout: cfg.IdleTimeout, Interval: 30 * time.Second}
	return deps, nil
}
