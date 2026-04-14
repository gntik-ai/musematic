package sandboxv1

import (
	"context"
	"net"
	"testing"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/status"
	"google.golang.org/grpc/test/bufconn"
	"google.golang.org/protobuf/types/known/durationpb"
	"google.golang.org/protobuf/types/known/timestamppb"
)

type sandboxServiceStub struct {
	UnimplementedSandboxServiceServer
}

func (sandboxServiceStub) CreateSandbox(context.Context, *CreateSandboxRequest) (*CreateSandboxResponse, error) {
	return &CreateSandboxResponse{SandboxId: "sandbox-1", State: SandboxState_SANDBOX_STATE_READY}, nil
}

func (sandboxServiceStub) ExecuteSandboxStep(context.Context, *ExecuteSandboxStepRequest) (*ExecuteSandboxStepResponse, error) {
	return &ExecuteSandboxStepResponse{
		Result:  &ExecutionResult{Stdout: "ok", ExitCode: 0},
		StepNum: 2,
	}, nil
}

func (sandboxServiceStub) StreamSandboxLogs(_ *StreamSandboxLogsRequest, stream grpc.ServerStreamingServer[SandboxLogLine]) error {
	return stream.Send(&SandboxLogLine{Line: "log-line", Stream: "stdout", Timestamp: timestamppb.Now()})
}

func (sandboxServiceStub) TerminateSandbox(context.Context, *TerminateSandboxRequest) (*TerminateSandboxResponse, error) {
	return &TerminateSandboxResponse{State: SandboxState_SANDBOX_STATE_TERMINATED}, nil
}

func (sandboxServiceStub) CollectSandboxArtifacts(context.Context, *CollectSandboxArtifactsRequest) (*CollectSandboxArtifactsResponse, error) {
	return &CollectSandboxArtifactsResponse{
		Artifacts: []*ArtifactEntry{{Filename: "result.txt", ObjectKey: "sandbox-artifacts/result.txt"}},
		Complete:  true,
	}, nil
}

func TestGeneratedMessagesEnumsAndClient(t *testing.T) {
	t.Parallel()

	resourceLimits := &ResourceLimits{
		CpuRequest:    "250m",
		CpuLimit:      "500m",
		MemoryRequest: "256Mi",
		MemoryLimit:   "512Mi",
	}
	template := &SandboxTemplate{Name: "python3.12", Image: "python:3.12-slim", Limits: resourceLimits, TimeoutSeconds: 30}
	correlation := &CorrelationContext{WorkspaceId: "ws-1", ExecutionId: "exec-1", InteractionId: "int-1", TraceId: "trace-1"}
	sandboxInfo := &SandboxInfo{
		SandboxId:   "sandbox-1",
		ExecutionId: "exec-1",
		State:       SandboxState_SANDBOX_STATE_READY,
		Template:    "python3.12",
		PodName:     "sandbox-pod",
		CreatedAt:   timestamppb.Now(),
		TotalSteps:  1,
		Correlation: correlation,
	}
	executionResult := &ExecutionResult{
		Stdout:           "ok",
		Stderr:           "",
		ExitCode:         0,
		Duration:         durationpb.New(2 * time.Second),
		TimedOut:         false,
		OomKilled:        false,
		StructuredOutput: "{}",
		OutputTruncated:  false,
	}
	event := &SandboxEvent{
		EventId:     "event-1",
		SandboxId:   "sandbox-1",
		ExecutionId: "exec-1",
		EventType:   SandboxEventType_SANDBOX_EVENT_READY,
		OccurredAt:  timestamppb.Now(),
		DetailsJson: "{}",
		NewState:    SandboxState_SANDBOX_STATE_READY,
	}
	artifact := &ArtifactEntry{
		ObjectKey:   "sandbox-artifacts/result.txt",
		Filename:    "result.txt",
		SizeBytes:   2,
		ContentType: "text/plain",
		CollectedAt: timestamppb.Now(),
	}
	createRequest := &CreateSandboxRequest{
		TemplateName:      "python3.12",
		Correlation:       correlation,
		ResourceOverrides: resourceLimits,
		TimeoutOverride:   10,
		NetworkEnabled:    true,
		EgressAllowlist:   []string{"example.com"},
		EnvVars:           map[string]string{"ENV": "1"},
		PipPackages:       []string{"pytest"},
		NpmPackages:       []string{"tsx"},
	}
	createResponse := &CreateSandboxResponse{SandboxId: "sandbox-1", State: SandboxState_SANDBOX_STATE_CREATING}
	executeRequest := &ExecuteSandboxStepRequest{SandboxId: "sandbox-1", Code: "print('hello')", TimeoutOverride: 5}
	executeResponse := &ExecuteSandboxStepResponse{Result: executionResult, StepNum: 1}
	streamRequest := &StreamSandboxLogsRequest{SandboxId: "sandbox-1", Follow: true}
	logLine := &SandboxLogLine{Line: "hello", Stream: "stdout", Timestamp: timestamppb.Now()}
	terminateRequest := &TerminateSandboxRequest{SandboxId: "sandbox-1", GracePeriodSeconds: 5}
	terminateResponse := &TerminateSandboxResponse{State: SandboxState_SANDBOX_STATE_TERMINATED}
	collectRequest := &CollectSandboxArtifactsRequest{SandboxId: "sandbox-1"}
	collectResponse := &CollectSandboxArtifactsResponse{Artifacts: []*ArtifactEntry{artifact}, Complete: true}

	_ = resourceLimits.String()
	_, _ = resourceLimits.Descriptor()
	_ = resourceLimits.ProtoReflect().Descriptor()
	resourceLimits.ProtoMessage()
	resourceLimits.Reset()

	_ = template.String()
	_, _ = template.Descriptor()
	_ = template.ProtoReflect().Descriptor()
	template.ProtoMessage()
	template.Reset()

	_ = correlation.String()
	_, _ = correlation.Descriptor()
	_ = correlation.ProtoReflect().Descriptor()
	correlation.ProtoMessage()
	correlation.Reset()

	_ = sandboxInfo.String()
	_, _ = sandboxInfo.Descriptor()
	_ = sandboxInfo.ProtoReflect().Descriptor()
	sandboxInfo.ProtoMessage()
	sandboxInfo.Reset()

	_ = executionResult.String()
	_, _ = executionResult.Descriptor()
	_ = executionResult.ProtoReflect().Descriptor()
	executionResult.ProtoMessage()
	executionResult.Reset()

	_ = event.String()
	_, _ = event.Descriptor()
	_ = event.ProtoReflect().Descriptor()
	event.ProtoMessage()
	event.Reset()

	_ = artifact.String()
	_, _ = artifact.Descriptor()
	_ = artifact.ProtoReflect().Descriptor()
	artifact.ProtoMessage()
	artifact.Reset()

	_ = createRequest.String()
	_, _ = createRequest.Descriptor()
	_ = createRequest.ProtoReflect().Descriptor()
	createRequest.ProtoMessage()
	createRequest.Reset()

	_ = createResponse.String()
	_, _ = createResponse.Descriptor()
	_ = createResponse.ProtoReflect().Descriptor()
	createResponse.ProtoMessage()
	createResponse.Reset()

	_ = executeRequest.String()
	_, _ = executeRequest.Descriptor()
	_ = executeRequest.ProtoReflect().Descriptor()
	executeRequest.ProtoMessage()
	executeRequest.Reset()

	_ = executeResponse.String()
	_, _ = executeResponse.Descriptor()
	_ = executeResponse.ProtoReflect().Descriptor()
	executeResponse.ProtoMessage()
	executeResponse.Reset()

	_ = streamRequest.String()
	_, _ = streamRequest.Descriptor()
	_ = streamRequest.ProtoReflect().Descriptor()
	streamRequest.ProtoMessage()
	streamRequest.Reset()

	_ = logLine.String()
	_, _ = logLine.Descriptor()
	_ = logLine.ProtoReflect().Descriptor()
	logLine.ProtoMessage()
	logLine.Reset()

	_ = terminateRequest.String()
	_, _ = terminateRequest.Descriptor()
	_ = terminateRequest.ProtoReflect().Descriptor()
	terminateRequest.ProtoMessage()
	terminateRequest.Reset()

	_ = terminateResponse.String()
	_, _ = terminateResponse.Descriptor()
	_ = terminateResponse.ProtoReflect().Descriptor()
	terminateResponse.ProtoMessage()
	terminateResponse.Reset()

	_ = collectRequest.String()
	_, _ = collectRequest.Descriptor()
	_ = collectRequest.ProtoReflect().Descriptor()
	collectRequest.ProtoMessage()
	collectRequest.Reset()

	_ = collectResponse.String()
	_, _ = collectResponse.Descriptor()
	_ = collectResponse.ProtoReflect().Descriptor()
	collectResponse.ProtoMessage()
	collectResponse.Reset()

	_ = resourceLimits.GetCpuRequest()
	_ = resourceLimits.GetCpuLimit()
	_ = resourceLimits.GetMemoryRequest()
	_ = resourceLimits.GetMemoryLimit()
	_ = template.GetName()
	_ = template.GetImage()
	_ = template.GetLimits()
	_ = template.GetTimeoutSeconds()
	_ = correlation.GetWorkspaceId()
	_ = correlation.GetExecutionId()
	_ = correlation.GetInteractionId()
	_ = correlation.GetTraceId()
	_ = sandboxInfo.GetSandboxId()
	_ = sandboxInfo.GetExecutionId()
	_ = sandboxInfo.GetState()
	_ = sandboxInfo.GetFailureReason()
	_ = sandboxInfo.GetTemplate()
	_ = sandboxInfo.GetPodName()
	_ = sandboxInfo.GetCreatedAt()
	_ = sandboxInfo.GetTotalSteps()
	_ = sandboxInfo.GetCorrelation()
	_ = executionResult.GetStdout()
	_ = executionResult.GetStderr()
	_ = executionResult.GetExitCode()
	_ = executionResult.GetDuration()
	_ = executionResult.GetTimedOut()
	_ = executionResult.GetOomKilled()
	_ = executionResult.GetStructuredOutput()
	_ = executionResult.GetOutputTruncated()
	_ = event.GetEventId()
	_ = event.GetSandboxId()
	_ = event.GetExecutionId()
	_ = event.GetEventType()
	_ = event.GetOccurredAt()
	_ = event.GetDetailsJson()
	_ = event.GetNewState()
	_ = artifact.GetObjectKey()
	_ = artifact.GetFilename()
	_ = artifact.GetSizeBytes()
	_ = artifact.GetContentType()
	_ = artifact.GetCollectedAt()
	_ = createRequest.GetTemplateName()
	_ = createRequest.GetCorrelation()
	_ = createRequest.GetResourceOverrides()
	_ = createRequest.GetTimeoutOverride()
	_ = createRequest.GetNetworkEnabled()
	_ = createRequest.GetEgressAllowlist()
	_ = createRequest.GetEnvVars()
	_ = createRequest.GetPipPackages()
	_ = createRequest.GetNpmPackages()
	_ = createResponse.GetSandboxId()
	_ = createResponse.GetState()
	_ = executeRequest.GetSandboxId()
	_ = executeRequest.GetCode()
	_ = executeRequest.GetTimeoutOverride()
	_ = executeResponse.GetResult()
	_ = executeResponse.GetStepNum()
	_ = streamRequest.GetSandboxId()
	_ = streamRequest.GetFollow()
	_ = logLine.GetLine()
	_ = logLine.GetStream()
	_ = logLine.GetTimestamp()
	_ = terminateRequest.GetSandboxId()
	_ = terminateRequest.GetGracePeriodSeconds()
	_ = terminateResponse.GetState()
	_ = collectRequest.GetSandboxId()
	_ = collectResponse.GetArtifacts()
	_ = collectResponse.GetComplete()

	_ = SandboxState_SANDBOX_STATE_READY.Enum()
	_ = SandboxState_SANDBOX_STATE_READY.String()
	_ = SandboxState_SANDBOX_STATE_READY.Descriptor()
	_ = SandboxState_SANDBOX_STATE_READY.Type()
	_ = SandboxState_SANDBOX_STATE_READY.Number()
	_, _ = SandboxState_SANDBOX_STATE_READY.EnumDescriptor()

	_ = SandboxEventType_SANDBOX_EVENT_READY.Enum()
	_ = SandboxEventType_SANDBOX_EVENT_READY.String()
	_ = SandboxEventType_SANDBOX_EVENT_READY.Descriptor()
	_ = SandboxEventType_SANDBOX_EVENT_READY.Type()
	_ = SandboxEventType_SANDBOX_EVENT_READY.Number()
	_, _ = SandboxEventType_SANDBOX_EVENT_READY.EnumDescriptor()

	listener := bufconn.Listen(1024 * 1024)
	server := grpc.NewServer()
	RegisterSandboxServiceServer(server, sandboxServiceStub{})
	go func() {
		_ = server.Serve(listener)
	}()
	defer server.Stop()

	conn, err := grpc.DialContext(context.Background(), "bufnet",
		grpc.WithContextDialer(func(context.Context, string) (net.Conn, error) {
			return listener.Dial()
		}),
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		t.Fatalf("grpc.DialContext() error = %v", err)
	}
	defer conn.Close()

	client := NewSandboxServiceClient(conn)
	if _, err := client.CreateSandbox(context.Background(), &CreateSandboxRequest{}); err != nil {
		t.Fatalf("CreateSandbox() error = %v", err)
	}
	if _, err := client.ExecuteSandboxStep(context.Background(), &ExecuteSandboxStepRequest{}); err != nil {
		t.Fatalf("ExecuteSandboxStep() error = %v", err)
	}
	stream, err := client.StreamSandboxLogs(context.Background(), &StreamSandboxLogsRequest{SandboxId: "sandbox-1"})
	if err != nil {
		t.Fatalf("StreamSandboxLogs() error = %v", err)
	}
	line, err := stream.Recv()
	if err != nil {
		t.Fatalf("stream.Recv() error = %v", err)
	}
	if line.GetLine() != "log-line" {
		t.Fatalf("unexpected log line %q", line.GetLine())
	}
	if _, err := client.TerminateSandbox(context.Background(), &TerminateSandboxRequest{}); err != nil {
		t.Fatalf("TerminateSandbox() error = %v", err)
	}
	if _, err := client.CollectSandboxArtifacts(context.Background(), &CollectSandboxArtifactsRequest{}); err != nil {
		t.Fatalf("CollectSandboxArtifacts() error = %v", err)
	}

	if SandboxService_ServiceDesc.ServiceName != "sandbox_manager.v1.SandboxService" {
		t.Fatalf("unexpected service name %q", SandboxService_ServiceDesc.ServiceName)
	}
}

func TestUnimplementedSandboxServiceServer(t *testing.T) {
	t.Parallel()

	server := UnimplementedSandboxServiceServer{}
	if _, err := server.CreateSandbox(context.Background(), &CreateSandboxRequest{}); status.Code(err) != codes.Unimplemented {
		t.Fatalf("CreateSandbox() error = %v", err)
	}
	if _, err := server.ExecuteSandboxStep(context.Background(), &ExecuteSandboxStepRequest{}); status.Code(err) != codes.Unimplemented {
		t.Fatalf("ExecuteSandboxStep() error = %v", err)
	}
	if err := server.StreamSandboxLogs(&StreamSandboxLogsRequest{}, nil); status.Code(err) != codes.Unimplemented {
		t.Fatalf("StreamSandboxLogs() error = %v", err)
	}
	if _, err := server.TerminateSandbox(context.Background(), &TerminateSandboxRequest{}); status.Code(err) != codes.Unimplemented {
		t.Fatalf("TerminateSandbox() error = %v", err)
	}
	if _, err := server.CollectSandboxArtifacts(context.Background(), &CollectSandboxArtifactsRequest{}); status.Code(err) != codes.Unimplemented {
		t.Fatalf("CollectSandboxArtifacts() error = %v", err)
	}
	server.mustEmbedUnimplementedSandboxServiceServer()
	server.testEmbeddedByValue()
}

func TestGeneratedNilReceivers(t *testing.T) {
	t.Parallel()

	var resourceLimits *ResourceLimits
	var template *SandboxTemplate
	var correlation *CorrelationContext
	var sandboxInfo *SandboxInfo
	var executionResult *ExecutionResult
	var event *SandboxEvent
	var artifact *ArtifactEntry
	var createRequest *CreateSandboxRequest
	var createResponse *CreateSandboxResponse
	var executeRequest *ExecuteSandboxStepRequest
	var executeResponse *ExecuteSandboxStepResponse
	var streamRequest *StreamSandboxLogsRequest
	var logLine *SandboxLogLine
	var terminateRequest *TerminateSandboxRequest
	var terminateResponse *TerminateSandboxResponse
	var collectRequest *CollectSandboxArtifactsRequest
	var collectResponse *CollectSandboxArtifactsResponse

	resourceLimits.ProtoMessage()
	_ = resourceLimits.ProtoReflect()
	_ = resourceLimits.GetCpuRequest()
	_ = resourceLimits.GetCpuLimit()
	_ = resourceLimits.GetMemoryRequest()
	_ = resourceLimits.GetMemoryLimit()

	template.ProtoMessage()
	_ = template.ProtoReflect()
	_ = template.GetName()
	_ = template.GetImage()
	_ = template.GetLimits()
	_ = template.GetTimeoutSeconds()

	correlation.ProtoMessage()
	_ = correlation.ProtoReflect()
	_ = correlation.GetWorkspaceId()
	_ = correlation.GetExecutionId()
	_ = correlation.GetInteractionId()
	_ = correlation.GetTraceId()

	sandboxInfo.ProtoMessage()
	_ = sandboxInfo.ProtoReflect()
	_ = sandboxInfo.GetSandboxId()
	_ = sandboxInfo.GetExecutionId()
	_ = sandboxInfo.GetState()
	_ = sandboxInfo.GetFailureReason()
	_ = sandboxInfo.GetTemplate()
	_ = sandboxInfo.GetPodName()
	_ = sandboxInfo.GetCreatedAt()
	_ = sandboxInfo.GetTotalSteps()
	_ = sandboxInfo.GetCorrelation()

	executionResult.ProtoMessage()
	_ = executionResult.ProtoReflect()
	_ = executionResult.GetStdout()
	_ = executionResult.GetStderr()
	_ = executionResult.GetExitCode()
	_ = executionResult.GetDuration()
	_ = executionResult.GetTimedOut()
	_ = executionResult.GetOomKilled()
	_ = executionResult.GetStructuredOutput()
	_ = executionResult.GetOutputTruncated()

	event.ProtoMessage()
	_ = event.ProtoReflect()
	_ = event.GetEventId()
	_ = event.GetSandboxId()
	_ = event.GetExecutionId()
	_ = event.GetEventType()
	_ = event.GetOccurredAt()
	_ = event.GetDetailsJson()
	_ = event.GetNewState()

	artifact.ProtoMessage()
	_ = artifact.ProtoReflect()
	_ = artifact.GetObjectKey()
	_ = artifact.GetFilename()
	_ = artifact.GetSizeBytes()
	_ = artifact.GetContentType()
	_ = artifact.GetCollectedAt()

	createRequest.ProtoMessage()
	_ = createRequest.ProtoReflect()
	_ = createRequest.GetTemplateName()
	_ = createRequest.GetCorrelation()
	_ = createRequest.GetResourceOverrides()
	_ = createRequest.GetTimeoutOverride()
	_ = createRequest.GetNetworkEnabled()
	_ = createRequest.GetEgressAllowlist()
	_ = createRequest.GetEnvVars()
	_ = createRequest.GetPipPackages()
	_ = createRequest.GetNpmPackages()

	createResponse.ProtoMessage()
	_ = createResponse.ProtoReflect()
	_ = createResponse.GetSandboxId()
	_ = createResponse.GetState()

	executeRequest.ProtoMessage()
	_ = executeRequest.ProtoReflect()
	_ = executeRequest.GetSandboxId()
	_ = executeRequest.GetCode()
	_ = executeRequest.GetTimeoutOverride()

	executeResponse.ProtoMessage()
	_ = executeResponse.ProtoReflect()
	_ = executeResponse.GetResult()
	_ = executeResponse.GetStepNum()

	streamRequest.ProtoMessage()
	_ = streamRequest.ProtoReflect()
	_ = streamRequest.GetSandboxId()
	_ = streamRequest.GetFollow()

	logLine.ProtoMessage()
	_ = logLine.ProtoReflect()
	_ = logLine.GetLine()
	_ = logLine.GetStream()
	_ = logLine.GetTimestamp()

	terminateRequest.ProtoMessage()
	_ = terminateRequest.ProtoReflect()
	_ = terminateRequest.GetSandboxId()
	_ = terminateRequest.GetGracePeriodSeconds()

	terminateResponse.ProtoMessage()
	_ = terminateResponse.ProtoReflect()
	_ = terminateResponse.GetState()

	collectRequest.ProtoMessage()
	_ = collectRequest.ProtoReflect()
	_ = collectRequest.GetSandboxId()

	collectResponse.ProtoMessage()
	_ = collectResponse.ProtoReflect()
	_ = collectResponse.GetArtifacts()
	_ = collectResponse.GetComplete()
}
