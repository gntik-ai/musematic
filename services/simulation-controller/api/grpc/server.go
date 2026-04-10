package grpcserver

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"time"

	simulationv1 "github.com/musematic/simulation-controller/api/grpc/v1"
	"github.com/musematic/simulation-controller/internal/artifact_collector"
	"github.com/musematic/simulation-controller/internal/ate_runner"
	"github.com/musematic/simulation-controller/internal/event_streamer"
	"github.com/musematic/simulation-controller/internal/sim_manager"
	"github.com/musematic/simulation-controller/pkg/metrics"
	"github.com/musematic/simulation-controller/pkg/persistence"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/types/known/timestamppb"
)

type HandlerDependencies struct {
	SimManager           sim_manager.Manager
	StateRegistry        *sim_manager.StateRegistry
	Store                store
	ArtifactCollector    artifact_collector.ArtifactCollector
	ATERunner            ate_runner.ATERunner
	EventStreamer        event_streamer.EventStreamer
	Fanout               *event_streamer.FanoutRegistry
	Producer             persistence.Producer
	Metrics              *metrics.Metrics
	Logger               *slog.Logger
	DefaultArtifactPaths []string
}

type Handler struct {
	simulationv1.UnimplementedSimulationControlServiceServer
	simManager           sim_manager.Manager
	stateRegistry        *sim_manager.StateRegistry
	store                store
	artifactCollector    artifact_collector.ArtifactCollector
	ateRunner            ate_runner.ATERunner
	eventStreamer        event_streamer.EventStreamer
	fanout               *event_streamer.FanoutRegistry
	producer             persistence.Producer
	metrics              *metrics.Metrics
	logger               *slog.Logger
	defaultArtifactPaths []string
}

type store interface {
	InsertSimulation(ctx context.Context, record persistence.SimulationRecord) error
	UpdateSimulationStatus(ctx context.Context, simulationID string, update persistence.SimulationStatusUpdate) error
	FindATESessionIDBySimulation(ctx context.Context, simulationID string) (string, error)
}

func NewHandler(deps HandlerDependencies) *Handler {
	defaultPaths := deps.DefaultArtifactPaths
	if len(defaultPaths) == 0 {
		defaultPaths = []string{"/output", "/workspace"}
	}
	return &Handler{
		simManager:           deps.SimManager,
		stateRegistry:        deps.StateRegistry,
		store:                deps.Store,
		artifactCollector:    deps.ArtifactCollector,
		ateRunner:            deps.ATERunner,
		eventStreamer:        deps.EventStreamer,
		fanout:               deps.Fanout,
		producer:             deps.Producer,
		metrics:              deps.Metrics,
		logger:               deps.Logger,
		defaultArtifactPaths: defaultPaths,
	}
}

func (h *Handler) CreateSimulation(ctx context.Context, req *simulationv1.CreateSimulationRequest) (*simulationv1.SimulationHandle, error) {
	if req.GetSimulationId() == "" || req.GetConfig().GetAgentImage() == "" {
		return nil, status.Error(codes.InvalidArgument, "simulation_id and config.agent_image are required")
	}
	if h.simManager == nil || h.store == nil {
		return nil, status.Error(codes.Unimplemented, "simulation controller is not configured")
	}

	now := time.Now().UTC()
	configJSON, err := protojson.Marshal(req.GetConfig())
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}
	if err := h.store.InsertSimulation(ctx, persistence.SimulationRecord{
		SimulationID:       req.GetSimulationId(),
		AgentImage:         req.GetConfig().GetAgentImage(),
		AgentConfigJSON:    configJSON,
		Status:             "CREATING",
		Namespace:          sim_manager.DefaultNamespace,
		CPURequest:         req.GetConfig().GetCpuRequest(),
		MemoryRequest:      req.GetConfig().GetMemoryRequest(),
		MaxDurationSeconds: req.GetConfig().GetMaxDurationSeconds(),
		CreatedAt:          now,
	}); err != nil {
		if errors.Is(err, persistence.ErrAlreadyExists) {
			return nil, status.Error(codes.AlreadyExists, err.Error())
		}
		return nil, status.Error(codes.Internal, err.Error())
	}

	pod, err := h.simManager.CreatePod(ctx, sim_manager.SimulationPodSpec{
		SimulationID:       req.GetSimulationId(),
		AgentImage:         req.GetConfig().GetAgentImage(),
		AgentEnv:           req.GetConfig().GetAgentEnv(),
		CPURequest:         req.GetConfig().GetCpuRequest(),
		MemoryRequest:      req.GetConfig().GetMemoryRequest(),
		MaxDurationSeconds: req.GetConfig().GetMaxDurationSeconds(),
	})
	if err != nil {
		message := err.Error()
		_ = h.store.UpdateSimulationStatus(ctx, req.GetSimulationId(), persistence.SimulationStatusUpdate{
			Status:       "FAILED",
			ErrorMessage: &message,
		})
		return nil, status.Error(codes.Internal, err.Error())
	}

	if h.stateRegistry != nil {
		h.stateRegistry.Register(sim_manager.SimulationState{
			SimulationID: req.GetSimulationId(),
			Status:       "CREATING",
			PodName:      pod.Name,
			PodPhase:     string(pod.Status.Phase),
			CreatedAt:    &now,
			ResourceUsage: sim_manager.ResourceUsage{
				CPURequest:    req.GetConfig().GetCpuRequest(),
				MemoryRequest: req.GetConfig().GetMemoryRequest(),
				CPULimit:      req.GetConfig().GetCpuRequest(),
				MemoryLimit:   req.GetConfig().GetMemoryRequest(),
			},
		})
	}

	_ = h.store.UpdateSimulationStatus(ctx, req.GetSimulationId(), persistence.SimulationStatusUpdate{
		Status:  "CREATING",
		PodName: pod.Name,
	})
	if h.metrics != nil {
		h.metrics.RecordSimulationCreated(ctx)
		h.metrics.RecordSimulationStatus(ctx, "CREATING", 1)
	}
	h.publishEvent(ctx, &simulationv1.SimulationEvent{
		SimulationId: req.GetSimulationId(),
		EventType:    "POD_CREATED",
		Detail:       "simulation pod created",
		Simulation:   true,
		OccurredAt:   timestamppb.New(now),
		Metadata:     map[string]string{"pod_name": pod.Name},
	})

	return &simulationv1.SimulationHandle{
		SimulationId: req.GetSimulationId(),
		PodName:      pod.Name,
		Status:       "CREATING",
		CreatedAt:    timestamppb.New(now),
	}, nil
}

func (h *Handler) GetSimulationStatus(ctx context.Context, req *simulationv1.GetSimulationStatusRequest) (*simulationv1.SimulationStatus, error) {
	if req.GetSimulationId() == "" {
		return nil, status.Error(codes.InvalidArgument, "simulation_id is required")
	}
	if h.stateRegistry == nil {
		return nil, status.Error(codes.Unimplemented, "state registry is not configured")
	}

	state, ok := h.stateRegistry.Get(req.GetSimulationId())
	if !ok {
		return nil, status.Error(codes.NotFound, "simulation not found")
	}

	elapsed := int64(0)
	if state.StartedAt != nil {
		end := time.Now().UTC()
		if state.CompletedAt != nil {
			end = state.CompletedAt.UTC()
		}
		elapsed = int64(end.Sub(*state.StartedAt).Seconds())
	}

	return &simulationv1.SimulationStatus{
		SimulationId:   state.SimulationID,
		Status:         state.Status,
		PodName:        state.PodName,
		PodPhase:       state.PodPhase,
		ElapsedSeconds: elapsed,
		ResourceUsage: &simulationv1.ResourceUsage{
			CpuRequest:    state.ResourceUsage.CPURequest,
			MemoryRequest: state.ResourceUsage.MemoryRequest,
			CpuLimit:      state.ResourceUsage.CPULimit,
			MemoryLimit:   state.ResourceUsage.MemoryLimit,
		},
		ErrorMessage: state.ErrorMessage,
		CreatedAt:    timestamp(state.CreatedAt),
		StartedAt:    timestamp(state.StartedAt),
		CompletedAt:  timestamp(state.CompletedAt),
	}, nil
}

func (h *Handler) StreamSimulationEvents(req *simulationv1.StreamSimulationEventsRequest, stream simulationv1.SimulationControlService_StreamSimulationEventsServer) error {
	if req.GetSimulationId() == "" {
		return status.Error(codes.InvalidArgument, "simulation_id is required")
	}
	if h.stateRegistry == nil || h.eventStreamer == nil {
		return status.Error(codes.Unimplemented, "event streaming is not configured")
	}
	if _, ok := h.stateRegistry.Get(req.GetSimulationId()); !ok {
		return status.Error(codes.NotFound, "simulation not found")
	}
	return h.eventStreamer.Stream(stream.Context(), req.GetSimulationId(), func(event *simulationv1.SimulationEvent) error {
		return stream.Send(event)
	})
}

func (h *Handler) TerminateSimulation(ctx context.Context, req *simulationv1.TerminateSimulationRequest) (*simulationv1.TerminateResult, error) {
	if req.GetSimulationId() == "" {
		return nil, status.Error(codes.InvalidArgument, "simulation_id is required")
	}
	if h.simManager == nil || h.store == nil || h.stateRegistry == nil {
		return nil, status.Error(codes.Unimplemented, "simulation controller is not configured")
	}

	state, ok := h.stateRegistry.Get(req.GetSimulationId())
	if !ok {
		return nil, status.Error(codes.NotFound, "simulation not found")
	}
	if state.Status == "TERMINATED" || state.Status == "COMPLETED" {
		return nil, status.Error(codes.FailedPrecondition, "simulation already in terminal state")
	}
	if err := h.simManager.DeletePod(ctx, state.PodName); err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	now := time.Now().UTC()
	if err := h.store.UpdateSimulationStatus(ctx, req.GetSimulationId(), persistence.SimulationStatusUpdate{
		Status:       "TERMINATED",
		TerminatedAt: &now,
	}); err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	state.Status = "TERMINATED"
	state.CompletedAt = &now
	h.stateRegistry.Register(state)
	if sessionID, err := h.store.FindATESessionIDBySimulation(ctx, req.GetSimulationId()); err == nil && h.ateRunner != nil {
		_ = h.ateRunner.Cleanup(ctx, sessionID)
	}
	if h.metrics != nil {
		h.metrics.RecordSimulationTermination(ctx, req.GetReason())
		h.metrics.RecordSimulationStatus(ctx, "TERMINATED", 1)
	}
	h.publishEvent(ctx, &simulationv1.SimulationEvent{
		SimulationId: req.GetSimulationId(),
		EventType:    "TERMINATED",
		Detail:       "simulation terminated",
		Simulation:   true,
		OccurredAt:   timestamppb.New(now),
		Metadata:     map[string]string{"reason": req.GetReason()},
	})
	if h.fanout != nil {
		h.fanout.Close(req.GetSimulationId())
	}

	return &simulationv1.TerminateResult{
		SimulationId: req.GetSimulationId(),
		Success:      true,
		Message:      "simulation terminated",
	}, nil
}

func (h *Handler) CollectSimulationArtifacts(ctx context.Context, req *simulationv1.CollectSimulationArtifactsRequest) (*simulationv1.ArtifactCollectionResult, error) {
	if req.GetSimulationId() == "" {
		return nil, status.Error(codes.InvalidArgument, "simulation_id is required")
	}
	if h.stateRegistry == nil || h.artifactCollector == nil {
		return nil, status.Error(codes.Unimplemented, "artifact collection is not configured")
	}
	state, ok := h.stateRegistry.Get(req.GetSimulationId())
	if !ok {
		return nil, status.Error(codes.NotFound, "simulation not found")
	}

	paths := req.GetPaths()
	if len(paths) == 0 {
		paths = append([]string(nil), h.defaultArtifactPaths...)
	}
	artifacts, partial, err := h.artifactCollector.Collect(ctx, req.GetSimulationId(), state.PodName, paths)
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}

	var totalBytes int64
	for _, artifact := range artifacts {
		totalBytes += artifact.GetSizeBytes()
	}
	if h.metrics != nil {
		h.metrics.RecordArtifactsCollected(ctx, int64(len(artifacts)))
		h.metrics.RecordArtifactsBytes(ctx, totalBytes)
	}
	h.publishEvent(ctx, &simulationv1.SimulationEvent{
		SimulationId: req.GetSimulationId(),
		EventType:    "ARTIFACT_COLLECTED",
		Detail:       fmt.Sprintf("collected %d artifacts", len(artifacts)),
		Simulation:   true,
		OccurredAt:   timestamppb.Now(),
		Metadata: map[string]string{
			"artifacts_collected": fmt.Sprintf("%d", len(artifacts)),
			"partial":             fmt.Sprintf("%t", partial),
		},
	})

	return &simulationv1.ArtifactCollectionResult{
		SimulationId:       req.GetSimulationId(),
		ArtifactsCollected: int32(len(artifacts)),
		TotalBytes:         totalBytes,
		Artifacts:          artifacts,
		Partial:            partial,
	}, nil
}

func (h *Handler) CreateAccreditedTestEnv(ctx context.Context, req *simulationv1.CreateATERequest) (*simulationv1.ATEHandle, error) {
	if req.GetSessionId() == "" || req.GetAgentId() == "" || req.GetConfig().GetAgentImage() == "" || len(req.GetScenarios()) == 0 {
		return nil, status.Error(codes.InvalidArgument, "session_id, agent_id, config.agent_image, and at least one scenario are required")
	}
	if h.ateRunner == nil {
		return nil, status.Error(codes.Unimplemented, "ate runner is not configured")
	}

	handle, err := h.ateRunner.Start(ctx, ate_runner.ATERequest{
		SessionID:   req.GetSessionId(),
		AgentID:     req.GetAgentId(),
		Config:      req.GetConfig(),
		Scenarios:   req.GetScenarios(),
		DatasetRefs: req.GetDatasetRefs(),
	})
	if err != nil {
		switch {
		case errors.Is(err, persistence.ErrAlreadyExists):
			return nil, status.Error(codes.AlreadyExists, err.Error())
		default:
			return nil, status.Error(codes.Internal, err.Error())
		}
	}
	if h.metrics != nil {
		h.metrics.RecordATESession(ctx)
	}
	return handle, nil
}

func (h *Handler) publishEvent(ctx context.Context, event *simulationv1.SimulationEvent) {
	if event == nil {
		return
	}
	if h.fanout != nil {
		h.fanout.Publish(event.GetSimulationId(), event)
	}
	if h.producer == nil {
		return
	}
	payload, err := event_streamer.MarshalEventEnvelope(event)
	if err != nil {
		if h.logger != nil {
			h.logger.Error("marshal event envelope failed", "error", err)
		}
		return
	}
	if err := h.producer.Produce("simulation.events", event.GetSimulationId(), payload); err != nil && h.logger != nil {
		h.logger.Error("publish simulation event failed", "error", err)
	}
}

func timestamp(value *time.Time) *timestamppb.Timestamp {
	if value == nil {
		return nil
	}
	return timestamppb.New(value.UTC())
}
