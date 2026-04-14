package simulationv1

import (
	"context"
	"net"
	"testing"

	"github.com/stretchr/testify/require"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/status"
	"google.golang.org/grpc/test/bufconn"
	"google.golang.org/protobuf/types/known/timestamppb"
)

type testSimulationControlService struct {
	UnimplementedSimulationControlServiceServer
}

func (s *testSimulationControlService) CreateSimulation(context.Context, *CreateSimulationRequest) (*SimulationHandle, error) {
	return &SimulationHandle{SimulationId: "sim-1", PodName: "pod-1", Status: "CREATING", CreatedAt: timestamppb.Now()}, nil
}

func (s *testSimulationControlService) GetSimulationStatus(context.Context, *GetSimulationStatusRequest) (*SimulationStatus, error) {
	return &SimulationStatus{
		SimulationId:   "sim-1",
		Status:         "RUNNING",
		PodName:        "pod-1",
		PodPhase:       "Running",
		ElapsedSeconds: 12,
		ResourceUsage: &ResourceUsage{
			CpuRequest:    "250m",
			MemoryRequest: "256Mi",
			CpuLimit:      "250m",
			MemoryLimit:   "256Mi",
		},
		CreatedAt: timestamppb.Now(),
		StartedAt: timestamppb.Now(),
	}, nil
}

func (s *testSimulationControlService) StreamSimulationEvents(_ *StreamSimulationEventsRequest, stream grpc.ServerStreamingServer[SimulationEvent]) error {
	return stream.Send(&SimulationEvent{
		SimulationId: "sim-1",
		EventType:    "POD_RUNNING",
		Detail:       "simulation running",
		Simulation:   true,
		OccurredAt:   timestamppb.Now(),
		Metadata:     map[string]string{"pod_name": "pod-1"},
	})
}

func (s *testSimulationControlService) TerminateSimulation(context.Context, *TerminateSimulationRequest) (*TerminateResult, error) {
	return &TerminateResult{SimulationId: "sim-1", Success: true, Message: "terminated"}, nil
}

func (s *testSimulationControlService) CollectSimulationArtifacts(context.Context, *CollectSimulationArtifactsRequest) (*ArtifactCollectionResult, error) {
	return &ArtifactCollectionResult{
		SimulationId:       "sim-1",
		ArtifactsCollected: 1,
		TotalBytes:         128,
		Artifacts: []*ArtifactRef{{
			ObjectKey:   "sim-1/output.tar.gz",
			Filename:    "output.tar.gz",
			SizeBytes:   128,
			ContentType: "application/gzip",
		}},
	}, nil
}

func (s *testSimulationControlService) CreateAccreditedTestEnv(context.Context, *CreateATERequest) (*ATEHandle, error) {
	return &ATEHandle{
		SessionId:     "session-1",
		SimulationId:  "sim-1",
		Status:        "PROVISIONING",
		ScenarioCount: 1,
		CreatedAt:     timestamppb.Now(),
	}, nil
}

func startTestSimulationServer(t *testing.T) (*grpc.ClientConn, SimulationControlServiceClient) {
	t.Helper()

	listener := bufconn.Listen(1024 * 1024)
	server := grpc.NewServer()
	RegisterSimulationControlServiceServer(server, &testSimulationControlService{})
	go func() {
		_ = server.Serve(listener)
	}()
	t.Cleanup(server.Stop)

	conn, err := grpc.NewClient("passthrough:///bufnet", grpc.WithContextDialer(func(context.Context, string) (net.Conn, error) {
		return listener.Dial()
	}), grpc.WithTransportCredentials(insecure.NewCredentials()))
	require.NoError(t, err)
	t.Cleanup(func() {
		_ = conn.Close()
	})

	return conn, NewSimulationControlServiceClient(conn)
}

func TestGeneratedMessagesExposeFieldsAndDescriptors(t *testing.T) {
	t.Parallel()

	config := &SimulationConfig{
		AgentImage:         "busybox:latest",
		AgentEnv:           map[string]string{"SIMULATION": "true"},
		CpuRequest:         "250m",
		MemoryRequest:      "256Mi",
		MaxDurationSeconds: 120,
	}
	require.Contains(t, config.String(), "busybox")
	require.NotNil(t, config.ProtoReflect())
	_, descriptorIndexes := config.Descriptor()
	require.NotEmpty(t, descriptorIndexes)
	require.Equal(t, "busybox:latest", config.GetAgentImage())
	require.Equal(t, "true", config.GetAgentEnv()["SIMULATION"])
	require.Equal(t, "250m", config.GetCpuRequest())
	require.Equal(t, "256Mi", config.GetMemoryRequest())
	require.EqualValues(t, 120, config.GetMaxDurationSeconds())

	request := &CreateSimulationRequest{SimulationId: "sim-1", Config: config}
	require.Equal(t, "sim-1", request.GetSimulationId())
	require.Equal(t, config, request.GetConfig())
	require.NotEmpty(t, request.String())
	request.Reset()
	require.Equal(t, "", request.GetSimulationId())

	handle := &SimulationHandle{SimulationId: "sim-1", PodName: "pod-1", Status: "CREATING", CreatedAt: timestamppb.Now()}
	require.Equal(t, "sim-1", handle.GetSimulationId())
	require.Equal(t, "pod-1", handle.GetPodName())
	require.Equal(t, "CREATING", handle.GetStatus())
	require.NotNil(t, handle.GetCreatedAt())
	require.NotEmpty(t, handle.String())
	handle.Reset()

	statusRequest := &GetSimulationStatusRequest{SimulationId: "sim-1"}
	require.Equal(t, "sim-1", statusRequest.GetSimulationId())
	statusRequest.Reset()

	resourceUsage := &ResourceUsage{CpuRequest: "250m", MemoryRequest: "256Mi", CpuLimit: "250m", MemoryLimit: "256Mi"}
	require.Equal(t, "250m", resourceUsage.GetCpuRequest())
	require.Equal(t, "256Mi", resourceUsage.GetMemoryRequest())
	require.Equal(t, "250m", resourceUsage.GetCpuLimit())
	require.Equal(t, "256Mi", resourceUsage.GetMemoryLimit())
	resourceUsage.Reset()

	simulationStatus := &SimulationStatus{
		SimulationId:   "sim-1",
		Status:         "RUNNING",
		PodName:        "pod-1",
		PodPhase:       "Running",
		ElapsedSeconds: 5,
		ResourceUsage:  resourceUsage,
		ErrorMessage:   "none",
		CreatedAt:      timestamppb.Now(),
		StartedAt:      timestamppb.Now(),
		CompletedAt:    timestamppb.Now(),
	}
	require.Equal(t, "sim-1", simulationStatus.GetSimulationId())
	require.Equal(t, "RUNNING", simulationStatus.GetStatus())
	require.Equal(t, "pod-1", simulationStatus.GetPodName())
	require.Equal(t, "Running", simulationStatus.GetPodPhase())
	require.EqualValues(t, 5, simulationStatus.GetElapsedSeconds())
	require.NotNil(t, simulationStatus.GetResourceUsage())
	require.Equal(t, "none", simulationStatus.GetErrorMessage())
	require.NotNil(t, simulationStatus.GetCreatedAt())
	require.NotNil(t, simulationStatus.GetStartedAt())
	require.NotNil(t, simulationStatus.GetCompletedAt())
	simulationStatus.Reset()

	streamRequest := &StreamSimulationEventsRequest{SimulationId: "sim-1"}
	require.Equal(t, "sim-1", streamRequest.GetSimulationId())
	streamRequest.Reset()

	event := &SimulationEvent{
		SimulationId: "sim-1",
		EventType:    "POD_RUNNING",
		Detail:       "simulation running",
		Simulation:   true,
		OccurredAt:   timestamppb.Now(),
		Metadata:     map[string]string{"pod_name": "pod-1"},
	}
	require.Equal(t, "sim-1", event.GetSimulationId())
	require.Equal(t, "POD_RUNNING", event.GetEventType())
	require.Equal(t, "simulation running", event.GetDetail())
	require.True(t, event.GetSimulation())
	require.NotNil(t, event.GetOccurredAt())
	require.Equal(t, "pod-1", event.GetMetadata()["pod_name"])
	event.Reset()

	terminateRequest := &TerminateSimulationRequest{SimulationId: "sim-1", Reason: "test"}
	require.Equal(t, "sim-1", terminateRequest.GetSimulationId())
	require.Equal(t, "test", terminateRequest.GetReason())
	terminateRequest.Reset()

	terminateResult := &TerminateResult{SimulationId: "sim-1", Success: true, Message: "terminated"}
	require.Equal(t, "sim-1", terminateResult.GetSimulationId())
	require.True(t, terminateResult.GetSuccess())
	require.Equal(t, "terminated", terminateResult.GetMessage())
	terminateResult.Reset()

	artifactRequest := &CollectSimulationArtifactsRequest{SimulationId: "sim-1", Paths: []string{"/output"}}
	require.Equal(t, "sim-1", artifactRequest.GetSimulationId())
	require.Equal(t, []string{"/output"}, artifactRequest.GetPaths())
	artifactRequest.Reset()

	artifactRef := &ArtifactRef{ObjectKey: "sim-1/output.tar.gz", Filename: "output.tar.gz", SizeBytes: 128, ContentType: "application/gzip"}
	require.Equal(t, "sim-1/output.tar.gz", artifactRef.GetObjectKey())
	require.Equal(t, "output.tar.gz", artifactRef.GetFilename())
	require.EqualValues(t, 128, artifactRef.GetSizeBytes())
	require.Equal(t, "application/gzip", artifactRef.GetContentType())
	artifactRef.Reset()

	artifactResult := &ArtifactCollectionResult{SimulationId: "sim-1", ArtifactsCollected: 1, TotalBytes: 128, Artifacts: []*ArtifactRef{artifactRef}, Partial: true}
	require.Equal(t, "sim-1", artifactResult.GetSimulationId())
	require.EqualValues(t, 1, artifactResult.GetArtifactsCollected())
	require.EqualValues(t, 128, artifactResult.GetTotalBytes())
	require.Len(t, artifactResult.GetArtifacts(), 1)
	require.True(t, artifactResult.GetPartial())
	artifactResult.Reset()

	scenario := &ATEScenario{
		ScenarioId:       "scenario-1",
		Name:             "happy path",
		InputData:        []byte(`{"prompt":"hello"}`),
		ScorerConfig:     `{"metric":"quality"}`,
		QualityThreshold: 0.9,
		SafetyRequired:   true,
	}
	require.Equal(t, "scenario-1", scenario.GetScenarioId())
	require.Equal(t, "happy path", scenario.GetName())
	require.Equal(t, []byte(`{"prompt":"hello"}`), scenario.GetInputData())
	require.Equal(t, `{"metric":"quality"}`, scenario.GetScorerConfig())
	require.EqualValues(t, 0.9, scenario.GetQualityThreshold())
	require.True(t, scenario.GetSafetyRequired())
	scenario.Reset()

	ateRequest := &CreateATERequest{
		SessionId:   "session-1",
		AgentId:     "agent-1",
		Config:      config,
		Scenarios:   []*ATEScenario{scenario},
		DatasetRefs: []string{"dataset-1"},
	}
	require.Equal(t, "session-1", ateRequest.GetSessionId())
	require.Equal(t, "agent-1", ateRequest.GetAgentId())
	require.Equal(t, config, ateRequest.GetConfig())
	require.Len(t, ateRequest.GetScenarios(), 1)
	require.Equal(t, []string{"dataset-1"}, ateRequest.GetDatasetRefs())
	ateRequest.Reset()

	ateHandle := &ATEHandle{SessionId: "session-1", SimulationId: "sim-1", Status: "PROVISIONING", ScenarioCount: 1, CreatedAt: timestamppb.Now()}
	require.Equal(t, "session-1", ateHandle.GetSessionId())
	require.Equal(t, "sim-1", ateHandle.GetSimulationId())
	require.Equal(t, "PROVISIONING", ateHandle.GetStatus())
	require.EqualValues(t, 1, ateHandle.GetScenarioCount())
	require.NotNil(t, ateHandle.GetCreatedAt())
	ateHandle.Reset()
}

func TestGeneratedGRPCClientAndServerRoundTrip(t *testing.T) {
	t.Parallel()

	conn, client := startTestSimulationServer(t)
	require.NotNil(t, conn)

	createHandle, err := client.CreateSimulation(context.Background(), &CreateSimulationRequest{SimulationId: "sim-1"})
	require.NoError(t, err)
	require.Equal(t, "sim-1", createHandle.GetSimulationId())

	statusResponse, err := client.GetSimulationStatus(context.Background(), &GetSimulationStatusRequest{SimulationId: "sim-1"})
	require.NoError(t, err)
	require.Equal(t, "RUNNING", statusResponse.GetStatus())

	stream, err := client.StreamSimulationEvents(context.Background(), &StreamSimulationEventsRequest{SimulationId: "sim-1"})
	require.NoError(t, err)
	streamEvent, err := stream.Recv()
	require.NoError(t, err)
	require.Equal(t, "POD_RUNNING", streamEvent.GetEventType())

	terminateResult, err := client.TerminateSimulation(context.Background(), &TerminateSimulationRequest{SimulationId: "sim-1"})
	require.NoError(t, err)
	require.True(t, terminateResult.GetSuccess())

	artifactResult, err := client.CollectSimulationArtifacts(context.Background(), &CollectSimulationArtifactsRequest{SimulationId: "sim-1"})
	require.NoError(t, err)
	require.EqualValues(t, 1, artifactResult.GetArtifactsCollected())

	ateHandle, err := client.CreateAccreditedTestEnv(context.Background(), &CreateATERequest{SessionId: "session-1"})
	require.NoError(t, err)
	require.Equal(t, "session-1", ateHandle.GetSessionId())
}

func TestUnimplementedServerReturnsUnimplementedErrors(t *testing.T) {
	t.Parallel()

	server := UnimplementedSimulationControlServiceServer{}
	_, err := server.CreateSimulation(context.Background(), &CreateSimulationRequest{})
	require.Equal(t, codes.Unimplemented, status.Code(err))
	_, err = server.GetSimulationStatus(context.Background(), &GetSimulationStatusRequest{})
	require.Equal(t, codes.Unimplemented, status.Code(err))
	err = server.StreamSimulationEvents(&StreamSimulationEventsRequest{}, nil)
	require.Equal(t, codes.Unimplemented, status.Code(err))
	_, err = server.TerminateSimulation(context.Background(), &TerminateSimulationRequest{})
	require.Equal(t, codes.Unimplemented, status.Code(err))
	_, err = server.CollectSimulationArtifacts(context.Background(), &CollectSimulationArtifactsRequest{})
	require.Equal(t, codes.Unimplemented, status.Code(err))
	_, err = server.CreateAccreditedTestEnv(context.Background(), &CreateATERequest{})
	require.Equal(t, codes.Unimplemented, status.Code(err))
	server.mustEmbedUnimplementedSimulationControlServiceServer()
	server.testEmbeddedByValue()
}
