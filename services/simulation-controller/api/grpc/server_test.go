package grpcserver

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"math"
	"testing"
	"time"

	simulationv1 "github.com/musematic/simulation-controller/api/grpc/v1"
	"github.com/musematic/simulation-controller/internal/ate_runner"
	"github.com/musematic/simulation-controller/internal/event_streamer"
	"github.com/musematic/simulation-controller/internal/sim_manager"
	"github.com/musematic/simulation-controller/pkg/persistence"
	"github.com/stretchr/testify/require"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

type fakeStore struct {
	inserted       []persistence.SimulationRecord
	insertErr      error
	updateErr      error
	updates        []persistence.SimulationStatusUpdate
	findSessionID  string
	findSessionErr error
}

func (f *fakeStore) InsertSimulation(_ context.Context, record persistence.SimulationRecord) error {
	if f.insertErr != nil {
		return f.insertErr
	}
	f.inserted = append(f.inserted, record)
	return nil
}

func (f *fakeStore) UpdateSimulationStatus(_ context.Context, _ string, update persistence.SimulationStatusUpdate) error {
	if f.updateErr != nil {
		return f.updateErr
	}
	f.updates = append(f.updates, update)
	return nil
}

func (f *fakeStore) FindATESessionIDBySimulation(context.Context, string) (string, error) {
	if f.findSessionErr != nil {
		return "", f.findSessionErr
	}
	return f.findSessionID, nil
}

type fakeManager struct {
	deleted []string
	pod     *corev1.Pod
	err     error
}

func (f *fakeManager) CreatePod(context.Context, sim_manager.SimulationPodSpec) (*corev1.Pod, error) {
	if f.err != nil {
		return nil, f.err
	}
	if f.pod != nil {
		return f.pod, nil
	}
	return &corev1.Pod{}, nil
}

func (f *fakeManager) DeletePod(_ context.Context, podName string) error {
	f.deleted = append(f.deleted, podName)
	return nil
}

func (f *fakeManager) GetPodPhase(context.Context, string) (string, error) { return "", nil }
func (f *fakeManager) EnsureNetworkPolicy(context.Context) error           { return nil }

type fakeProducer struct {
	topics []string
	keys   []string
	err    error
}

func (f *fakeProducer) Produce(topic, key string, _ []byte) error {
	f.topics = append(f.topics, topic)
	f.keys = append(f.keys, key)
	return f.err
}

func (f *fakeProducer) Close() {}

type fakeCollector struct {
	refs    []*simulationv1.ArtifactRef
	partial bool
	err     error
	paths   []string
}

func (f *fakeCollector) Collect(_ context.Context, _ string, _ string, paths []string) ([]*simulationv1.ArtifactRef, bool, error) {
	f.paths = append([]string(nil), paths...)
	return f.refs, f.partial, f.err
}

type fakeEventStreamer struct {
	events []*simulationv1.SimulationEvent
	err    error
}

func (f *fakeEventStreamer) Stream(_ context.Context, _ string, send func(*simulationv1.SimulationEvent) error) error {
	for _, event := range f.events {
		if err := send(event); err != nil {
			return err
		}
	}
	return f.err
}

type fakeATERunner struct {
	handle   *simulationv1.ATEHandle
	startErr error
	cleanups []string
}

func (f *fakeATERunner) Start(context.Context, ate_runner.ATERequest) (*simulationv1.ATEHandle, error) {
	if f.startErr != nil {
		return nil, f.startErr
	}
	return f.handle, nil
}

func (f *fakeATERunner) Cleanup(_ context.Context, sessionID string) error {
	f.cleanups = append(f.cleanups, sessionID)
	return nil
}

type fakeSimulationStream struct {
	ctx    context.Context
	events []*simulationv1.SimulationEvent
}

func (f *fakeSimulationStream) SetHeader(metadata.MD) error  { return nil }
func (f *fakeSimulationStream) SendHeader(metadata.MD) error { return nil }
func (f *fakeSimulationStream) SetTrailer(metadata.MD)       {}
func (f *fakeSimulationStream) Context() context.Context {
	if f.ctx != nil {
		return f.ctx
	}
	return context.Background()
}
func (f *fakeSimulationStream) SendMsg(any) error { return nil }
func (f *fakeSimulationStream) RecvMsg(any) error { return nil }
func (f *fakeSimulationStream) Send(event *simulationv1.SimulationEvent) error {
	f.events = append(f.events, event)
	return nil
}

func TestGetSimulationStatusUsesRegistryFastPath(t *testing.T) {
	t.Parallel()

	startedAt := time.Now().Add(-2 * time.Minute).UTC()
	createdAt := startedAt.Add(-30 * time.Second)
	registry := sim_manager.NewStateRegistry()
	registry.Register(sim_manager.SimulationState{
		SimulationID: "sim-1",
		Status:       "RUNNING",
		PodName:      "pod-1",
		PodPhase:     "Running",
		CreatedAt:    &createdAt,
		StartedAt:    &startedAt,
		ResourceUsage: sim_manager.ResourceUsage{
			CPURequest:    "250m",
			MemoryRequest: "256Mi",
		},
	})

	handler := NewHandler(HandlerDependencies{
		StateRegistry: registry,
		Store:         &fakeStore{},
		Logger:        slog.New(slog.NewTextHandler(io.Discard, nil)),
	})

	response, err := handler.GetSimulationStatus(context.Background(), &simulationv1.GetSimulationStatusRequest{SimulationId: "sim-1"})
	require.NoError(t, err)
	require.Equal(t, "RUNNING", response.GetStatus())
	require.Equal(t, "pod-1", response.GetPodName())
	require.Greater(t, response.GetElapsedSeconds(), int64(0))
}

func TestTerminateSimulationPublishesEventAndLeavesOtherStatesUntouched(t *testing.T) {
	t.Parallel()

	registry := sim_manager.NewStateRegistry()
	registry.Register(sim_manager.SimulationState{SimulationID: "sim-a", Status: "RUNNING", PodName: "pod-a"})
	registry.Register(sim_manager.SimulationState{SimulationID: "sim-b", Status: "RUNNING", PodName: "pod-b"})

	fanout := event_streamer.NewFanoutRegistry(4)
	ch := fanout.Subscribe("sim-a")
	manager := &fakeManager{}
	store := &fakeStore{findSessionErr: persistence.ErrNotFound}
	handler := NewHandler(HandlerDependencies{
		SimManager:    manager,
		StateRegistry: registry,
		Store:         store,
		Fanout:        fanout,
		Logger:        slog.New(slog.NewTextHandler(io.Discard, nil)),
	})

	response, err := handler.TerminateSimulation(context.Background(), &simulationv1.TerminateSimulationRequest{
		SimulationId: "sim-a",
		Reason:       "test",
	})
	require.NoError(t, err)
	require.True(t, response.GetSuccess())
	require.Equal(t, []string{"pod-a"}, manager.deleted)
	require.Len(t, store.updates, 1)
	require.Equal(t, "TERMINATED", store.updates[0].Status)

	event := <-ch
	require.Equal(t, "TERMINATED", event.GetEventType())
	_, ok := <-ch
	require.False(t, ok)

	stateA, _ := registry.Get("sim-a")
	stateB, _ := registry.Get("sim-b")
	require.Equal(t, "TERMINATED", stateA.Status)
	require.Equal(t, "RUNNING", stateB.Status)
}

func TestCreateSimulationRegistersStateAndPublishesEvent(t *testing.T) {
	t.Parallel()

	registry := sim_manager.NewStateRegistry()
	store := &fakeStore{}
	producer := &fakeProducer{}
	handler := NewHandler(HandlerDependencies{
		SimManager: &fakeManager{pod: &corev1.Pod{
			ObjectMeta: metav1.ObjectMeta{Name: "pod-1"},
			Status:     corev1.PodStatus{Phase: corev1.PodPending},
		}},
		StateRegistry: registry,
		Store:         store,
		Producer:      producer,
		Logger:        slog.New(slog.NewTextHandler(io.Discard, nil)),
	})

	response, err := handler.CreateSimulation(context.Background(), &simulationv1.CreateSimulationRequest{
		SimulationId: "sim-1",
		Config: &simulationv1.SimulationConfig{
			AgentImage:         "busybox:latest",
			CpuRequest:         "250m",
			MemoryRequest:      "256Mi",
			MaxDurationSeconds: 60,
		},
	})
	require.NoError(t, err)
	require.Equal(t, "pod-1", response.GetPodName())
	require.Len(t, store.inserted, 1)
	require.Len(t, store.updates, 1)
	require.Equal(t, []string{"simulation.events"}, producer.topics)
	require.Equal(t, []string{"sim-1"}, producer.keys)

	state, ok := registry.Get("sim-1")
	require.True(t, ok)
	require.Equal(t, "CREATING", state.Status)
	require.Equal(t, "pod-1", state.PodName)
}

func TestCreateSimulationMapsValidationAndAlreadyExists(t *testing.T) {
	t.Parallel()

	handler := NewHandler(HandlerDependencies{})
	_, err := handler.CreateSimulation(context.Background(), &simulationv1.CreateSimulationRequest{})
	require.Equal(t, codes.InvalidArgument, status.Code(err))

	handler = NewHandler(HandlerDependencies{
		SimManager: &fakeManager{},
		Store:      &fakeStore{insertErr: persistence.ErrAlreadyExists},
	})
	_, err = handler.CreateSimulation(context.Background(), &simulationv1.CreateSimulationRequest{
		SimulationId: "sim-1",
		Config:       &simulationv1.SimulationConfig{AgentImage: "busybox:latest"},
	})
	require.Equal(t, codes.AlreadyExists, status.Code(err))
}

func TestStreamSimulationEventsDelegatesToStreamer(t *testing.T) {
	t.Parallel()

	registry := sim_manager.NewStateRegistry()
	registry.Register(sim_manager.SimulationState{SimulationID: "sim-1"})
	streamer := &fakeEventStreamer{events: []*simulationv1.SimulationEvent{{
		SimulationId: "sim-1",
		EventType:    "POD_RUNNING",
		OccurredAt:   timestamppb.Now(),
	}}}
	handler := NewHandler(HandlerDependencies{
		StateRegistry: registry,
		EventStreamer: streamer,
	})
	stream := &fakeSimulationStream{}

	require.NoError(t, handler.StreamSimulationEvents(&simulationv1.StreamSimulationEventsRequest{SimulationId: "sim-1"}, stream))
	require.Len(t, stream.events, 1)
	require.Equal(t, "POD_RUNNING", stream.events[0].GetEventType())
}

func TestStreamSimulationEventsValidationBranches(t *testing.T) {
	t.Parallel()

	handler := NewHandler(HandlerDependencies{})
	stream := &fakeSimulationStream{}

	err := handler.StreamSimulationEvents(&simulationv1.StreamSimulationEventsRequest{}, stream)
	require.Equal(t, codes.InvalidArgument, status.Code(err))

	handler = NewHandler(HandlerDependencies{StateRegistry: sim_manager.NewStateRegistry()})
	err = handler.StreamSimulationEvents(&simulationv1.StreamSimulationEventsRequest{SimulationId: "sim-1"}, stream)
	require.Equal(t, codes.Unimplemented, status.Code(err))

	err = NewHandler(HandlerDependencies{
		StateRegistry: sim_manager.NewStateRegistry(),
		EventStreamer: &fakeEventStreamer{},
	}).StreamSimulationEvents(&simulationv1.StreamSimulationEventsRequest{SimulationId: "sim-1"}, stream)
	require.Equal(t, codes.NotFound, status.Code(err))
}

func TestCollectSimulationArtifactsUsesDefaultPaths(t *testing.T) {
	t.Parallel()

	registry := sim_manager.NewStateRegistry()
	registry.Register(sim_manager.SimulationState{SimulationID: "sim-1", PodName: "pod-1"})
	collector := &fakeCollector{refs: []*simulationv1.ArtifactRef{{
		ObjectKey:   "sim-1/output.tar.gz",
		Filename:    "output.tar.gz",
		SizeBytes:   128,
		ContentType: "application/gzip",
	}}}
	producer := &fakeProducer{}
	handler := NewHandler(HandlerDependencies{
		StateRegistry:        registry,
		ArtifactCollector:    collector,
		Producer:             producer,
		DefaultArtifactPaths: []string{"/output"},
		Logger:               slog.New(slog.NewTextHandler(io.Discard, nil)),
	})

	response, err := handler.CollectSimulationArtifacts(context.Background(), &simulationv1.CollectSimulationArtifactsRequest{SimulationId: "sim-1"})
	require.NoError(t, err)
	require.EqualValues(t, 1, response.GetArtifactsCollected())
	require.Equal(t, []string{"/output"}, collector.paths)
	require.Equal(t, []string{"simulation.events"}, producer.topics)
}

func TestCollectSimulationArtifactsValidationBranches(t *testing.T) {
	t.Parallel()

	handler := NewHandler(HandlerDependencies{})
	_, err := handler.CollectSimulationArtifacts(context.Background(), &simulationv1.CollectSimulationArtifactsRequest{})
	require.Equal(t, codes.InvalidArgument, status.Code(err))

	registry := sim_manager.NewStateRegistry()
	_, err = NewHandler(HandlerDependencies{StateRegistry: registry}).CollectSimulationArtifacts(context.Background(), &simulationv1.CollectSimulationArtifactsRequest{
		SimulationId: "sim-1",
	})
	require.Equal(t, codes.Unimplemented, status.Code(err))

	_, err = NewHandler(HandlerDependencies{
		StateRegistry:     registry,
		ArtifactCollector: &fakeCollector{},
	}).CollectSimulationArtifacts(context.Background(), &simulationv1.CollectSimulationArtifactsRequest{SimulationId: "sim-1"})
	require.Equal(t, codes.NotFound, status.Code(err))

	registry.Register(sim_manager.SimulationState{SimulationID: "sim-1", PodName: "pod-1"})
	_, err = NewHandler(HandlerDependencies{
		StateRegistry:     registry,
		ArtifactCollector: &fakeCollector{err: errors.New("collect failed")},
	}).CollectSimulationArtifacts(context.Background(), &simulationv1.CollectSimulationArtifactsRequest{SimulationId: "sim-1"})
	require.Equal(t, codes.Internal, status.Code(err))
}

func TestCreateAccreditedTestEnvDelegatesToRunner(t *testing.T) {
	t.Parallel()

	runner := &fakeATERunner{handle: &simulationv1.ATEHandle{
		SessionId:     "session-1",
		SimulationId:  "sim-1",
		Status:        "PROVISIONING",
		ScenarioCount: 1,
	}}
	handler := NewHandler(HandlerDependencies{ATERunner: runner})

	handle, err := handler.CreateAccreditedTestEnv(context.Background(), &simulationv1.CreateATERequest{
		SessionId: "session-1",
		AgentId:   "agent-1",
		Config:    &simulationv1.SimulationConfig{AgentImage: "busybox:latest"},
		Scenarios: []*simulationv1.ATEScenario{{ScenarioId: "scenario-1"}},
	})
	require.NoError(t, err)
	require.Equal(t, "session-1", handle.GetSessionId())

	runner.startErr = persistence.ErrAlreadyExists
	_, err = handler.CreateAccreditedTestEnv(context.Background(), &simulationv1.CreateATERequest{
		SessionId: "session-1",
		AgentId:   "agent-1",
		Config:    &simulationv1.SimulationConfig{AgentImage: "busybox:latest"},
		Scenarios: []*simulationv1.ATEScenario{{ScenarioId: "scenario-1"}},
	})
	require.Equal(t, codes.AlreadyExists, status.Code(err))

	runner.startErr = errors.New("boom")
	_, err = handler.CreateAccreditedTestEnv(context.Background(), &simulationv1.CreateATERequest{
		SessionId: "session-1",
		AgentId:   "agent-1",
		Config:    &simulationv1.SimulationConfig{AgentImage: "busybox:latest"},
		Scenarios: []*simulationv1.ATEScenario{{ScenarioId: "scenario-1"}},
	})
	require.Equal(t, codes.Internal, status.Code(err))
}

func TestCreateAccreditedTestEnvValidationBranches(t *testing.T) {
	t.Parallel()

	handler := NewHandler(HandlerDependencies{})
	_, err := handler.CreateAccreditedTestEnv(context.Background(), &simulationv1.CreateATERequest{})
	require.Equal(t, codes.InvalidArgument, status.Code(err))

	_, err = NewHandler(HandlerDependencies{}).CreateAccreditedTestEnv(context.Background(), &simulationv1.CreateATERequest{
		SessionId: "session-1",
		AgentId:   "agent-1",
		Config:    &simulationv1.SimulationConfig{AgentImage: "busybox:latest"},
		Scenarios: []*simulationv1.ATEScenario{{ScenarioId: "scenario-1"}},
	})
	require.Equal(t, codes.Unimplemented, status.Code(err))
}

func TestHandlerHelpersCoverEdgeCases(t *testing.T) {
	t.Parallel()

	require.EqualValues(t, math.MinInt32, safeInt32(-1<<62))
	require.EqualValues(t, math.MaxInt32, safeInt32(1<<62))
	require.Nil(t, timestamp(nil))

	handler := NewHandler(HandlerDependencies{
		Producer: &fakeProducer{err: errors.New("produce failed")},
		Logger:   slog.New(slog.NewTextHandler(io.Discard, nil)),
	})
	handler.publishEvent(context.Background(), nil)
	handler.publishEvent(context.Background(), &simulationv1.SimulationEvent{SimulationId: "sim-1", EventType: "POD_CREATED", Simulation: true})
}
