package grpcserver

import (
	"context"
	"errors"
	"log/slog"
	"time"

	runtimev1 "github.com/andrea-mucci/musematic/services/runtime-controller/api/grpc/v1"
	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/artifacts"
	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/events"
	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/launcher"
	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/state"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"
)

type PodExecutor interface {
	ExecInPod(context.Context, string, []string) ([]byte, error)
	DeletePod(context.Context, string, int64) error
}

type Store interface {
	GetRuntimeByExecutionID(context.Context, string) (state.RuntimeRecord, error)
	UpdateRuntimeState(context.Context, string, string, string) error
	GetRuntimeEventsSince(context.Context, string, time.Time) ([]state.RuntimeEventRecord, error)
	InsertRuntimeEvent(context.Context, state.RuntimeEventRecord) error
}

type RuntimeControlServiceServer struct {
	runtimev1.UnimplementedRuntimeControlServiceServer
	Launcher  *launcher.Launcher
	Store     Store
	Pods      PodExecutor
	Collector *artifacts.Collector
	Fanout    *events.FanoutRegistry
	Logger    *slog.Logger
}

func (s *RuntimeControlServiceServer) LaunchRuntime(ctx context.Context, req *runtimev1.LaunchRuntimeRequest) (*runtimev1.LaunchRuntimeResponse, error) {
	info, warmStart, err := s.Launcher.Launch(ctx, req.Contract)
	if err != nil {
		switch {
		case errors.Is(err, launcher.ErrAlreadyExists):
			return nil, status.Error(codes.AlreadyExists, err.Error())
		case errors.Is(err, launcher.ErrInvalidContract):
			return nil, status.Error(codes.InvalidArgument, err.Error())
		default:
			return nil, status.Error(codes.Internal, err.Error())
		}
	}
	return &runtimev1.LaunchRuntimeResponse{
		RuntimeId: info.RuntimeId,
		State:     info.State,
		WarmStart: warmStart,
	}, nil
}

func (s *RuntimeControlServiceServer) GetRuntime(ctx context.Context, req *runtimev1.GetRuntimeRequest) (*runtimev1.GetRuntimeResponse, error) {
	record, err := s.Store.GetRuntimeByExecutionID(ctx, req.ExecutionId)
	if err != nil {
		if state.IsNotFound(err) {
			return nil, status.Error(codes.NotFound, err.Error())
		}
		return nil, status.Error(codes.Internal, err.Error())
	}
	return &runtimev1.GetRuntimeResponse{Runtime: runtimeInfo(record)}, nil
}

func (s *RuntimeControlServiceServer) PauseRuntime(ctx context.Context, req *runtimev1.PauseRuntimeRequest) (*runtimev1.PauseRuntimeResponse, error) {
	record, err := s.Store.GetRuntimeByExecutionID(ctx, req.ExecutionId)
	if err != nil {
		if state.IsNotFound(err) {
			return nil, status.Error(codes.NotFound, err.Error())
		}
		return nil, status.Error(codes.Internal, err.Error())
	}
	if record.State != "running" {
		return nil, status.Error(codes.FailedPrecondition, "runtime is not running")
	}
	if _, err := s.Pods.ExecInPod(ctx, record.PodName, []string{"sh", "-c", "kill -TSTP 1"}); err == nil {
		if err := s.Store.UpdateRuntimeState(ctx, req.ExecutionId, "paused", ""); err != nil {
			return nil, status.Error(codes.Internal, err.Error())
		}
		s.broadcast(record, "runtime.paused", runtimev1.RuntimeEventType_RUNTIME_EVENT_PAUSED, runtimev1.RuntimeState_RUNTIME_STATE_PAUSED, "")
		return &runtimev1.PauseRuntimeResponse{State: runtimev1.RuntimeState_RUNTIME_STATE_PAUSED}, nil
	}
	return &runtimev1.PauseRuntimeResponse{State: runtimev1.RuntimeState_RUNTIME_STATE_RUNNING}, nil
}

func (s *RuntimeControlServiceServer) ResumeRuntime(ctx context.Context, req *runtimev1.ResumeRuntimeRequest) (*runtimev1.ResumeRuntimeResponse, error) {
	record, err := s.Store.GetRuntimeByExecutionID(ctx, req.ExecutionId)
	if err != nil {
		if state.IsNotFound(err) {
			return nil, status.Error(codes.NotFound, err.Error())
		}
		return nil, status.Error(codes.Internal, err.Error())
	}
	if record.State != "paused" {
		return nil, status.Error(codes.FailedPrecondition, "runtime is not paused")
	}
	if _, err := s.Pods.ExecInPod(ctx, record.PodName, []string{"sh", "-c", "kill -CONT 1"}); err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}
	if err := s.Store.UpdateRuntimeState(ctx, req.ExecutionId, "running", ""); err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}
	s.broadcast(record, "runtime.resumed", runtimev1.RuntimeEventType_RUNTIME_EVENT_RESUMED, runtimev1.RuntimeState_RUNTIME_STATE_RUNNING, "")
	return &runtimev1.ResumeRuntimeResponse{State: runtimev1.RuntimeState_RUNTIME_STATE_RUNNING}, nil
}

func (s *RuntimeControlServiceServer) StopRuntime(ctx context.Context, req *runtimev1.StopRuntimeRequest) (*runtimev1.StopRuntimeResponse, error) {
	record, err := s.Store.GetRuntimeByExecutionID(ctx, req.ExecutionId)
	if err != nil {
		if state.IsNotFound(err) {
			return nil, status.Error(codes.NotFound, err.Error())
		}
		return nil, status.Error(codes.Internal, err.Error())
	}
	grace := int64(req.GracePeriodSeconds)
	if grace <= 0 {
		grace = 30
	}
	if s.Collector != nil {
		_, _, _ = s.Collector.Collect(ctx, req.ExecutionId)
	}
	_, _ = s.Pods.ExecInPod(ctx, record.PodName, []string{"sh", "-c", "kill -TERM 1"})
	if err := s.Pods.DeletePod(ctx, record.PodName, grace); err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}
	if err := s.Store.UpdateRuntimeState(ctx, req.ExecutionId, "stopped", ""); err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}
	s.broadcast(record, "runtime.stopped", runtimev1.RuntimeEventType_RUNTIME_EVENT_STOPPED, runtimev1.RuntimeState_RUNTIME_STATE_STOPPED, "")
	return &runtimev1.StopRuntimeResponse{State: runtimev1.RuntimeState_RUNTIME_STATE_STOPPED}, nil
}

func (s *RuntimeControlServiceServer) StreamRuntimeEvents(req *runtimev1.StreamRuntimeEventsRequest, stream runtimev1.RuntimeControlService_StreamRuntimeEventsServer) error {
	if _, err := s.Store.GetRuntimeByExecutionID(stream.Context(), req.ExecutionId); err != nil {
		if state.IsNotFound(err) {
			return status.Error(codes.NotFound, err.Error())
		}
		return status.Error(codes.Internal, err.Error())
	}
	if req.Since != nil {
		eventsSince, err := s.Store.GetRuntimeEventsSince(stream.Context(), req.ExecutionId, req.Since.AsTime())
		if err != nil {
			return status.Error(codes.Internal, err.Error())
		}
		for _, stored := range eventsSince {
			if err := stream.Send(&runtimev1.RuntimeEvent{
				EventId:     stored.EventID.String(),
				RuntimeId:   stored.RuntimeID.String(),
				ExecutionId: stored.ExecutionID,
				OccurredAt:  timestamppb.New(stored.EmittedAt),
				DetailsJson: string(stored.Payload),
			}); err != nil {
				return err
			}
		}
	}
	if s.Fanout == nil {
		return nil
	}
	ch, unsubscribe := s.Fanout.Subscribe(req.ExecutionId)
	defer unsubscribe()
	for {
		select {
		case <-stream.Context().Done():
			return stream.Context().Err()
		case event, ok := <-ch:
			if !ok {
				return nil
			}
			if err := stream.Send(event); err != nil {
				return err
			}
			if event.NewState == runtimev1.RuntimeState_RUNTIME_STATE_STOPPED || event.NewState == runtimev1.RuntimeState_RUNTIME_STATE_FORCE_STOPPED || event.NewState == runtimev1.RuntimeState_RUNTIME_STATE_FAILED {
				return nil
			}
		}
	}
}

func (s *RuntimeControlServiceServer) CollectRuntimeArtifacts(ctx context.Context, req *runtimev1.CollectRuntimeArtifactsRequest) (*runtimev1.CollectRuntimeArtifactsResponse, error) {
	if s.Collector == nil {
		return &runtimev1.CollectRuntimeArtifactsResponse{}, nil
	}
	entries, complete, err := s.Collector.Collect(ctx, req.ExecutionId)
	if err != nil {
		if state.IsNotFound(err) {
			return nil, status.Error(codes.NotFound, err.Error())
		}
		return nil, status.Error(codes.Internal, err.Error())
	}
	if record, getErr := s.Store.GetRuntimeByExecutionID(ctx, req.ExecutionId); getErr == nil {
		if manifest, buildErr := artifacts.BuildManifest(record.RuntimeID.String(), record.ExecutionID, entries, complete); buildErr == nil && s.Fanout != nil {
			s.Fanout.Publish(manifest)
		}
	}
	return &runtimev1.CollectRuntimeArtifactsResponse{Artifacts: entries, Complete: complete}, nil
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

func runtimeInfo(record state.RuntimeRecord) *runtimev1.RuntimeInfo {
	return &runtimev1.RuntimeInfo{
		RuntimeId:       record.RuntimeID.String(),
		ExecutionId:     record.ExecutionID,
		State:           mapState(record.State),
		FailureReason:   record.FailureReason,
		PodName:         record.PodName,
		LaunchedAt:      timestamp(record.LaunchedAt),
		LastHeartbeatAt: timestamp(record.LastHeartbeatAt),
		CorrelationContext: &runtimev1.CorrelationContext{
			WorkspaceId: record.WorkspaceID,
			ExecutionId: record.ExecutionID,
		},
	}
}

func mapState(stateValue string) runtimev1.RuntimeState {
	switch stateValue {
	case "running":
		return runtimev1.RuntimeState_RUNTIME_STATE_RUNNING
	case "paused":
		return runtimev1.RuntimeState_RUNTIME_STATE_PAUSED
	case "stopped":
		return runtimev1.RuntimeState_RUNTIME_STATE_STOPPED
	case "force_stopped":
		return runtimev1.RuntimeState_RUNTIME_STATE_FORCE_STOPPED
	case "failed":
		return runtimev1.RuntimeState_RUNTIME_STATE_FAILED
	default:
		return runtimev1.RuntimeState_RUNTIME_STATE_PENDING
	}
}

func timestamp(value *time.Time) *timestamppb.Timestamp {
	if value == nil {
		return nil
	}
	return timestamppb.New(*value)
}

func (s *RuntimeControlServiceServer) broadcast(record state.RuntimeRecord, name string, eventType runtimev1.RuntimeEventType, newState runtimev1.RuntimeState, details string) {
	envelope := events.BuildEnvelope(name, record.RuntimeID.String(), record.ExecutionID, &runtimev1.CorrelationContext{
		WorkspaceId: record.WorkspaceID,
		ExecutionId: record.ExecutionID,
	}, map[string]string{"state": record.State})
	event := events.RuntimeEventFromEnvelope(envelope, eventType, newState, details)
	_ = s.Store.InsertRuntimeEvent(context.Background(), state.RuntimeEventRecord{
		RuntimeID:   record.RuntimeID,
		ExecutionID: record.ExecutionID,
		EventType:   name,
		Payload:     []byte(details),
	})
	if s.Fanout != nil {
		s.Fanout.Publish(event)
	}
}
