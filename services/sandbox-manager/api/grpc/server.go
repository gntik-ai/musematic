package grpcserver

import (
	"context"
	"errors"
	"log/slog"

	sandboxv1 "github.com/andrea-mucci/musematic/services/sandbox-manager/api/grpc/v1"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/artifacts"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/executor"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/logs"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/sandbox"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
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

func (s *SandboxServiceServer) CreateSandbox(ctx context.Context, req *sandboxv1.CreateSandboxRequest) (*sandboxv1.CreateSandboxResponse, error) {
	entry, err := s.Manager.Create(ctx, req)
	if err != nil {
		switch {
		case errors.Is(err, sandbox.ErrTemplateNotFound):
			return nil, status.Error(codes.InvalidArgument, err.Error())
		case errors.Is(err, sandbox.ErrConcurrentLimit):
			return nil, status.Error(codes.ResourceExhausted, err.Error())
		default:
			return nil, status.Error(codes.Unavailable, err.Error())
		}
	}
	return &sandboxv1.CreateSandboxResponse{
		SandboxId: entry.SandboxID,
		State:     entry.State,
	}, nil
}

func (s *SandboxServiceServer) ExecuteSandboxStep(ctx context.Context, req *sandboxv1.ExecuteSandboxStepRequest) (*sandboxv1.ExecuteSandboxStepResponse, error) {
	result, stepNum, err := s.Executor.Execute(ctx, req.GetSandboxId(), req.GetCode(), req.GetTimeoutOverride())
	if err != nil {
		switch {
		case errors.Is(err, sandbox.ErrSandboxNotFound):
			return nil, status.Error(codes.NotFound, err.Error())
		case errors.Is(err, sandbox.ErrInvalidState):
			return nil, status.Error(codes.FailedPrecondition, err.Error())
		case errors.Is(err, context.DeadlineExceeded):
			return nil, status.Error(codes.DeadlineExceeded, err.Error())
		default:
			return nil, status.Error(codes.Internal, err.Error())
		}
	}
	return &sandboxv1.ExecuteSandboxStepResponse{
		Result:  result,
		StepNum: stepNum,
	}, nil
}

func (s *SandboxServiceServer) StreamSandboxLogs(req *sandboxv1.StreamSandboxLogsRequest, stream sandboxv1.SandboxService_StreamSandboxLogsServer) error {
	if _, err := s.Manager.Get(req.GetSandboxId()); err != nil {
		return status.Error(codes.NotFound, err.Error())
	}
	if !req.GetFollow() {
		for _, line := range s.Fanout.Buffered(req.GetSandboxId()) {
			if err := stream.Send(line); err != nil {
				return err
			}
		}
		return nil
	}
	ch, unsubscribe := s.Fanout.Subscribe(req.GetSandboxId())
	defer unsubscribe()
	for {
		select {
		case <-stream.Context().Done():
			return stream.Context().Err()
		case line, ok := <-ch:
			if !ok {
				return nil
			}
			if err := stream.Send(line); err != nil {
				return err
			}
		}
	}
}

func (s *SandboxServiceServer) TerminateSandbox(ctx context.Context, req *sandboxv1.TerminateSandboxRequest) (*sandboxv1.TerminateSandboxResponse, error) {
	if s.Collector != nil {
		if entry, err := s.Manager.Get(req.GetSandboxId()); err == nil && entry.State != sandboxv1.SandboxState_SANDBOX_STATE_FAILED {
			_, _, _ = s.Collector.Collect(ctx, *entry)
		}
	}
	if err := s.Manager.MarkTerminated(ctx, req.GetSandboxId(), int64(req.GetGracePeriodSeconds())); err != nil {
		if errors.Is(err, sandbox.ErrSandboxNotFound) {
			return nil, status.Error(codes.NotFound, err.Error())
		}
		return nil, status.Error(codes.DeadlineExceeded, err.Error())
	}
	if s.Fanout != nil {
		s.Fanout.Close(req.GetSandboxId())
	}
	return &sandboxv1.TerminateSandboxResponse{State: sandboxv1.SandboxState_SANDBOX_STATE_TERMINATED}, nil
}

func (s *SandboxServiceServer) CollectSandboxArtifacts(ctx context.Context, req *sandboxv1.CollectSandboxArtifactsRequest) (*sandboxv1.CollectSandboxArtifactsResponse, error) {
	entries, complete, err := s.Collector.CollectBySandboxID(ctx, req.GetSandboxId())
	if err != nil {
		if errors.Is(err, sandbox.ErrSandboxNotFound) {
			return nil, status.Error(codes.NotFound, err.Error())
		}
		return nil, status.Error(codes.FailedPrecondition, err.Error())
	}
	return &sandboxv1.CollectSandboxArtifactsResponse{
		Artifacts: entries,
		Complete:  complete,
	}, nil
}

func UnaryLoggingInterceptor(logger *slog.Logger) grpc.UnaryServerInterceptor {
	return func(ctx context.Context, req any, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (any, error) {
		if logger != nil {
			logger.Info("grpc unary request", "method", info.FullMethod)
		}
		return handler(ctx, req)
	}
}

func StreamLoggingInterceptor(logger *slog.Logger) grpc.StreamServerInterceptor {
	return func(srv any, ss grpc.ServerStream, info *grpc.StreamServerInfo, handler grpc.StreamHandler) error {
		if logger != nil {
			logger.Info("grpc stream request", "method", info.FullMethod)
		}
		return handler(srv, ss)
	}
}
