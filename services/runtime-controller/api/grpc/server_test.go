package grpcserver

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"sync"
	"testing"
	"time"

	runtimev1 "github.com/andrea-mucci/musematic/services/runtime-controller/api/grpc/v1"
	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/artifacts"
	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/events"
	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/launcher"
	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/state"
	runtimemetrics "github.com/andrea-mucci/musematic/services/runtime-controller/pkg/metrics"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"
	v1 "k8s.io/api/core/v1"
)

type fakeLaunchStore struct {
	runtime     state.RuntimeRecord
	getErr      error
	inserted    []state.RuntimeRecord
	taskPlans   []state.TaskPlanRecord
	events      []state.RuntimeEventRecord
	updatedTo   string
	updateErr   error
	insertErr   error
	taskPlanErr error
}

func (f *fakeLaunchStore) InsertRuntime(_ context.Context, record state.RuntimeRecord) error {
	if f.insertErr != nil {
		return f.insertErr
	}
	f.inserted = append(f.inserted, record)
	return nil
}

func (f *fakeLaunchStore) GetRuntimeByExecutionID(context.Context, string) (state.RuntimeRecord, error) {
	return f.runtime, f.getErr
}

func (f *fakeLaunchStore) UpdateRuntimeState(_ context.Context, _ string, stateValue string, _ string) error {
	if f.updateErr != nil {
		return f.updateErr
	}
	f.updatedTo = stateValue
	return nil
}

func (f *fakeLaunchStore) InsertTaskPlanRecord(_ context.Context, record state.TaskPlanRecord) error {
	if f.taskPlanErr != nil {
		return f.taskPlanErr
	}
	f.taskPlans = append(f.taskPlans, record)
	return nil
}

func (f *fakeLaunchStore) InsertRuntimeEvent(_ context.Context, event state.RuntimeEventRecord) error {
	f.events = append(f.events, event)
	return nil
}

type fakeServerStore struct {
	record        state.RuntimeRecord
	getErr        error
	eventsSince   []state.RuntimeEventRecord
	eventsErr     error
	updateErr     error
	insertErr     error
	warmStatus    []state.WarmPoolStatusRecord
	warmStatusErr error
	upsertErr     error
	updates       []struct {
		executionID string
		stateValue  string
		reason      string
	}
	upserts []struct {
		workspaceID string
		agentType   string
		targetSize  int
	}
	insertedEvents []state.RuntimeEventRecord
}

func (f *fakeServerStore) GetRuntimeByExecutionID(context.Context, string) (state.RuntimeRecord, error) {
	return f.record, f.getErr
}

func (f *fakeServerStore) UpdateRuntimeState(_ context.Context, executionID string, stateValue string, reason string) error {
	if f.updateErr != nil {
		return f.updateErr
	}
	f.updates = append(f.updates, struct {
		executionID string
		stateValue  string
		reason      string
	}{executionID: executionID, stateValue: stateValue, reason: reason})
	return nil
}

func (f *fakeServerStore) GetRuntimeEventsSince(context.Context, string, time.Time) ([]state.RuntimeEventRecord, error) {
	return f.eventsSince, f.eventsErr
}

func (f *fakeServerStore) InsertRuntimeEvent(_ context.Context, event state.RuntimeEventRecord) error {
	if f.insertErr != nil {
		return f.insertErr
	}
	f.insertedEvents = append(f.insertedEvents, event)
	return nil
}

func (f *fakeServerStore) ListWarmPoolStatus(context.Context, string, string) ([]state.WarmPoolStatusRecord, error) {
	return f.warmStatus, f.warmStatusErr
}

func (f *fakeServerStore) UpsertWarmPoolTarget(_ context.Context, workspaceID string, agentType string, targetSize int) error {
	if f.upsertErr != nil {
		return f.upsertErr
	}
	f.upserts = append(f.upserts, struct {
		workspaceID string
		agentType   string
		targetSize  int
	}{workspaceID: workspaceID, agentType: agentType, targetSize: targetSize})
	return nil
}

type fakePodOps struct {
	mu          sync.Mutex
	created     *v1.Pod
	execErr     error
	deleteErr   error
	logsErr     error
	logs        []byte
	phase       v1.PodPhase
	getErr      error
	execOutputs map[string][]byte
	execCalls   [][]string
	deletes     []int64
}

func (f *fakePodOps) CreatePod(_ context.Context, pod *v1.Pod) (*v1.Pod, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.created = pod
	return pod, nil
}

func (f *fakePodOps) PrepareWarmPod(context.Context, string, *runtimev1.RuntimeContract) error {
	return nil
}

func (f *fakePodOps) ExecInPod(_ context.Context, _ string, cmd []string) ([]byte, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.execCalls = append(f.execCalls, append([]string(nil), cmd...))
	if f.execErr != nil {
		return nil, f.execErr
	}
	if f.execOutputs != nil {
		if output, ok := f.execOutputs[cmd[len(cmd)-1]]; ok {
			return output, nil
		}
	}
	return []byte("ok"), nil
}

func (f *fakePodOps) GetPod(context.Context, string) (*v1.Pod, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.getErr != nil {
		return nil, f.getErr
	}
	phase := f.phase
	if phase == "" {
		phase = v1.PodSucceeded
	}
	return &v1.Pod{Status: v1.PodStatus{Phase: phase}}, nil
}

func (f *fakePodOps) DeletePod(_ context.Context, _ string, gracePeriodSeconds int64) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.deleteErr != nil {
		return f.deleteErr
	}
	f.deletes = append(f.deletes, gracePeriodSeconds)
	return nil
}

func (f *fakePodOps) GetPodLogs(context.Context, string) ([]byte, error) {
	return f.logs, f.logsErr
}

type fakeRuntimeLookupError struct{ err error }

func (f fakeRuntimeLookupError) GetRuntimeByExecutionID(context.Context, string) (state.RuntimeRecord, error) {
	return state.RuntimeRecord{}, f.err
}

func (fakeRuntimeLookupError) UpdateRuntimeState(context.Context, string, string, string) error {
	return nil
}
func (fakeRuntimeLookupError) GetRuntimeEventsSince(context.Context, string, time.Time) ([]state.RuntimeEventRecord, error) {
	return nil, nil
}
func (fakeRuntimeLookupError) InsertRuntimeEvent(context.Context, state.RuntimeEventRecord) error {
	return nil
}
func (fakeRuntimeLookupError) ListWarmPoolStatus(context.Context, string, string) ([]state.WarmPoolStatusRecord, error) {
	return nil, nil
}
func (fakeRuntimeLookupError) UpsertWarmPoolTarget(context.Context, string, string, int) error {
	return nil
}

type fakePresigner struct{}

func (fakePresigner) PresignAgentPackageURL(context.Context, string, time.Duration) (string, error) {
	return "https://example.invalid/agent.tgz", nil
}

type fakeRuntimeEventStream struct {
	ctx  context.Context
	sent []*runtimev1.RuntimeEvent
	err  error
}

func (f *fakeRuntimeEventStream) Send(event *runtimev1.RuntimeEvent) error {
	if f.err != nil {
		return f.err
	}
	f.sent = append(f.sent, event)
	return nil
}

func (f *fakeRuntimeEventStream) SetHeader(metadata.MD) error  { return nil }
func (f *fakeRuntimeEventStream) SendHeader(metadata.MD) error { return nil }
func (f *fakeRuntimeEventStream) SetTrailer(metadata.MD)       {}
func (f *fakeRuntimeEventStream) Context() context.Context     { return f.ctx }
func (f *fakeRuntimeEventStream) SendMsg(any) error            { return nil }
func (f *fakeRuntimeEventStream) RecvMsg(any) error            { return nil }

func runtimeRecord(stateValue string) state.RuntimeRecord {
	now := time.Now().UTC()
	return state.RuntimeRecord{
		RuntimeID:       uuid.New(),
		ExecutionID:     "exec-1",
		WorkspaceID:     "ws-1",
		State:           stateValue,
		PodName:         "pod-1",
		LaunchedAt:      &now,
		LastHeartbeatAt: &now,
	}
}

func TestLaunchRuntimeSuccessAndAlreadyExists(t *testing.T) {
	launchStore := &fakeLaunchStore{getErr: pgx.ErrNoRows}
	pods := &fakePodOps{}
	service := &RuntimeControlServiceServer{
		Launcher: &launcher.Launcher{
			Namespace:  "platform-execution",
			PresignTTL: time.Hour,
			Store:      launchStore,
			Pods:       pods,
			Presigner:  fakePresigner{},
		},
		Metrics: runtimemetrics.NewRegistry(),
	}

	response, err := service.LaunchRuntime(context.Background(), &runtimev1.LaunchRuntimeRequest{
		Contract: &runtimev1.RuntimeContract{
			AgentRevision: "agent-v1",
			CorrelationContext: &runtimev1.CorrelationContext{
				ExecutionId: "exec-1",
				WorkspaceId: "ws-1",
			},
		},
	})
	if err != nil {
		t.Fatalf("LaunchRuntime returned error: %v", err)
	}
	if response.RuntimeId == "" || response.State != runtimev1.RuntimeState_RUNTIME_STATE_RUNNING || response.WarmStart {
		t.Fatalf("unexpected launch response: %+v", response)
	}

	launchStore.getErr = nil
	launchStore.runtime = state.RuntimeRecord{RuntimeID: uuid.New(), ExecutionID: "exec-1"}
	_, err = service.LaunchRuntime(context.Background(), &runtimev1.LaunchRuntimeRequest{
		Contract: &runtimev1.RuntimeContract{CorrelationContext: &runtimev1.CorrelationContext{ExecutionId: "exec-1", WorkspaceId: "ws-1"}},
	})
	if status.Code(err) != codes.AlreadyExists {
		t.Fatalf("expected AlreadyExists, got %v", err)
	}

	_, err = service.LaunchRuntime(context.Background(), &runtimev1.LaunchRuntimeRequest{Contract: &runtimev1.RuntimeContract{}})
	if status.Code(err) != codes.InvalidArgument {
		t.Fatalf("expected InvalidArgument, got %v", err)
	}

	launchStore = &fakeLaunchStore{getErr: pgx.ErrNoRows, insertErr: errors.New("insert failed")}
	service.Launcher.Store = launchStore
	_, err = service.LaunchRuntime(context.Background(), &runtimev1.LaunchRuntimeRequest{
		Contract: &runtimev1.RuntimeContract{CorrelationContext: &runtimev1.CorrelationContext{ExecutionId: "exec-2", WorkspaceId: "ws-1"}},
	})
	if status.Code(err) != codes.Internal {
		t.Fatalf("expected Internal, got %v", err)
	}
}

func TestWarmPoolStatusAndConfig(t *testing.T) {
	now := time.Now().UTC()
	store := &fakeServerStore{warmStatus: []state.WarmPoolStatusRecord{{
		WorkspaceID:     "ws-1",
		AgentType:       "python-3.12",
		TargetSize:      5,
		AvailableCount:  3,
		DispatchedCount: 2,
		WarmingCount:    1,
		LastDispatchAt:  &now,
	}}}
	metrics := runtimemetrics.NewRegistry()
	service := &RuntimeControlServiceServer{Store: store, Metrics: metrics}

	statusResponse, err := service.WarmPoolStatus(context.Background(), &runtimev1.WarmPoolStatusRequest{})
	if err != nil {
		t.Fatalf("WarmPoolStatus returned error: %v", err)
	}
	if len(statusResponse.Keys) != 1 || statusResponse.Keys[0].AvailableCount != 3 {
		t.Fatalf("unexpected warm pool status response: %+v", statusResponse)
	}
	snapshot := metrics.Snapshot()
	if snapshot.WarmPoolTarget["ws-1/python-3.12"] != 5 || snapshot.WarmPoolAvailable["ws-1/python-3.12"] != 3 {
		t.Fatalf("warm pool metrics were not updated from status response: %+v", snapshot)
	}

	configResponse, err := service.WarmPoolConfig(context.Background(), &runtimev1.WarmPoolConfigRequest{
		WorkspaceId: "ws-1",
		AgentType:   "python-3.12",
		TargetSize:  7,
	})
	if err != nil {
		t.Fatalf("WarmPoolConfig returned error: %v", err)
	}
	if !configResponse.Accepted || len(store.upserts) != 1 || store.upserts[0].targetSize != 7 {
		t.Fatalf("unexpected warm pool config result: %+v upserts=%+v", configResponse, store.upserts)
	}

	if _, err := service.WarmPoolConfig(context.Background(), &runtimev1.WarmPoolConfigRequest{TargetSize: 1}); status.Code(err) != codes.InvalidArgument {
		t.Fatalf("expected InvalidArgument for missing identifiers, got %v", err)
	}
	if _, err := service.WarmPoolConfig(context.Background(), &runtimev1.WarmPoolConfigRequest{WorkspaceId: "ws-1", AgentType: "python-3.12", TargetSize: -1}); status.Code(err) != codes.InvalidArgument {
		t.Fatalf("expected InvalidArgument for negative target size, got %v", err)
	}

	store.warmStatusErr = errors.New("status failed")
	if _, err := service.WarmPoolStatus(context.Background(), &runtimev1.WarmPoolStatusRequest{}); status.Code(err) != codes.Internal {
		t.Fatalf("expected Internal for status lookup error, got %v", err)
	}

	store.warmStatusErr = nil
	store.upsertErr = errors.New("upsert failed")
	if _, err := service.WarmPoolConfig(context.Background(), &runtimev1.WarmPoolConfigRequest{WorkspaceId: "ws-1", AgentType: "python-3.12", TargetSize: 7}); status.Code(err) != codes.Internal {
		t.Fatalf("expected Internal for upsert error, got %v", err)
	}

	if timestampOrNil(nil) != nil {
		t.Fatalf("expected nil timestamp for nil time pointer")
	}
}

func TestGetRuntimeMapsRecordAndNotFound(t *testing.T) {
	record := runtimeRecord("running")
	store := &fakeServerStore{record: record}
	service := &RuntimeControlServiceServer{Store: store}

	response, err := service.GetRuntime(context.Background(), &runtimev1.GetRuntimeRequest{ExecutionId: "exec-1"})
	if err != nil {
		t.Fatalf("GetRuntime returned error: %v", err)
	}
	if response.Runtime.RuntimeId != record.RuntimeID.String() || response.Runtime.State != runtimev1.RuntimeState_RUNTIME_STATE_RUNNING {
		t.Fatalf("unexpected runtime response: %+v", response.Runtime)
	}

	store.getErr = pgx.ErrNoRows
	_, err = service.GetRuntime(context.Background(), &runtimev1.GetRuntimeRequest{ExecutionId: "exec-1"})
	if status.Code(err) != codes.NotFound {
		t.Fatalf("expected NotFound, got %v", err)
	}
}

func TestPauseResumeAndStopRuntime(t *testing.T) {
	store := &fakeServerStore{record: runtimeRecord("running")}
	pods := &fakePodOps{}
	service := &RuntimeControlServiceServer{Store: store, Pods: pods, Fanout: events.NewFanoutRegistry()}

	pause, err := service.PauseRuntime(context.Background(), &runtimev1.PauseRuntimeRequest{ExecutionId: "exec-1"})
	if err != nil || pause.State != runtimev1.RuntimeState_RUNTIME_STATE_PAUSED {
		t.Fatalf("unexpected pause result: %+v err=%v", pause, err)
	}

	store.record.State = "paused"
	resume, err := service.ResumeRuntime(context.Background(), &runtimev1.ResumeRuntimeRequest{ExecutionId: "exec-1"})
	if err != nil || resume.State != runtimev1.RuntimeState_RUNTIME_STATE_RUNNING {
		t.Fatalf("unexpected resume result: %+v err=%v", resume, err)
	}

	store.record.State = "running"
	stop, err := service.StopRuntime(context.Background(), &runtimev1.StopRuntimeRequest{ExecutionId: "exec-1"})
	if err != nil || stop.State != runtimev1.RuntimeState_RUNTIME_STATE_STOPPED {
		t.Fatalf("unexpected stop result: %+v err=%v", stop, err)
	}
	if len(pods.deletes) != 1 || pods.deletes[0] != 30 {
		t.Fatalf("unexpected delete calls: %+v", pods.deletes)
	}
	if len(store.insertedEvents) < 3 {
		t.Fatalf("expected broadcast events for transitions, got %d", len(store.insertedEvents))
	}
}

func TestStopRuntimeForceKillsWhenPodDoesNotTerminate(t *testing.T) {
	store := &fakeServerStore{record: runtimeRecord("running")}
	pods := &fakePodOps{phase: v1.PodRunning}
	service := &RuntimeControlServiceServer{Store: store, Pods: pods, Fanout: events.NewFanoutRegistry()}

	response, err := service.StopRuntime(context.Background(), &runtimev1.StopRuntimeRequest{ExecutionId: "exec-1", GracePeriodSeconds: 1})
	if err != nil {
		t.Fatalf("StopRuntime returned error: %v", err)
	}
	if !response.ForceKilled || response.State != runtimev1.RuntimeState_RUNTIME_STATE_FORCE_STOPPED {
		t.Fatalf("expected force stop response, got %+v", response)
	}
	if len(pods.deletes) != 1 || pods.deletes[0] != 0 {
		t.Fatalf("expected force delete grace 0, got %+v", pods.deletes)
	}
}

func TestStopRuntimeTreatsMissingPodAsTerminatedAndStartsCollection(t *testing.T) {
	store := &fakeServerStore{record: runtimeRecord("running")}
	pods := &fakePodOps{getErr: errors.New("pod disappeared"), logs: []byte("logs")}
	service := &RuntimeControlServiceServer{
		Store: store,
		Pods:  pods,
		Collector: &artifacts.Collector{
			Store:    store,
			Pods:     pods,
			Uploader: &artifacts.BytesUploader{},
		},
	}

	response, err := service.StopRuntime(context.Background(), &runtimev1.StopRuntimeRequest{ExecutionId: "exec-1", GracePeriodSeconds: 1})
	if err != nil {
		t.Fatalf("StopRuntime returned error: %v", err)
	}
	if response.ForceKilled {
		t.Fatalf("missing pod should be treated as already terminated")
	}
}

func TestPauseResumeAndStopRuntimeErrorBranches(t *testing.T) {
	store := &fakeServerStore{record: runtimeRecord("paused")}
	pods := &fakePodOps{}
	service := &RuntimeControlServiceServer{Store: store, Pods: pods}

	if _, err := service.PauseRuntime(context.Background(), &runtimev1.PauseRuntimeRequest{ExecutionId: "exec-1"}); status.Code(err) != codes.FailedPrecondition {
		t.Fatalf("expected pause precondition failure, got %v", err)
	}

	store.record.State = "running"
	pods.execErr = errors.New("exec failed")
	pause, err := service.PauseRuntime(context.Background(), &runtimev1.PauseRuntimeRequest{ExecutionId: "exec-1"})
	if err != nil || pause.State != runtimev1.RuntimeState_RUNTIME_STATE_RUNNING {
		t.Fatalf("unexpected pause fallback result: %+v err=%v", pause, err)
	}

	store.record.State = "running"
	if _, err := service.ResumeRuntime(context.Background(), &runtimev1.ResumeRuntimeRequest{ExecutionId: "exec-1"}); status.Code(err) != codes.FailedPrecondition {
		t.Fatalf("expected resume precondition failure, got %v", err)
	}

	store.record.State = "paused"
	resume, err := service.ResumeRuntime(context.Background(), &runtimev1.ResumeRuntimeRequest{ExecutionId: "exec-1"})
	if err != nil || resume.State != runtimev1.RuntimeState_RUNTIME_STATE_PAUSED {
		t.Fatalf("expected resume fallback, got response=%+v err=%v", resume, err)
	}

	store.record.State = "running"
	pods.execErr = nil
	pods.deleteErr = errors.New("delete failed")
	if _, err := service.StopRuntime(context.Background(), &runtimev1.StopRuntimeRequest{ExecutionId: "exec-1", GracePeriodSeconds: 5}); status.Code(err) != codes.Internal {
		t.Fatalf("expected stop internal error, got %v", err)
	}
}

func TestRuntimeStateHandlersReturnLookupAndUpdateErrors(t *testing.T) {
	store := &fakeServerStore{getErr: pgx.ErrNoRows}
	service := &RuntimeControlServiceServer{Store: store, Pods: &fakePodOps{}}
	if _, err := service.PauseRuntime(context.Background(), &runtimev1.PauseRuntimeRequest{ExecutionId: "missing"}); status.Code(err) != codes.NotFound {
		t.Fatalf("expected pause not found, got %v", err)
	}
	if _, err := service.ResumeRuntime(context.Background(), &runtimev1.ResumeRuntimeRequest{ExecutionId: "missing"}); status.Code(err) != codes.NotFound {
		t.Fatalf("expected resume not found, got %v", err)
	}
	if _, err := service.StopRuntime(context.Background(), &runtimev1.StopRuntimeRequest{ExecutionId: "missing"}); status.Code(err) != codes.NotFound {
		t.Fatalf("expected stop not found, got %v", err)
	}

	store = &fakeServerStore{record: runtimeRecord("running"), updateErr: errors.New("update failed")}
	service = &RuntimeControlServiceServer{Store: store, Pods: &fakePodOps{}}
	if _, err := service.PauseRuntime(context.Background(), &runtimev1.PauseRuntimeRequest{ExecutionId: "exec-1"}); status.Code(err) != codes.Internal {
		t.Fatalf("expected pause update error, got %v", err)
	}
	if _, err := service.StopRuntime(context.Background(), &runtimev1.StopRuntimeRequest{ExecutionId: "exec-1"}); status.Code(err) != codes.Internal {
		t.Fatalf("expected stop update error, got %v", err)
	}

	store = &fakeServerStore{record: runtimeRecord("paused"), updateErr: errors.New("update failed")}
	service = &RuntimeControlServiceServer{Store: store, Pods: &fakePodOps{}}
	if _, err := service.ResumeRuntime(context.Background(), &runtimev1.ResumeRuntimeRequest{ExecutionId: "exec-1"}); status.Code(err) != codes.Internal {
		t.Fatalf("expected resume update error, got %v", err)
	}
}

func TestStreamRuntimeEventsReplaysAndStreamsTerminalEvent(t *testing.T) {
	store := &fakeServerStore{
		record: runtimeRecord("running"),
		eventsSince: []state.RuntimeEventRecord{{
			EventID:     uuid.New(),
			RuntimeID:   uuid.New(),
			ExecutionID: "exec-1",
			EventType:   "runtime.launched",
			Payload:     []byte(`{"event":"replayed"}`),
			EmittedAt:   time.Now().UTC(),
		}},
	}
	fanout := events.NewFanoutRegistry()
	service := &RuntimeControlServiceServer{Store: store, Fanout: fanout}
	stream := &fakeRuntimeEventStream{ctx: context.Background()}
	done := make(chan error, 1)

	go func() {
		done <- service.StreamRuntimeEvents(&runtimev1.StreamRuntimeEventsRequest{
			ExecutionId: "exec-1",
			Since:       timestamppb.New(time.Now().Add(-time.Minute)),
		}, stream)
	}()
	time.Sleep(20 * time.Millisecond)
	fanout.Publish(&runtimev1.RuntimeEvent{
		EventId:     uuid.NewString(),
		ExecutionId: "exec-1",
		NewState:    runtimev1.RuntimeState_RUNTIME_STATE_STOPPED,
	})

	select {
	case err := <-done:
		if err != nil {
			t.Fatalf("StreamRuntimeEvents returned error: %v", err)
		}
	case <-time.After(time.Second):
		t.Fatalf("timed out waiting for stream completion")
	}
	if len(stream.sent) != 2 {
		t.Fatalf("expected replayed + live event, got %d", len(stream.sent))
	}
	if stream.sent[0].DetailsJson != `{"event":"replayed"}` || stream.sent[1].NewState != runtimev1.RuntimeState_RUNTIME_STATE_STOPPED {
		t.Fatalf("unexpected streamed events: %+v", stream.sent)
	}
}

func TestCollectRuntimeArtifactsPublishesManifest(t *testing.T) {
	store := &fakeServerStore{record: runtimeRecord("running")}
	pods := &fakePodOps{
		logs: []byte("runtime logs"),
		execOutputs: map[string][]byte{
			"ls -1 /agent/outputs 2>/dev/null || true": []byte("artifact.txt\n"),
			"cat /agent/outputs/artifact.txt":          []byte("artifact body"),
		},
	}
	fanout := events.NewFanoutRegistry()
	ch, unsubscribe := fanout.Subscribe("exec-1")
	defer unsubscribe()
	service := &RuntimeControlServiceServer{
		Store: store,
		Collector: &artifacts.Collector{
			Store:    store,
			Pods:     pods,
			Uploader: &artifacts.BytesUploader{},
		},
		Fanout: fanout,
	}

	response, err := service.CollectRuntimeArtifacts(context.Background(), &runtimev1.CollectRuntimeArtifactsRequest{ExecutionId: "exec-1"})
	if err != nil {
		t.Fatalf("CollectRuntimeArtifacts returned error: %v", err)
	}
	if len(response.Artifacts) != 2 || !response.Complete {
		t.Fatalf("unexpected artifacts response: %+v", response)
	}
	select {
	case event := <-ch:
		if event.EventType != runtimev1.RuntimeEventType_RUNTIME_EVENT_ARTIFACT_COLLECTED {
			t.Fatalf("unexpected manifest event: %+v", event)
		}
	default:
		t.Fatalf("expected artifact manifest event")
	}
}

func TestUtilityHelpersAndInterceptors(t *testing.T) {
	if mapState("running") != runtimev1.RuntimeState_RUNTIME_STATE_RUNNING ||
		mapState("paused") != runtimev1.RuntimeState_RUNTIME_STATE_PAUSED ||
		mapState("stopped") != runtimev1.RuntimeState_RUNTIME_STATE_STOPPED ||
		mapState("force_stopped") != runtimev1.RuntimeState_RUNTIME_STATE_FORCE_STOPPED ||
		mapState("failed") != runtimev1.RuntimeState_RUNTIME_STATE_FAILED ||
		mapState("unknown") != runtimev1.RuntimeState_RUNTIME_STATE_PENDING {
		t.Fatalf("unexpected state mapping")
	}
	if timestamp(nil) != nil {
		t.Fatalf("expected nil timestamp for nil time")
	}

	unaryCalled := false
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	unary, err := UnaryLoggingInterceptor(logger)(context.Background(), "request", &grpc.UnaryServerInfo{FullMethod: "/runtime.Log"}, func(context.Context, any) (any, error) {
		unaryCalled = true
		return "response", nil
	})
	if err != nil || unary != "response" || !unaryCalled {
		t.Fatalf("unexpected unary interceptor result: %v %v", unary, err)
	}

	streamCalled := false
	err = StreamLoggingInterceptor(logger)("srv", &fakeRuntimeEventStream{ctx: context.Background()}, &grpc.StreamServerInfo{FullMethod: "/runtime.StreamLog"}, func(any, grpc.ServerStream) error {
		streamCalled = true
		return nil
	})
	if err != nil || !streamCalled {
		t.Fatalf("unexpected stream interceptor result: %v", err)
	}

	tracingUnaryCalled := false
	tracingUnary, err := UnaryTracingInterceptor()(context.Background(), "request", &grpc.UnaryServerInfo{FullMethod: "/runtime.Trace"}, func(context.Context, any) (any, error) {
		tracingUnaryCalled = true
		return "traced", nil
	})
	if err != nil || tracingUnary != "traced" || !tracingUnaryCalled {
		t.Fatalf("unexpected tracing unary interceptor result: %v %v", tracingUnary, err)
	}

	tracingStreamCalled := false
	err = StreamTracingInterceptor()("srv", &fakeRuntimeEventStream{ctx: context.Background()}, &grpc.StreamServerInfo{FullMethod: "/runtime.TraceStream"}, func(any, grpc.ServerStream) error {
		tracingStreamCalled = true
		return nil
	})
	if err != nil || !tracingStreamCalled {
		t.Fatalf("unexpected tracing stream interceptor result: %v", err)
	}
}

func TestStreamRuntimeEventsAndCollectArtifactsErrorBranches(t *testing.T) {
	store := &fakeServerStore{getErr: pgx.ErrNoRows}
	service := &RuntimeControlServiceServer{Store: store}

	if err := service.StreamRuntimeEvents(&runtimev1.StreamRuntimeEventsRequest{ExecutionId: "exec-1"}, &fakeRuntimeEventStream{ctx: context.Background()}); status.Code(err) != codes.NotFound {
		t.Fatalf("expected stream not found, got %v", err)
	}

	service = &RuntimeControlServiceServer{Store: &fakeServerStore{record: runtimeRecord("running")}}
	response, err := service.CollectRuntimeArtifacts(context.Background(), &runtimev1.CollectRuntimeArtifactsRequest{ExecutionId: "exec-1"})
	if err != nil || len(response.Artifacts) != 0 || response.Complete {
		t.Fatalf("unexpected nil collector result: %+v err=%v", response, err)
	}

	service = &RuntimeControlServiceServer{Store: &fakeServerStore{record: runtimeRecord("running"), eventsErr: errors.New("replay failed")}}
	err = service.StreamRuntimeEvents(&runtimev1.StreamRuntimeEventsRequest{ExecutionId: "exec-1", Since: timestamppb.Now()}, &fakeRuntimeEventStream{ctx: context.Background()})
	if status.Code(err) != codes.Internal {
		t.Fatalf("expected replay internal error, got %v", err)
	}

	service = &RuntimeControlServiceServer{
		Store:  &fakeServerStore{record: runtimeRecord("running"), eventsSince: []state.RuntimeEventRecord{{RuntimeID: uuid.New(), ExecutionID: "exec-1", EmittedAt: time.Now()}}},
		Fanout: events.NewFanoutRegistry(),
	}
	err = service.StreamRuntimeEvents(&runtimev1.StreamRuntimeEventsRequest{ExecutionId: "exec-1", Since: timestamppb.Now()}, &fakeRuntimeEventStream{ctx: context.Background(), err: errors.New("send failed")})
	if err == nil {
		t.Fatalf("expected stream send error")
	}

	service = &RuntimeControlServiceServer{
		Store: &fakeServerStore{record: runtimeRecord("running"), getErr: nil},
		Collector: &artifacts.Collector{
			Store:    fakeRuntimeLookupError{err: pgx.ErrNoRows},
			Pods:     &fakePodOps{},
			Uploader: &artifacts.BytesUploader{},
		},
	}
	if _, err := service.CollectRuntimeArtifacts(context.Background(), &runtimev1.CollectRuntimeArtifactsRequest{ExecutionId: "exec-1"}); status.Code(err) != codes.NotFound {
		t.Fatalf("expected collect not found, got %v", err)
	}
}

func TestAdditionalServerErrorBranches(t *testing.T) {
	store := &fakeServerStore{getErr: errors.New("boom")}
	service := &RuntimeControlServiceServer{Store: store}
	if _, err := service.GetRuntime(context.Background(), &runtimev1.GetRuntimeRequest{ExecutionId: "exec-1"}); status.Code(err) != codes.Internal {
		t.Fatalf("expected internal get error, got %v", err)
	}

	store = &fakeServerStore{
		record:    runtimeRecord("running"),
		eventsErr: errors.New("events failed"),
	}
	if err := (&RuntimeControlServiceServer{Store: store}).StreamRuntimeEvents(&runtimev1.StreamRuntimeEventsRequest{
		ExecutionId: "exec-1",
		Since:       timestamppb.New(time.Now()),
	}, &fakeRuntimeEventStream{ctx: context.Background()}); status.Code(err) != codes.Internal {
		t.Fatalf("expected stream internal error, got %v", err)
	}

	store = &fakeServerStore{
		record: runtimeRecord("running"),
		eventsSince: []state.RuntimeEventRecord{{
			EventID:   uuid.New(),
			RuntimeID: uuid.New(),
			Payload:   []byte(`{"event":"replayed"}`),
			EmittedAt: time.Now(),
		}},
	}
	if err := (&RuntimeControlServiceServer{Store: store, Fanout: nil}).StreamRuntimeEvents(&runtimev1.StreamRuntimeEventsRequest{
		ExecutionId: "exec-1",
		Since:       timestamppb.New(time.Now()),
	}, &fakeRuntimeEventStream{ctx: context.Background()}); err != nil {
		t.Fatalf("expected replay-only stream success, got %v", err)
	}

	store = &fakeServerStore{
		record: runtimeRecord("running"),
		eventsSince: []state.RuntimeEventRecord{{
			EventID:   uuid.New(),
			RuntimeID: uuid.New(),
			Payload:   []byte(`{"event":"replayed"}`),
			EmittedAt: time.Now(),
		}},
	}
	if err := (&RuntimeControlServiceServer{Store: store, Fanout: nil}).StreamRuntimeEvents(&runtimev1.StreamRuntimeEventsRequest{
		ExecutionId: "exec-1",
		Since:       timestamppb.New(time.Now()),
	}, &fakeRuntimeEventStream{ctx: context.Background(), err: errors.New("send failed")}); err == nil {
		t.Fatalf("expected send error")
	}

	launchStore := &fakeLaunchStore{getErr: pgx.ErrNoRows, insertErr: errors.New("insert failed")}
	_, err := (&RuntimeControlServiceServer{
		Launcher: &launcher.Launcher{
			Namespace: "platform-execution",
			Store:     launchStore,
			Pods:      &fakePodOps{},
		},
	}).LaunchRuntime(context.Background(), &runtimev1.LaunchRuntimeRequest{
		Contract: &runtimev1.RuntimeContract{
			AgentRevision: "agent-v1",
			CorrelationContext: &runtimev1.CorrelationContext{
				ExecutionId: "exec-1",
				WorkspaceId: "ws-1",
			},
		},
	})
	if status.Code(err) != codes.Internal {
		t.Fatalf("expected launch internal error, got %v", err)
	}
}
