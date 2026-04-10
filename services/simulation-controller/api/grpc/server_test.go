package grpcserver

import (
	"context"
	"io"
	"log/slog"
	"testing"
	"time"

	simulationv1 "github.com/musematic/simulation-controller/api/grpc/v1"
	"github.com/musematic/simulation-controller/internal/ate_runner"
	"github.com/musematic/simulation-controller/internal/event_streamer"
	"github.com/musematic/simulation-controller/internal/sim_manager"
	"github.com/musematic/simulation-controller/pkg/persistence"
	"github.com/stretchr/testify/require"
	corev1 "k8s.io/api/core/v1"
)

type fakeStore struct {
	updates        []persistence.SimulationStatusUpdate
	findSessionID  string
	findSessionErr error
}

func (f *fakeStore) InsertSimulation(context.Context, persistence.SimulationRecord) error { return nil }

func (f *fakeStore) UpdateSimulationStatus(_ context.Context, _ string, update persistence.SimulationStatusUpdate) error {
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
}

func (f *fakeManager) CreatePod(context.Context, sim_manager.SimulationPodSpec) (*corev1.Pod, error) {
	return nil, nil
}

func (f *fakeManager) DeletePod(_ context.Context, podName string) error {
	f.deleted = append(f.deleted, podName)
	return nil
}

func (f *fakeManager) GetPodPhase(context.Context, string) (string, error) { return "", nil }
func (f *fakeManager) EnsureNetworkPolicy(context.Context) error           { return nil }

type fakeATERunner struct {
	cleanups []string
}

func (f *fakeATERunner) Start(context.Context, ate_runner.ATERequest) (*simulationv1.ATEHandle, error) {
	return nil, nil
}

func (f *fakeATERunner) Cleanup(_ context.Context, sessionID string) error {
	f.cleanups = append(f.cleanups, sessionID)
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
