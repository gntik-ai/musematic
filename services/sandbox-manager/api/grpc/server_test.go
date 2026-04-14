package grpcserver

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"context"
	"errors"
	"io"
	"log/slog"
	"testing"
	"time"

	sandboxv1 "github.com/andrea-mucci/musematic/services/sandbox-manager/api/grpc/v1"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/artifacts"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/events"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/executor"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/logs"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/sandbox"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/state"
	"google.golang.org/grpc"
	grpcodes "google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
	v1 "k8s.io/api/core/v1"
	"k8s.io/client-go/rest"
)

type serverPodController struct {
	pod          *v1.Pod
	deleted      []string
	createErr    error
	getErr       error
	deleteErr    error
	keepOnDelete bool
}

func (c *serverPodController) CreatePod(_ context.Context, pod *v1.Pod) (*v1.Pod, error) {
	if c.createErr != nil {
		return nil, c.createErr
	}
	copy := pod.DeepCopy()
	copy.Status.Phase = v1.PodRunning
	c.pod = copy
	return copy, nil
}

func (c *serverPodController) GetPod(_ context.Context, _ string) (*v1.Pod, error) {
	if c.getErr != nil {
		return nil, c.getErr
	}
	if len(c.deleted) > 0 {
		return nil, context.Canceled
	}
	return c.pod.DeepCopy(), nil
}

func (c *serverPodController) ListPodsByLabel(context.Context, string) ([]v1.Pod, error) {
	if c.pod == nil {
		return nil, nil
	}
	return []v1.Pod{*c.pod.DeepCopy()}, nil
}

func (c *serverPodController) DeletePod(_ context.Context, podName string, _ int64) error {
	if c.deleteErr != nil {
		return c.deleteErr
	}
	c.deleted = append(c.deleted, podName)
	if !c.keepOnDelete {
		c.pod = nil
	}
	return nil
}

type serverStore struct{}

func (serverStore) InsertSandbox(context.Context, state.SandboxRecord) error { return nil }
func (serverStore) UpdateSandboxState(context.Context, string, string, string, int32, *int64) error {
	return nil
}
func (serverStore) InsertSandboxEvent(context.Context, state.SandboxEventRecord) error { return nil }

type serverEmitter struct{}

func (serverEmitter) Emit(context.Context, *sandboxv1.SandboxEvent, events.Envelope) error {
	return nil
}

type archiveStreamerStub struct {
	reader io.ReadCloser
}

func (s archiveStreamerStub) StreamArchive(context.Context, string, string) (io.ReadCloser, error) {
	return s.reader, nil
}

type sandboxLogStream struct {
	ctx     context.Context
	lines   []*sandboxv1.SandboxLogLine
	sendErr error
}

func (s *sandboxLogStream) Context() context.Context { return s.ctx }
func (s *sandboxLogStream) Send(line *sandboxv1.SandboxLogLine) error {
	if s.sendErr != nil {
		return s.sendErr
	}
	s.lines = append(s.lines, line)
	return nil
}
func (s *sandboxLogStream) SetHeader(metadata.MD) error  { return nil }
func (s *sandboxLogStream) SendHeader(metadata.MD) error { return nil }
func (s *sandboxLogStream) SetTrailer(metadata.MD)       {}
func (s *sandboxLogStream) SendMsg(any) error            { return nil }
func (s *sandboxLogStream) RecvMsg(any) error            { return nil }

func testArchive(t *testing.T, files map[string]string) io.ReadCloser {
	t.Helper()
	var raw bytes.Buffer
	gz := gzip.NewWriter(&raw)
	tw := tar.NewWriter(gz)
	for name, contents := range files {
		payload := []byte(contents)
		if err := tw.WriteHeader(&tar.Header{Name: name, Mode: 0o644, Size: int64(len(payload))}); err != nil {
			t.Fatalf("WriteHeader() error = %v", err)
		}
		if _, err := tw.Write(payload); err != nil {
			t.Fatalf("Write() error = %v", err)
		}
	}
	if err := tw.Close(); err != nil {
		t.Fatalf("Close tar writer: %v", err)
	}
	if err := gz.Close(); err != nil {
		t.Fatalf("Close gzip writer: %v", err)
	}
	return io.NopCloser(bytes.NewReader(raw.Bytes()))
}

func newReadySandbox(t *testing.T) (*sandbox.Manager, *serverPodController, *sandbox.Entry) {
	t.Helper()

	pods := &serverPodController{}
	manager := sandbox.NewManager(sandbox.ManagerConfig{
		Namespace:      "platform-execution",
		DefaultTimeout: 30 * time.Second,
		MaxTimeout:     300 * time.Second,
		MaxConcurrent:  2,
		Store:          serverStore{},
		Pods:           pods,
		Emitter:        serverEmitter{},
	})
	entry, err := manager.Create(context.Background(), &sandboxv1.CreateSandboxRequest{
		TemplateName: "python3.12",
		Correlation: &sandboxv1.CorrelationContext{
			WorkspaceId: "ws-1",
			ExecutionId: "exec-1",
		},
	})
	if err != nil {
		t.Fatalf("Create() error = %v", err)
	}
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		current, getErr := manager.Get(entry.SandboxID)
		if getErr == nil && current.State == sandboxv1.SandboxState_SANDBOX_STATE_READY {
			return manager, pods, current
		}
		time.Sleep(50 * time.Millisecond)
	}
	t.Fatal("sandbox did not reach ready state")
	return nil, nil, nil
}

func TestStreamSandboxLogsSendsBufferedAndFollowedLines(t *testing.T) {
	t.Parallel()

	manager, _, entry := newReadySandbox(t)
	fanout := logs.NewFanoutRegistry(4)
	server := &SandboxServiceServer{Manager: manager, Fanout: fanout}

	fanout.Publish(entry.SandboxID, &sandboxv1.SandboxLogLine{Line: "buffered"})
	stream := &sandboxLogStream{ctx: context.Background()}
	if err := server.StreamSandboxLogs(&sandboxv1.StreamSandboxLogsRequest{SandboxId: entry.SandboxID}, stream); err != nil {
		t.Fatalf("StreamSandboxLogs() buffered error = %v", err)
	}
	if len(stream.lines) != 1 || stream.lines[0].GetLine() != "buffered" {
		t.Fatalf("unexpected buffered lines: %+v", stream.lines)
	}

	followCtx, cancel := context.WithCancel(context.Background())
	followStream := &sandboxLogStream{ctx: followCtx}
	go func() {
		time.Sleep(20 * time.Millisecond)
		fanout.Publish(entry.SandboxID, &sandboxv1.SandboxLogLine{Line: "live"})
		cancel()
	}()
	if err := server.StreamSandboxLogs(&sandboxv1.StreamSandboxLogsRequest{SandboxId: entry.SandboxID, Follow: true}, followStream); err != context.Canceled {
		t.Fatalf("StreamSandboxLogs() follow error = %v", err)
	}
	if len(followStream.lines) != 1 || followStream.lines[0].GetLine() != "live" {
		t.Fatalf("unexpected live lines: %+v", followStream.lines)
	}
}

func TestCreateSandboxAndExecuteSandboxStep(t *testing.T) {
	t.Parallel()

	pods := &serverPodController{}
	manager := sandbox.NewManager(sandbox.ManagerConfig{
		Namespace:      "platform-execution",
		DefaultTimeout: 30 * time.Second,
		MaxTimeout:     300 * time.Second,
		MaxConcurrent:  2,
		Store:          serverStore{},
		Pods:           pods,
		Emitter:        serverEmitter{},
	})
	server := &SandboxServiceServer{Manager: manager}

	createResponse, err := server.CreateSandbox(context.Background(), &sandboxv1.CreateSandboxRequest{
		TemplateName: "python3.12",
		Correlation: &sandboxv1.CorrelationContext{
			WorkspaceId: "ws-1",
			ExecutionId: "exec-1",
		},
	})
	if err != nil {
		t.Fatalf("CreateSandbox() error = %v", err)
	}
	if createResponse.GetSandboxId() == "" || createResponse.GetState() != sandboxv1.SandboxState_SANDBOX_STATE_CREATING {
		t.Fatalf("unexpected create response %+v", createResponse)
	}

	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		current, getErr := manager.Get(createResponse.GetSandboxId())
		if getErr == nil && current.State == sandboxv1.SandboxState_SANDBOX_STATE_READY {
			break
		}
		time.Sleep(50 * time.Millisecond)
	}

	execSvc := executor.New(manager, pods, nil, 1024)
	execSvc.Exec = func(_ context.Context, _ *rest.Config, _, _ string, _ []string, _ io.Reader, stdout io.Writer, _ io.Writer) error {
		_, _ = stdout.Write([]byte("hello\n"))
		return nil
	}
	server.Executor = execSvc

	execResponse, err := server.ExecuteSandboxStep(context.Background(), &sandboxv1.ExecuteSandboxStepRequest{
		SandboxId: createResponse.GetSandboxId(),
		Code:      `print("hello")`,
	})
	if err != nil {
		t.Fatalf("ExecuteSandboxStep() error = %v", err)
	}
	if execResponse.GetResult().GetStdout() != "hello\n" || execResponse.GetStepNum() != 1 {
		t.Fatalf("unexpected execute response %+v", execResponse)
	}
}

func TestLoggingInterceptorsInvokeHandlers(t *testing.T) {
	t.Parallel()

	unaryCalled := false
	unaryInterceptor := UnaryLoggingInterceptor(slog.Default())
	if _, err := unaryInterceptor(context.Background(), "request", &grpc.UnaryServerInfo{FullMethod: "/sandbox.v1/CreateSandbox"}, func(ctx context.Context, req any) (any, error) {
		unaryCalled = true
		return "ok", nil
	}); err != nil {
		t.Fatalf("UnaryLoggingInterceptor() error = %v", err)
	}
	if !unaryCalled {
		t.Fatal("expected unary handler to be called")
	}

	streamCalled := false
	streamInterceptor := StreamLoggingInterceptor(slog.Default())
	if err := streamInterceptor(nil, &sandboxLogStream{ctx: context.Background()}, &grpc.StreamServerInfo{FullMethod: "/sandbox.v1/StreamSandboxLogs"}, func(_ any, _ grpc.ServerStream) error {
		streamCalled = true
		return nil
	}); err != nil {
		t.Fatalf("StreamLoggingInterceptor() error = %v", err)
	}
	if !streamCalled {
		t.Fatal("expected stream handler to be called")
	}
}

func TestTerminateSandboxCollectsArtifactsAndClosesFanout(t *testing.T) {
	t.Parallel()

	manager, pods, entry := newReadySandbox(t)
	fanout := logs.NewFanoutRegistry(4)
	ch, _ := fanout.Subscribe(entry.SandboxID)
	collector := artifacts.NewCollector(manager, archiveStreamerStub{reader: testArchive(t, map[string]string{"result.txt": "ok"})}, &artifacts.MemoryUploader{}, "bucket")
	server := &SandboxServiceServer{
		Manager:   manager,
		Collector: collector,
		Fanout:    fanout,
	}

	response, err := server.TerminateSandbox(context.Background(), &sandboxv1.TerminateSandboxRequest{
		SandboxId:          entry.SandboxID,
		GracePeriodSeconds: 0,
	})
	if err != nil {
		t.Fatalf("TerminateSandbox() error = %v", err)
	}
	if response.GetState() != sandboxv1.SandboxState_SANDBOX_STATE_TERMINATED {
		t.Fatalf("unexpected terminated state %s", response.GetState())
	}
	if len(pods.deleted) == 0 {
		t.Fatal("expected pod deletion")
	}
	_, ok := <-ch
	if ok {
		t.Fatal("expected fanout channel to be closed after termination")
	}
}

func TestCollectSandboxArtifactsReturnsManifest(t *testing.T) {
	t.Parallel()

	manager, _, entry := newReadySandbox(t)
	collector := artifacts.NewCollector(manager, archiveStreamerStub{reader: testArchive(t, map[string]string{"result.txt": "ok"})}, &artifacts.MemoryUploader{}, "bucket")
	server := &SandboxServiceServer{Manager: manager, Collector: collector}

	response, err := server.CollectSandboxArtifacts(context.Background(), &sandboxv1.CollectSandboxArtifactsRequest{SandboxId: entry.SandboxID})
	if err != nil {
		t.Fatalf("CollectSandboxArtifacts() error = %v", err)
	}
	if !response.GetComplete() {
		t.Fatal("expected artifact collection to complete")
	}
	if len(response.GetArtifacts()) != 1 || response.GetArtifacts()[0].GetFilename() != "result.txt" {
		t.Fatalf("unexpected artifacts: %+v", response.GetArtifacts())
	}
}

func TestCreateSandboxErrorMappings(t *testing.T) {
	t.Parallel()

	t.Run("invalid template", func(t *testing.T) {
		server := &SandboxServiceServer{Manager: sandbox.NewManager(sandbox.ManagerConfig{
			Namespace: "platform-execution",
			Pods:      &serverPodController{},
		})}
		_, err := server.CreateSandbox(context.Background(), &sandboxv1.CreateSandboxRequest{
			TemplateName: "missing",
			Correlation:  &sandboxv1.CorrelationContext{WorkspaceId: "ws-1", ExecutionId: "exec-1"},
		})
		if status.Code(err) != grpcodes.InvalidArgument {
			t.Fatalf("CreateSandbox() code = %s, want %s", status.Code(err), grpcodes.InvalidArgument)
		}
	})

	t.Run("concurrent limit", func(t *testing.T) {
		server := &SandboxServiceServer{Manager: sandbox.NewManager(sandbox.ManagerConfig{
			Namespace:     "platform-execution",
			MaxConcurrent: 0,
			Pods:          &serverPodController{},
		})}
		_, err := server.CreateSandbox(context.Background(), &sandboxv1.CreateSandboxRequest{
			TemplateName: "python3.12",
			Correlation:  &sandboxv1.CorrelationContext{WorkspaceId: "ws-1", ExecutionId: "exec-1"},
		})
		if status.Code(err) != grpcodes.ResourceExhausted {
			t.Fatalf("CreateSandbox() code = %s, want %s", status.Code(err), grpcodes.ResourceExhausted)
		}
	})

	t.Run("unavailable", func(t *testing.T) {
		server := &SandboxServiceServer{Manager: sandbox.NewManager(sandbox.ManagerConfig{
			Namespace: "platform-execution",
			Pods:      &serverPodController{},
		})}
		_, err := server.CreateSandbox(context.Background(), &sandboxv1.CreateSandboxRequest{TemplateName: "python3.12"})
		if status.Code(err) != grpcodes.Unavailable {
			t.Fatalf("CreateSandbox() code = %s, want %s", status.Code(err), grpcodes.Unavailable)
		}
	})
}

func TestExecuteSandboxStepErrorMappings(t *testing.T) {
	t.Parallel()

	t.Run("sandbox not found", func(t *testing.T) {
		manager := sandbox.NewManager(sandbox.ManagerConfig{Namespace: "platform-execution"})
		server := &SandboxServiceServer{Manager: manager, Executor: executor.New(manager, &serverPodController{}, nil, 1024)}
		_, err := server.ExecuteSandboxStep(context.Background(), &sandboxv1.ExecuteSandboxStepRequest{SandboxId: "missing", Code: "print(1)"})
		if status.Code(err) != grpcodes.NotFound {
			t.Fatalf("ExecuteSandboxStep() code = %s, want %s", status.Code(err), grpcodes.NotFound)
		}
	})

	t.Run("invalid state", func(t *testing.T) {
		pods := &serverPodController{}
		manager := sandbox.NewManager(sandbox.ManagerConfig{
			Namespace:      "platform-execution",
			DefaultTimeout: 30 * time.Second,
			MaxTimeout:     300 * time.Second,
			MaxConcurrent:  1,
			Store:          serverStore{},
			Pods:           pods,
			Emitter:        serverEmitter{},
		})
		server := &SandboxServiceServer{Manager: manager}
		createResponse, err := server.CreateSandbox(context.Background(), &sandboxv1.CreateSandboxRequest{
			TemplateName: "python3.12",
			Correlation:  &sandboxv1.CorrelationContext{WorkspaceId: "ws-1", ExecutionId: "exec-1"},
		})
		if err != nil {
			t.Fatalf("CreateSandbox() error = %v", err)
		}
		server.Executor = executor.New(manager, pods, nil, 1024)
		_, err = server.ExecuteSandboxStep(context.Background(), &sandboxv1.ExecuteSandboxStepRequest{
			SandboxId: createResponse.GetSandboxId(),
			Code:      "print(1)",
		})
		if status.Code(err) != grpcodes.FailedPrecondition {
			t.Fatalf("ExecuteSandboxStep() code = %s, want %s", status.Code(err), grpcodes.FailedPrecondition)
		}
	})

	t.Run("deadline exceeded", func(t *testing.T) {
		manager, pods, entry := newReadySandbox(t)
		execSvc := executor.New(manager, pods, nil, 1024)
		execSvc.Exec = func(context.Context, *rest.Config, string, string, []string, io.Reader, io.Writer, io.Writer) error {
			return context.DeadlineExceeded
		}
		server := &SandboxServiceServer{Manager: manager, Executor: execSvc}
		_, err := server.ExecuteSandboxStep(context.Background(), &sandboxv1.ExecuteSandboxStepRequest{
			SandboxId: entry.SandboxID,
			Code:      "print(1)",
		})
		if status.Code(err) != grpcodes.DeadlineExceeded {
			t.Fatalf("ExecuteSandboxStep() code = %s, want %s", status.Code(err), grpcodes.DeadlineExceeded)
		}
	})

	t.Run("internal", func(t *testing.T) {
		manager, pods, entry := newReadySandbox(t)
		expectedErr := errors.New("exec boom")
		execSvc := executor.New(manager, pods, nil, 1024)
		execSvc.Exec = func(context.Context, *rest.Config, string, string, []string, io.Reader, io.Writer, io.Writer) error {
			return expectedErr
		}
		server := &SandboxServiceServer{Manager: manager, Executor: execSvc}
		_, err := server.ExecuteSandboxStep(context.Background(), &sandboxv1.ExecuteSandboxStepRequest{
			SandboxId: entry.SandboxID,
			Code:      "print(1)",
		})
		if status.Code(err) != grpcodes.Internal {
			t.Fatalf("ExecuteSandboxStep() code = %s, want %s", status.Code(err), grpcodes.Internal)
		}
	})
}

func TestStreamSandboxLogsErrorMappings(t *testing.T) {
	t.Parallel()

	t.Run("sandbox not found", func(t *testing.T) {
		server := &SandboxServiceServer{Manager: sandbox.NewManager(sandbox.ManagerConfig{Namespace: "platform-execution"}), Fanout: logs.NewFanoutRegistry(4)}
		err := server.StreamSandboxLogs(&sandboxv1.StreamSandboxLogsRequest{SandboxId: "missing"}, &sandboxLogStream{ctx: context.Background()})
		if status.Code(err) != grpcodes.NotFound {
			t.Fatalf("StreamSandboxLogs() code = %s, want %s", status.Code(err), grpcodes.NotFound)
		}
	})

	t.Run("buffered send error", func(t *testing.T) {
		manager, _, entry := newReadySandbox(t)
		fanout := logs.NewFanoutRegistry(4)
		fanout.Publish(entry.SandboxID, &sandboxv1.SandboxLogLine{Line: "buffered"})
		server := &SandboxServiceServer{Manager: manager, Fanout: fanout}
		expectedErr := errors.New("send boom")
		err := server.StreamSandboxLogs(&sandboxv1.StreamSandboxLogsRequest{SandboxId: entry.SandboxID}, &sandboxLogStream{
			ctx:     context.Background(),
			sendErr: expectedErr,
		})
		if !errors.Is(err, expectedErr) {
			t.Fatalf("StreamSandboxLogs() error = %v, want %v", err, expectedErr)
		}
	})
}

func TestTerminateSandboxErrorMappings(t *testing.T) {
	t.Parallel()

	t.Run("sandbox not found", func(t *testing.T) {
		server := &SandboxServiceServer{Manager: sandbox.NewManager(sandbox.ManagerConfig{Namespace: "platform-execution"})}
		_, err := server.TerminateSandbox(context.Background(), &sandboxv1.TerminateSandboxRequest{SandboxId: "missing"})
		if status.Code(err) != grpcodes.NotFound {
			t.Fatalf("TerminateSandbox() code = %s, want %s", status.Code(err), grpcodes.NotFound)
		}
	})

	t.Run("deadline exceeded", func(t *testing.T) {
		manager, pods, entry := newReadySandbox(t)
		pods.deleteErr = errors.New("delete boom")
		server := &SandboxServiceServer{Manager: manager}
		_, err := server.TerminateSandbox(context.Background(), &sandboxv1.TerminateSandboxRequest{SandboxId: entry.SandboxID})
		if status.Code(err) != grpcodes.DeadlineExceeded {
			t.Fatalf("TerminateSandbox() code = %s, want %s", status.Code(err), grpcodes.DeadlineExceeded)
		}
	})
}

func TestCollectSandboxArtifactsErrorMappings(t *testing.T) {
	t.Parallel()

	t.Run("sandbox not found", func(t *testing.T) {
		server := &SandboxServiceServer{
			Collector: artifacts.NewCollector(sandbox.NewManager(sandbox.ManagerConfig{Namespace: "platform-execution"}), nil, nil, "bucket"),
		}
		_, err := server.CollectSandboxArtifacts(context.Background(), &sandboxv1.CollectSandboxArtifactsRequest{SandboxId: "missing"})
		if status.Code(err) != grpcodes.NotFound {
			t.Fatalf("CollectSandboxArtifacts() code = %s, want %s", status.Code(err), grpcodes.NotFound)
		}
	})

	t.Run("failed precondition", func(t *testing.T) {
		server := &SandboxServiceServer{
			Collector: artifacts.NewCollector(nil, nil, nil, "bucket"),
		}
		_, err := server.CollectSandboxArtifacts(context.Background(), &sandboxv1.CollectSandboxArtifactsRequest{SandboxId: "sandbox-1"})
		if status.Code(err) != grpcodes.FailedPrecondition {
			t.Fatalf("CollectSandboxArtifacts() code = %s, want %s", status.Code(err), grpcodes.FailedPrecondition)
		}
	})
}
