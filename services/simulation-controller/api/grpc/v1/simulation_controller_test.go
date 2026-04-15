package simulationv1

import (
	"context"
	"errors"
	"net"
	"testing"

	"github.com/stretchr/testify/require"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/metadata"
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

type fakeClientConn struct {
	invokeErr    error
	newStreamErr error
	stream       *fakeClientStream
}

func (f *fakeClientConn) Invoke(context.Context, string, any, any, ...grpc.CallOption) error {
	return f.invokeErr
}

func (f *fakeClientConn) NewStream(context.Context, *grpc.StreamDesc, string, ...grpc.CallOption) (grpc.ClientStream, error) {
	if f.newStreamErr != nil {
		return nil, f.newStreamErr
	}
	if f.stream != nil {
		return f.stream, nil
	}
	return &fakeClientStream{}, nil
}

type fakeClientStream struct {
	sendErr  error
	closeErr error
}

func (f *fakeClientStream) Header() (metadata.MD, error) { return nil, nil }
func (f *fakeClientStream) Trailer() metadata.MD         { return nil }
func (f *fakeClientStream) CloseSend() error             { return f.closeErr }
func (f *fakeClientStream) Context() context.Context     { return context.Background() }
func (f *fakeClientStream) SendMsg(any) error            { return f.sendErr }
func (f *fakeClientStream) RecvMsg(any) error            { return nil }

type fakeServerStream struct {
	recvErr error
	sent    []any
}

func (f *fakeServerStream) SetHeader(metadata.MD) error  { return nil }
func (f *fakeServerStream) SendHeader(metadata.MD) error { return nil }
func (f *fakeServerStream) SetTrailer(metadata.MD)       {}
func (f *fakeServerStream) Context() context.Context     { return context.Background() }
func (f *fakeServerStream) SendMsg(message any) error {
	f.sent = append(f.sent, message)
	return nil
}
func (f *fakeServerStream) RecvMsg(message any) error {
	if f.recvErr != nil {
		return f.recvErr
	}
	if req, ok := message.(*StreamSimulationEventsRequest); ok {
		req.SimulationId = "sim-1"
	}
	return nil
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
	config.Reset()
	require.Empty(t, config.GetAgentImage())

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

func TestGeneratedMessageNilGettersAndLegacyMethods(t *testing.T) {
	t.Parallel()

	file_simulation_controller_proto_init()

	messages := []interface {
		String() string
		ProtoMessage()
		Descriptor() ([]byte, []int)
	}{
		&SimulationConfig{},
		&CreateSimulationRequest{},
		&SimulationHandle{},
		&GetSimulationStatusRequest{},
		&SimulationStatus{},
		&ResourceUsage{},
		&StreamSimulationEventsRequest{},
		&SimulationEvent{},
		&TerminateSimulationRequest{},
		&TerminateResult{},
		&CollectSimulationArtifactsRequest{},
		&ArtifactCollectionResult{},
		&ArtifactRef{},
		&ATEScenario{},
		&CreateATERequest{},
		&ATEHandle{},
	}
	for _, message := range messages {
		_ = message.String()
		message.ProtoMessage()
		raw, indexes := message.Descriptor()
		require.NotEmpty(t, raw)
		require.NotNil(t, indexes)
	}

	var config *SimulationConfig
	require.Empty(t, config.GetAgentImage())
	require.Empty(t, config.GetAgentEnv())
	require.Empty(t, config.GetCpuRequest())
	require.Empty(t, config.GetMemoryRequest())
	require.Zero(t, config.GetMaxDurationSeconds())

	var createReq *CreateSimulationRequest
	require.Empty(t, createReq.GetSimulationId())
	require.Nil(t, createReq.GetConfig())

	var handle *SimulationHandle
	require.Empty(t, handle.GetSimulationId())
	require.Empty(t, handle.GetPodName())
	require.Empty(t, handle.GetStatus())
	require.Nil(t, handle.GetCreatedAt())

	var statusReq *GetSimulationStatusRequest
	require.Empty(t, statusReq.GetSimulationId())

	var statusMsg *SimulationStatus
	require.Empty(t, statusMsg.GetSimulationId())
	require.Empty(t, statusMsg.GetStatus())
	require.Empty(t, statusMsg.GetPodName())
	require.Empty(t, statusMsg.GetPodPhase())
	require.Zero(t, statusMsg.GetElapsedSeconds())
	require.Nil(t, statusMsg.GetResourceUsage())
	require.Empty(t, statusMsg.GetErrorMessage())
	require.Nil(t, statusMsg.GetCreatedAt())
	require.Nil(t, statusMsg.GetStartedAt())
	require.Nil(t, statusMsg.GetCompletedAt())

	var usage *ResourceUsage
	require.Empty(t, usage.GetCpuRequest())
	require.Empty(t, usage.GetMemoryRequest())
	require.Empty(t, usage.GetCpuLimit())
	require.Empty(t, usage.GetMemoryLimit())

	var streamReq *StreamSimulationEventsRequest
	require.Empty(t, streamReq.GetSimulationId())

	var event *SimulationEvent
	require.Empty(t, event.GetSimulationId())
	require.Empty(t, event.GetEventType())
	require.Empty(t, event.GetDetail())
	require.False(t, event.GetSimulation())
	require.Nil(t, event.GetOccurredAt())
	require.Empty(t, event.GetMetadata())

	var terminateReq *TerminateSimulationRequest
	require.Empty(t, terminateReq.GetSimulationId())
	require.Empty(t, terminateReq.GetReason())

	var terminateResult *TerminateResult
	require.Empty(t, terminateResult.GetSimulationId())
	require.False(t, terminateResult.GetSuccess())
	require.Empty(t, terminateResult.GetMessage())

	var artifactsReq *CollectSimulationArtifactsRequest
	require.Empty(t, artifactsReq.GetSimulationId())
	require.Empty(t, artifactsReq.GetPaths())

	var artifactsResult *ArtifactCollectionResult
	require.Empty(t, artifactsResult.GetSimulationId())
	require.Zero(t, artifactsResult.GetArtifactsCollected())
	require.Zero(t, artifactsResult.GetTotalBytes())
	require.Empty(t, artifactsResult.GetArtifacts())
	require.False(t, artifactsResult.GetPartial())

	var artifactRef *ArtifactRef
	require.Empty(t, artifactRef.GetObjectKey())
	require.Empty(t, artifactRef.GetFilename())
	require.Zero(t, artifactRef.GetSizeBytes())
	require.Empty(t, artifactRef.GetContentType())

	var scenario *ATEScenario
	require.Empty(t, scenario.GetScenarioId())
	require.Empty(t, scenario.GetName())
	require.Empty(t, scenario.GetInputData())
	require.Empty(t, scenario.GetScorerConfig())
	require.Zero(t, scenario.GetQualityThreshold())
	require.False(t, scenario.GetSafetyRequired())

	var ateReq *CreateATERequest
	require.Empty(t, ateReq.GetSessionId())
	require.Empty(t, ateReq.GetAgentId())
	require.Nil(t, ateReq.GetConfig())
	require.Empty(t, ateReq.GetScenarios())
	require.Empty(t, ateReq.GetDatasetRefs())

	var ateHandle *ATEHandle
	require.Empty(t, ateHandle.GetSessionId())
	require.Empty(t, ateHandle.GetSimulationId())
	require.Empty(t, ateHandle.GetStatus())
	require.Zero(t, ateHandle.GetScenarioCount())
	require.Nil(t, ateHandle.GetCreatedAt())
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

func TestGeneratedGRPCClientErrorBranches(t *testing.T) {
	t.Parallel()

	invokeErr := errors.New("invoke failed")
	client := NewSimulationControlServiceClient(&fakeClientConn{invokeErr: invokeErr})
	_, err := client.CreateSimulation(context.Background(), &CreateSimulationRequest{})
	require.ErrorIs(t, err, invokeErr)
	_, err = client.GetSimulationStatus(context.Background(), &GetSimulationStatusRequest{})
	require.ErrorIs(t, err, invokeErr)
	_, err = client.TerminateSimulation(context.Background(), &TerminateSimulationRequest{})
	require.ErrorIs(t, err, invokeErr)
	_, err = client.CollectSimulationArtifacts(context.Background(), &CollectSimulationArtifactsRequest{})
	require.ErrorIs(t, err, invokeErr)
	_, err = client.CreateAccreditedTestEnv(context.Background(), &CreateATERequest{})
	require.ErrorIs(t, err, invokeErr)

	streamErr := errors.New("stream failed")
	client = NewSimulationControlServiceClient(&fakeClientConn{newStreamErr: streamErr})
	_, err = client.StreamSimulationEvents(context.Background(), &StreamSimulationEventsRequest{})
	require.ErrorIs(t, err, streamErr)

	sendErr := errors.New("send failed")
	client = NewSimulationControlServiceClient(&fakeClientConn{stream: &fakeClientStream{sendErr: sendErr}})
	_, err = client.StreamSimulationEvents(context.Background(), &StreamSimulationEventsRequest{})
	require.ErrorIs(t, err, sendErr)

	closeErr := errors.New("close failed")
	client = NewSimulationControlServiceClient(&fakeClientConn{stream: &fakeClientStream{closeErr: closeErr}})
	_, err = client.StreamSimulationEvents(context.Background(), &StreamSimulationEventsRequest{})
	require.ErrorIs(t, err, closeErr)
}

func TestGeneratedGRPCHandlers(t *testing.T) {
	t.Parallel()

	server := &testSimulationControlService{}
	decodeErr := errors.New("decode failed")
	badDecoder := func(any) error { return decodeErr }
	goodDecoder := func(any) error { return nil }
	interceptor := func(ctx context.Context, req any, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (any, error) {
		require.NotEmpty(t, info.FullMethod)
		return handler(ctx, req)
	}

	unaryHandlers := []func(interface{}, context.Context, func(interface{}) error, grpc.UnaryServerInterceptor) (interface{}, error){
		_SimulationControlService_CreateSimulation_Handler,
		_SimulationControlService_GetSimulationStatus_Handler,
		_SimulationControlService_TerminateSimulation_Handler,
		_SimulationControlService_CollectSimulationArtifacts_Handler,
		_SimulationControlService_CreateAccreditedTestEnv_Handler,
	}
	for _, handler := range unaryHandlers {
		_, err := handler(server, context.Background(), badDecoder, nil)
		require.ErrorIs(t, err, decodeErr)
		response, err := handler(server, context.Background(), goodDecoder, nil)
		require.NoError(t, err)
		require.NotNil(t, response)
		response, err = handler(server, context.Background(), goodDecoder, interceptor)
		require.NoError(t, err)
		require.NotNil(t, response)
	}

	stream := &fakeServerStream{}
	require.NoError(t, _SimulationControlService_StreamSimulationEvents_Handler(server, stream))
	require.Len(t, stream.sent, 1)

	err := _SimulationControlService_StreamSimulationEvents_Handler(server, &fakeServerStream{recvErr: decodeErr})
	require.ErrorIs(t, err, decodeErr)
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
