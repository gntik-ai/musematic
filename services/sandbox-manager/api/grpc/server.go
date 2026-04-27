package grpcserver

import (
	"context"
	"errors"
	"log/slog"

	sandboxv1 "github.com/andrea-mucci/musematic/services/sandbox-manager/api/grpc/v1"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/artifacts"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/executor"
	structuredlogging "github.com/andrea-mucci/musematic/services/sandbox-manager/internal/logging"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/logs"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/sandbox"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	otelcodes "go.opentelemetry.io/otel/codes"
	"google.golang.org/grpc"
	grpcodes "google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

type SandboxServiceServer struct {
	sandboxv1.UnimplementedSandboxServiceServer
	Manager   *sandbox.Manager
	Executor  *executor.Executor
	Collector *artifacts.Collector
	Fanout    *logs.FanoutRegistry
	Logger    *slog.Logger
}

var serverTracer = otel.Tracer("sandbox-manager/api/grpc")

func (s *SandboxServiceServer) CreateSandbox(ctx context.Context, req *sandboxv1.CreateSandboxRequest) (*sandboxv1.CreateSandboxResponse, error) {
	ctx, span := serverTracer.Start(ctx, "SandboxService/CreateSandbox")
	span.SetAttributes(
		attribute.String("template.name", req.GetTemplateName()),
		attribute.String("workspace.id", req.GetCorrelation().GetWorkspaceId()),
		attribute.String("execution.id", req.GetCorrelation().GetExecutionId()),
	)
	defer span.End()

	entry, err := s.Manager.Create(ctx, req)
	if err != nil {
		span.RecordError(err)
		span.SetStatus(otelcodes.Error, err.Error())
		switch {
		case errors.Is(err, sandbox.ErrTemplateNotFound):
			return nil, status.Error(grpcodes.InvalidArgument, err.Error())
		case errors.Is(err, sandbox.ErrConcurrentLimit):
			return nil, status.Error(grpcodes.ResourceExhausted, err.Error())
		default:
			return nil, status.Error(grpcodes.Unavailable, err.Error())
		}
	}
	span.SetAttributes(attribute.String("sandbox.id", entry.SandboxID), attribute.String("sandbox.state", entry.State.String()))
	return &sandboxv1.CreateSandboxResponse{
		SandboxId: entry.SandboxID,
		State:     entry.State,
	}, nil
}

func (s *SandboxServiceServer) ExecuteSandboxStep(ctx context.Context, req *sandboxv1.ExecuteSandboxStepRequest) (*sandboxv1.ExecuteSandboxStepResponse, error) {
	ctx, span := serverTracer.Start(ctx, "SandboxService/ExecuteSandboxStep")
	span.SetAttributes(
		attribute.String("sandbox.id", req.GetSandboxId()),
		attribute.Int("code.length", len(req.GetCode())),
		attribute.Int64("timeout.override", int64(req.GetTimeoutOverride())),
	)
	defer span.End()

	result, stepNum, err := s.Executor.Execute(ctx, req.GetSandboxId(), req.GetCode(), req.GetTimeoutOverride())
	if err != nil {
		span.RecordError(err)
		span.SetStatus(otelcodes.Error, err.Error())
		switch {
		case errors.Is(err, sandbox.ErrSandboxNotFound):
			return nil, status.Error(grpcodes.NotFound, err.Error())
		case errors.Is(err, sandbox.ErrInvalidState):
			return nil, status.Error(grpcodes.FailedPrecondition, err.Error())
		case errors.Is(err, context.DeadlineExceeded):
			return nil, status.Error(grpcodes.DeadlineExceeded, err.Error())
		default:
			return nil, status.Error(grpcodes.Internal, err.Error())
		}
	}
	span.SetAttributes(
		attribute.Int64("execution.step_num", int64(stepNum)),
		attribute.Int64("execution.exit_code", int64(result.GetExitCode())),
		attribute.Bool("execution.timed_out", result.GetTimedOut()),
		attribute.Bool("execution.oom_killed", result.GetOomKilled()),
	)
	return &sandboxv1.ExecuteSandboxStepResponse{
		Result:  result,
		StepNum: stepNum,
	}, nil
}

func (s *SandboxServiceServer) StreamSandboxLogs(req *sandboxv1.StreamSandboxLogsRequest, stream sandboxv1.SandboxService_StreamSandboxLogsServer) error {
	ctx, span := serverTracer.Start(stream.Context(), "SandboxService/StreamSandboxLogs")
	span.SetAttributes(attribute.String("sandbox.id", req.GetSandboxId()), attribute.Bool("stream.follow", req.GetFollow()))
	defer span.End()

	if _, err := s.Manager.Get(req.GetSandboxId()); err != nil {
		span.RecordError(err)
		span.SetStatus(otelcodes.Error, err.Error())
		return status.Error(grpcodes.NotFound, err.Error())
	}
	if !req.GetFollow() {
		for _, line := range s.Fanout.Buffered(req.GetSandboxId()) {
			if err := stream.Send(line); err != nil {
				span.RecordError(err)
				span.SetStatus(otelcodes.Error, err.Error())
				return err
			}
		}
		return nil
	}
	ch, unsubscribe := s.Fanout.Subscribe(req.GetSandboxId())
	defer unsubscribe()
	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case line, ok := <-ch:
			if !ok {
				return nil
			}
			if err := stream.Send(line); err != nil {
				span.RecordError(err)
				span.SetStatus(otelcodes.Error, err.Error())
				return err
			}
		}
	}
}

func (s *SandboxServiceServer) TerminateSandbox(ctx context.Context, req *sandboxv1.TerminateSandboxRequest) (*sandboxv1.TerminateSandboxResponse, error) {
	ctx, span := serverTracer.Start(ctx, "SandboxService/TerminateSandbox")
	span.SetAttributes(
		attribute.String("sandbox.id", req.GetSandboxId()),
		attribute.Int64("grace_period_seconds", int64(req.GetGracePeriodSeconds())),
	)
	defer span.End()

	if s.Collector != nil {
		if entry, err := s.Manager.Get(req.GetSandboxId()); err == nil && entry.State != sandboxv1.SandboxState_SANDBOX_STATE_FAILED {
			_, _, _ = s.Collector.Collect(ctx, *entry)
		}
	}
	if err := s.Manager.MarkTerminated(ctx, req.GetSandboxId(), int64(req.GetGracePeriodSeconds())); err != nil {
		span.RecordError(err)
		span.SetStatus(otelcodes.Error, err.Error())
		if errors.Is(err, sandbox.ErrSandboxNotFound) {
			return nil, status.Error(grpcodes.NotFound, err.Error())
		}
		return nil, status.Error(grpcodes.DeadlineExceeded, err.Error())
	}
	if s.Fanout != nil {
		s.Fanout.Close(req.GetSandboxId())
	}
	span.SetAttributes(attribute.String("sandbox.state", sandboxv1.SandboxState_SANDBOX_STATE_TERMINATED.String()))
	return &sandboxv1.TerminateSandboxResponse{State: sandboxv1.SandboxState_SANDBOX_STATE_TERMINATED}, nil
}

func (s *SandboxServiceServer) CollectSandboxArtifacts(ctx context.Context, req *sandboxv1.CollectSandboxArtifactsRequest) (*sandboxv1.CollectSandboxArtifactsResponse, error) {
	ctx, span := serverTracer.Start(ctx, "SandboxService/CollectSandboxArtifacts")
	span.SetAttributes(attribute.String("sandbox.id", req.GetSandboxId()))
	defer span.End()

	entries, complete, err := s.Collector.CollectBySandboxID(ctx, req.GetSandboxId())
	if err != nil {
		span.RecordError(err)
		span.SetStatus(otelcodes.Error, err.Error())
		if errors.Is(err, sandbox.ErrSandboxNotFound) {
			return nil, status.Error(grpcodes.NotFound, err.Error())
		}
		return nil, status.Error(grpcodes.FailedPrecondition, err.Error())
	}
	span.SetAttributes(attribute.Int("artifact.count", len(entries)), attribute.Bool("artifact.complete", complete))
	return &sandboxv1.CollectSandboxArtifactsResponse{
		Artifacts: entries,
		Complete:  complete,
	}, nil
}

func UnaryLoggingInterceptor(logger *slog.Logger) grpc.UnaryServerInterceptor {
	return func(ctx context.Context, req any, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (any, error) {
		ctx = structuredlogging.WithGRPCMetadata(ctx)
		if logger != nil {
			logger.InfoContext(ctx, "grpc unary request", "method", info.FullMethod)
		}
		return handler(ctx, req)
	}
}

func StreamLoggingInterceptor(logger *slog.Logger) grpc.StreamServerInterceptor {
	return func(srv any, ss grpc.ServerStream, info *grpc.StreamServerInfo, handler grpc.StreamHandler) error {
		wrapped := metadataServerStream{ServerStream: ss, ctx: structuredlogging.WithGRPCMetadata(ss.Context())}
		if logger != nil {
			logger.InfoContext(wrapped.Context(), "grpc stream request", "method", info.FullMethod)
		}
		return handler(srv, wrapped)
	}
}

type metadataServerStream struct {
	grpc.ServerStream
	ctx context.Context
}

func (s metadataServerStream) Context() context.Context {
	return s.ctx
}
