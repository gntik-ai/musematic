package reasoningv1

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"net"
	"testing"
	"time"

	"github.com/musematic/reasoning-engine/internal/budget_tracker"
	"github.com/musematic/reasoning-engine/internal/correction_loop"
	"github.com/musematic/reasoning-engine/internal/cot_coordinator"
	"github.com/musematic/reasoning-engine/internal/debate"
	"github.com/musematic/reasoning-engine/internal/mode_selector"
	"github.com/musematic/reasoning-engine/internal/tot_manager"
	"github.com/musematic/reasoning-engine/pkg/metrics"
	"github.com/musematic/reasoning-engine/pkg/persistence"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
	"google.golang.org/grpc/test/bufconn"
	"google.golang.org/protobuf/proto"
	"google.golang.org/protobuf/types/known/timestamppb"
)

type modeSelectorStub struct {
	selection mode_selector.Selection
	err       error
}

func (s modeSelectorStub) Select(context.Context, mode_selector.Request) (mode_selector.Selection, error) {
	return s.selection, s.err
}

type budgetTrackerStub struct {
	statuses    map[string]*budget_tracker.BudgetStatus
	registry    *budget_tracker.EventRegistry
	allocateErr error
	statusErr   error
}

func newBudgetTrackerStub(registry *budget_tracker.EventRegistry) *budgetTrackerStub {
	return &budgetTrackerStub{
		statuses: map[string]*budget_tracker.BudgetStatus{},
		registry: registry,
	}
}

func (b *budgetTrackerStub) Allocate(_ context.Context, execID, stepID string, limits budget_tracker.BudgetAllocation, _ int64) error {
	if b.allocateErr != nil {
		return b.allocateErr
	}
	status := &budget_tracker.BudgetStatus{
		ExecutionID: execID,
		StepID:      stepID,
		Limits:      limits,
		Used:        budget_tracker.BudgetAllocation{},
		Status:      "ALLOCATED",
		AllocatedAt: time.Now().UTC(),
	}
	key := budget_tracker.Key(execID, stepID)
	b.statuses[key] = status
	if b.registry != nil {
		b.registry.Register(key)
		b.registry.Publish(key, budget_tracker.BudgetEvent{
			ExecutionID: execID,
			StepID:      stepID,
			EventType:   "ALLOCATED",
			OccurredAt:  time.Now().UTC(),
		})
	}
	return nil
}

func (b *budgetTrackerStub) Decrement(_ context.Context, execID, stepID, _ string, amount float64) (float64, error) {
	key := budget_tracker.Key(execID, stepID)
	statusValue, ok := b.statuses[key]
	if !ok {
		return 0, budget_tracker.ErrBudgetNotFound
	}
	statusValue.Used.Tokens += int64(amount)
	return float64(statusValue.Used.Tokens), nil
}

func (b *budgetTrackerStub) GetStatus(_ context.Context, execID, stepID string) (*budget_tracker.BudgetStatus, error) {
	if b.statusErr != nil {
		return nil, b.statusErr
	}
	statusValue, ok := b.statuses[budget_tracker.Key(execID, stepID)]
	if !ok {
		return nil, budget_tracker.ErrBudgetNotFound
	}
	return statusValue, nil
}

type traceCoordinatorStub struct {
	err error
}

func (s traceCoordinatorStub) ProcessStream(_ context.Context, stream cot_coordinator.TraceStream) (*cot_coordinator.TraceAck, error) {
	if s.err != nil {
		return nil, s.err
	}
	ack := &cot_coordinator.TraceAck{}
	for {
		event, err := stream.Recv()
		if err == io.EOF {
			return ack, nil
		}
		if err != nil {
			return nil, err
		}
		ack.ExecutionID = event.ExecutionID
		ack.TotalReceived++
		ack.TotalPersisted++
	}
}

type totManagerStub struct {
	createErr error
	evalErr   error
}

func (s totManagerStub) CreateBranch(_ context.Context, treeID, branchID, hypothesis string, _ budget_tracker.BudgetAllocation) (*tot_manager.BranchHandle, error) {
	if s.createErr != nil {
		return nil, s.createErr
	}
	return &tot_manager.BranchHandle{TreeID: treeID, BranchID: branchID, Status: "CREATED", CreatedAt: time.Now().UTC()}, nil
}

func (s totManagerStub) EvaluateBranches(context.Context, string, string) (*tot_manager.SelectionResult, error) {
	if s.evalErr != nil {
		return nil, s.evalErr
	}
	return &tot_manager.SelectionResult{
		SelectedBranchID:  "branch-1",
		SelectedQuality:   0.9,
		SelectedTokenCost: 3,
		AllBranches: []tot_manager.BranchSummary{{
			BranchID:     "branch-1",
			Hypothesis:   "best branch",
			QualityScore: 0.9,
			TokenCost:    3,
			Status:       "COMPLETED",
			Score:        0.225,
		}},
	}, nil
}

type correctionLoopStub struct {
	startErr  error
	submitErr error
	status    correction_loop.Status
	iteration int
	delta     float64
}

func (s correctionLoopStub) Start(context.Context, string, string, correction_loop.LoopConfig) (*correction_loop.LoopHandle, error) {
	if s.startErr != nil {
		return nil, s.startErr
	}
	return &correction_loop.LoopHandle{LoopID: "loop-1", Status: "RUNNING", StartedAt: time.Now().UTC()}, nil
}

func (s correctionLoopStub) Submit(context.Context, string, float64, float64, int64) (correction_loop.Status, int, float64, error) {
	if s.submitErr != nil {
		return "", 0, 0, s.submitErr
	}
	if s.status == "" {
		return correction_loop.StatusConverged, 6, 0.003, nil
	}
	return s.status, s.iteration, s.delta, nil
}

//nolint:gocyclo // This test intentionally exercises the whole public gRPC surface in one flow.
func TestHandlerUnaryAndStreamingRPCs(t *testing.T) {
	registry := budget_tracker.NewEventRegistry()
	budgets := newBudgetTrackerStub(registry)
	handler := NewHandler(HandlerDependencies{
		ModeSelector:   modeSelectorStub{selection: mode_selector.Selection{Mode: "DIRECT", ComplexityScore: 1, RecommendedBudget: mode_selector.BudgetAllocation{Tokens: 100, Rounds: 1, Cost: 0.1, TimeMS: 1000}, Rationale: "simple"}},
		BudgetTracker:  budgets,
		EventRegistry:  registry,
		CoTCoordinator: traceCoordinatorStub{},
		ToTManager:     totManagerStub{},
		CorrectionLoop: correctionLoopStub{},
		Metrics:        metrics.New(),
	})

	listener := bufconn.Listen(1024 * 1024)
	server := grpc.NewServer()
	RegisterReasoningEngineServiceServer(server, handler)
	go func() {
		_ = server.Serve(listener)
	}()
	defer server.Stop()

	conn, err := grpc.NewClient("passthrough:///bufnet",
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithContextDialer(func(context.Context, string) (net.Conn, error) { return listener.Dial() }),
	)
	if err != nil {
		t.Fatalf("grpc.NewClient() error = %v", err)
	}
	defer func() {
		_ = conn.Close()
	}()

	client := NewReasoningEngineServiceClient(conn)

	modeResp, err := client.SelectReasoningMode(context.Background(), &SelectReasoningModeRequest{
		ExecutionId:       "exec-1",
		TaskBrief:         "What is 2+2?",
		BudgetConstraints: &BudgetConstraints{MaxTokens: 1000},
	})
	if err != nil || modeResp.GetMode() != ReasoningMode_DIRECT {
		t.Fatalf("SelectReasoningMode() resp=%+v err=%v", modeResp, err)
	}

	envelope, err := client.AllocateReasoningBudget(context.Background(), &AllocateReasoningBudgetRequest{
		ExecutionId: "exec-1",
		StepId:      "step-1",
		Limits:      &BudgetAllocation{Tokens: 1000},
	})
	if err != nil || envelope.GetStatus() != "ALLOCATED" {
		t.Fatalf("AllocateReasoningBudget() resp=%+v err=%v", envelope, err)
	}

	statusResp, err := client.GetReasoningBudgetStatus(context.Background(), &GetBudgetStatusRequest{ExecutionId: "exec-1", StepId: "step-1"})
	if err != nil || statusResp.GetEnvelope().GetExecutionId() != "exec-1" {
		t.Fatalf("GetReasoningBudgetStatus() resp=%+v err=%v", statusResp, err)
	}

	go func() {
		waitForBudgetSubscriber(registry, budget_tracker.Key("exec-1", "step-1"))
		registry.Close(budget_tracker.Key("exec-1", "step-1"), budget_tracker.BudgetEvent{
			ExecutionID: "exec-1",
			StepID:      "step-1",
			EventType:   "COMPLETED",
			OccurredAt:  time.Now().UTC(),
		})
	}()
	streamCtx, cancelStream := context.WithTimeout(context.Background(), time.Second)
	defer cancelStream()
	budgetStream, err := client.StreamBudgetEvents(streamCtx, &StreamBudgetEventsRequest{ExecutionId: "exec-1", StepId: "step-1"})
	if err != nil {
		t.Fatalf("StreamBudgetEvents() error = %v", err)
	}
	event, err := budgetStream.Recv()
	if err != nil || event.GetEventType() != "COMPLETED" {
		t.Fatalf("StreamBudgetEvents() event=%+v err=%v", event, err)
	}

	registry.Register(budget_tracker.Key("exec-1", "step-1"))
	directCtx, cancelDirect := context.WithTimeout(context.Background(), time.Second)
	defer cancelDirect()
	directStream := &fakeBudgetEventStream{ctx: directCtx}
	go func() {
		waitForBudgetSubscriber(registry, budget_tracker.Key("exec-1", "step-1"))
		registry.Close(budget_tracker.Key("exec-1", "step-1"), budget_tracker.BudgetEvent{
			ExecutionID: "exec-1",
			StepID:      "step-1",
			EventType:   "COMPLETED",
			OccurredAt:  time.Now().UTC(),
		})
	}()
	if err := handler.StreamBudgetEvents(&StreamBudgetEventsRequest{ExecutionId: "exec-1", StepId: "step-1"}, directStream); err != nil {
		t.Fatalf("direct StreamBudgetEvents() error = %v", err)
	}
	if len(directStream.events) != 1 || directStream.events[0].GetEventType() != "COMPLETED" {
		t.Fatalf("direct stream events = %+v", directStream.events)
	}

	traceClient, err := client.StreamReasoningTrace(context.Background())
	if err != nil {
		t.Fatalf("StreamReasoningTrace() error = %v", err)
	}
	if err := traceClient.Send(&ReasoningTraceEvent{
		ExecutionId: "exec-1",
		StepId:      "step-1",
		EventId:     "event-1",
		EventType:   "reasoning_step",
		SequenceNum: 1,
		Payload:     []byte("payload"),
		OccurredAt:  timestamppb.Now(),
	}); err != nil {
		t.Fatalf("trace Send() error = %v", err)
	}
	traceAck, err := traceClient.CloseAndRecv()
	if err != nil || traceAck.GetTotalReceived() != 1 {
		t.Fatalf("trace CloseAndRecv() resp=%+v err=%v", traceAck, err)
	}

	treeHandle, err := client.CreateTreeBranch(context.Background(), &CreateTreeBranchRequest{
		TreeId:       "tree-1",
		BranchId:     "branch-1",
		Hypothesis:   "best branch",
		BranchBudget: &BudgetAllocation{Tokens: 10},
	})
	if err != nil || treeHandle.GetStatus() != "CREATED" {
		t.Fatalf("CreateTreeBranch() resp=%+v err=%v", treeHandle, err)
	}

	treeSelection, err := client.EvaluateTreeBranches(context.Background(), &EvaluateTreeBranchesRequest{TreeId: "tree-1"})
	if err != nil || treeSelection.GetSelectedBranchId() != "branch-1" {
		t.Fatalf("EvaluateTreeBranches() resp=%+v err=%v", treeSelection, err)
	}

	loopHandle, err := client.StartSelfCorrectionLoop(context.Background(), &StartSelfCorrectionRequest{
		LoopId:        "loop-1",
		ExecutionId:   "exec-1",
		MaxIterations: 10,
		CostCap:       1,
		Epsilon:       0.01,
	})
	if err != nil || loopHandle.GetStatus() != "RUNNING" {
		t.Fatalf("StartSelfCorrectionLoop() resp=%+v err=%v", loopHandle, err)
	}

	convergence, err := client.SubmitCorrectionIteration(context.Background(), &CorrectionIterationEvent{
		LoopId:       "loop-1",
		QualityScore: 0.808,
		Cost:         0.1,
		DurationMs:   10,
	})
	if err != nil || convergence.GetStatus() != ConvergenceStatus_CONVERGED {
		t.Fatalf("SubmitCorrectionIteration() resp=%+v err=%v", convergence, err)
	}
}

func TestHandlerRPCsWithInterceptors(t *testing.T) {
	registry := budget_tracker.NewEventRegistry()
	budgets := newBudgetTrackerStub(registry)
	handler := NewHandler(HandlerDependencies{
		ModeSelector:   modeSelectorStub{selection: mode_selector.Selection{Mode: "DIRECT", ComplexityScore: 1, RecommendedBudget: mode_selector.BudgetAllocation{Tokens: 100, Rounds: 1, Cost: 0.1, TimeMS: 1000}, Rationale: "simple"}},
		BudgetTracker:  budgets,
		EventRegistry:  registry,
		CoTCoordinator: traceCoordinatorStub{},
		ToTManager:     totManagerStub{},
		CorrectionLoop: correctionLoopStub{},
		Metrics:        metrics.New(),
	})

	unaryInterceptor := UnaryInterceptor(slog.New(slog.NewTextHandler(io.Discard, nil)))
	ctx := context.Background()

	if _, err := _ReasoningEngineService_SelectReasoningMode_Handler(handler, ctx, decodeMessage(&SelectReasoningModeRequest{
		ExecutionId:       "exec-2",
		TaskBrief:         "Explain the answer",
		BudgetConstraints: &BudgetConstraints{MaxTokens: 1000},
	}), unaryInterceptor); err != nil {
		t.Fatalf("SelectReasoningMode handler error = %v", err)
	}

	if _, err := _ReasoningEngineService_AllocateReasoningBudget_Handler(handler, ctx, decodeMessage(&AllocateReasoningBudgetRequest{
		ExecutionId: "exec-2",
		StepId:      "step-1",
		Limits:      &BudgetAllocation{Tokens: 1000},
	}), unaryInterceptor); err != nil {
		t.Fatalf("AllocateReasoningBudget handler error = %v", err)
	}

	if _, err := _ReasoningEngineService_GetReasoningBudgetStatus_Handler(handler, ctx, decodeMessage(&GetBudgetStatusRequest{
		ExecutionId: "exec-2",
		StepId:      "step-1",
	}), unaryInterceptor); err != nil {
		t.Fatalf("GetReasoningBudgetStatus handler error = %v", err)
	}

	interceptorCtx, cancelInterceptorStream := context.WithTimeout(context.Background(), time.Second)
	defer cancelInterceptorStream()
	stream := &generatedBudgetEventServerStream{
		ctx: interceptorCtx,
		req: &StreamBudgetEventsRequest{ExecutionId: "exec-2", StepId: "step-1"},
	}
	go func() {
		waitForBudgetSubscriber(registry, budget_tracker.Key("exec-2", "step-1"))
		registry.Close(budget_tracker.Key("exec-2", "step-1"), budget_tracker.BudgetEvent{
			ExecutionID: "exec-2",
			StepID:      "step-1",
			EventType:   "COMPLETED",
			OccurredAt:  time.Now().UTC(),
		})
	}()
	if err := _ReasoningEngineService_StreamBudgetEvents_Handler(handler, stream); err != nil {
		t.Fatalf("StreamBudgetEvents handler error = %v", err)
	}
	if len(stream.events) != 1 || stream.events[0].GetEventType() != "COMPLETED" {
		t.Fatalf("unexpected streamed events: %+v", stream.events)
	}

	if _, err := _ReasoningEngineService_CreateTreeBranch_Handler(handler, ctx, decodeMessage(&CreateTreeBranchRequest{
		TreeId:       "tree-2",
		BranchId:     "branch-1",
		Hypothesis:   "best branch",
		BranchBudget: &BudgetAllocation{Tokens: 10},
	}), unaryInterceptor); err != nil {
		t.Fatalf("CreateTreeBranch handler error = %v", err)
	}

	if _, err := _ReasoningEngineService_EvaluateTreeBranches_Handler(handler, ctx, decodeMessage(&EvaluateTreeBranchesRequest{
		TreeId: "tree-2",
	}), unaryInterceptor); err != nil {
		t.Fatalf("EvaluateTreeBranches handler error = %v", err)
	}

	if _, err := _ReasoningEngineService_StartSelfCorrectionLoop_Handler(handler, ctx, decodeMessage(&StartSelfCorrectionRequest{
		LoopId:        "loop-2",
		ExecutionId:   "exec-2",
		MaxIterations: 10,
		CostCap:       1,
		Epsilon:       0.01,
	}), unaryInterceptor); err != nil {
		t.Fatalf("StartSelfCorrectionLoop handler error = %v", err)
	}

	if _, err := _ReasoningEngineService_SubmitCorrectionIteration_Handler(handler, ctx, decodeMessage(&CorrectionIterationEvent{
		LoopId:       "loop-2",
		QualityScore: 0.8,
		Cost:         0.1,
		DurationMs:   10,
	}), unaryInterceptor); err != nil {
		t.Fatalf("SubmitCorrectionIteration handler error = %v", err)
	}
}

func TestHandlerUnaryAndStreamingRPCsDebateAndTrace(t *testing.T) {
	traceReader := &traceStoreStub{record: &persistence.ReasoningTraceRecord{
		ExecutionID: "exec-debate-grpc",
		Technique:   "DEBATE",
		Status:      "complete",
		StorageKey:  "reasoning-traces/exec-debate-grpc/DEBATE/debate-grpc.json",
		StepCount:   2,
	}}
	uploader := &capturingTraceUploader{}
	traceWriter := &capturingTraceStore{}
	events := &capturingReasoningEvents{debateDone: make(chan map[string]any, 1)}
	handler := NewHandler(HandlerDependencies{
		DebateService:   debate.NewService(debate.NewConsensusDetector(nil, 0.05), uploader, traceWriter, events),
		TraceStore:      traceReader,
		TraceUploader:   uploader,
		ReasoningEvents: events,
		Metrics:         metrics.New(),
	})

	listener := bufconn.Listen(1024 * 1024)
	server := grpc.NewServer()
	RegisterReasoningEngineServiceServer(server, handler)
	go func() {
		_ = server.Serve(listener)
	}()
	defer server.Stop()

	conn, err := grpc.NewClient("passthrough:///bufnet",
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithContextDialer(func(context.Context, string) (net.Conn, error) { return listener.Dial() }),
	)
	if err != nil {
		t.Fatalf("grpc.NewClient() error = %v", err)
	}
	defer func() {
		_ = conn.Close()
	}()

	client := NewReasoningEngineServiceClient(conn)

	started, err := client.StartDebateSession(context.Background(), &StartDebateSessionRequest{
		ExecutionId:     "exec-debate-grpc",
		DebateId:        "debate-grpc",
		ParticipantFqns: []string{"agent.alpha", "agent.beta"},
		RoundLimit:      2,
	})
	if err != nil || started.GetStatus() != "RUNNING" {
		t.Fatalf("StartDebateSession() resp=%+v err=%v", started, err)
	}

	if _, err := client.SubmitDebateTurn(context.Background(), &SubmitDebateTurnRequest{
		DebateId:   "debate-grpc",
		AgentFqn:   "agent.alpha",
		StepType:   "synthesis",
		Content:    "aligned answer for consensus",
		TokensUsed: 21,
		OccurredAt: timestamppb.Now(),
	}); err != nil {
		t.Fatalf("SubmitDebateTurn(first) error = %v", err)
	}
	round, err := client.SubmitDebateTurn(context.Background(), &SubmitDebateTurnRequest{
		DebateId:     "debate-grpc",
		AgentFqn:     "agent.beta",
		StepType:     "synthesis",
		Content:      "shared answer for consensus",
		QualityScore: 0.92,
		TokensUsed:   18,
		OccurredAt:   timestamppb.Now(),
	})
	if err != nil || !round.GetDebateComplete() {
		t.Fatalf("SubmitDebateTurn(second) resp=%+v err=%v", round, err)
	}

	final, err := client.FinalizeDebateSession(context.Background(), &FinalizeDebateSessionRequest{DebateId: "debate-grpc"})
	if err != nil || final.GetStorageKey() == "" {
		t.Fatalf("FinalizeDebateSession() resp=%+v err=%v", final, err)
	}

	traceResp, err := client.GetReasoningTrace(context.Background(), &GetReasoningTraceRequest{ExecutionId: "exec-debate-grpc", StepId: "debate-grpc"})
	if err != nil || traceResp.GetStorageKey() != traceReader.record.StorageKey {
		t.Fatalf("GetReasoningTrace() resp=%+v err=%v", traceResp, err)
	}
}

func TestHandlerRPCsWithInterceptorsDebateAndTrace(t *testing.T) {
	traceReader := &traceStoreStub{record: &persistence.ReasoningTraceRecord{
		ExecutionID: "exec-debate-interceptor",
		Technique:   "DEBATE",
		Status:      "complete",
		StorageKey:  "reasoning-traces/exec-debate-interceptor/DEBATE/debate-interceptor.json",
		StepCount:   2,
	}}
	uploader := &capturingTraceUploader{}
	traceWriter := &capturingTraceStore{}
	events := &capturingReasoningEvents{debateDone: make(chan map[string]any, 1)}
	handler := NewHandler(HandlerDependencies{
		DebateService:   debate.NewService(debate.NewConsensusDetector(nil, 0.05), uploader, traceWriter, events),
		TraceStore:      traceReader,
		TraceUploader:   uploader,
		ReasoningEvents: events,
		Metrics:         metrics.New(),
	})

	unaryInterceptor := UnaryInterceptor(slog.New(slog.NewTextHandler(io.Discard, nil)))
	ctx := context.Background()

	if _, err := _ReasoningEngineService_StartDebateSession_Handler(handler, ctx, decodeMessage(&StartDebateSessionRequest{
		ExecutionId:     "exec-debate-interceptor",
		DebateId:        "debate-interceptor",
		ParticipantFqns: []string{"agent.alpha", "agent.beta"},
		RoundLimit:      2,
	}), unaryInterceptor); err != nil {
		t.Fatalf("StartDebateSession handler error = %v", err)
	}

	if _, err := _ReasoningEngineService_SubmitDebateTurn_Handler(handler, ctx, decodeMessage(&SubmitDebateTurnRequest{
		DebateId:   "debate-interceptor",
		AgentFqn:   "agent.alpha",
		StepType:   "synthesis",
		Content:    "aligned answer for consensus",
		TokensUsed: 21,
		OccurredAt: timestamppb.Now(),
	}), unaryInterceptor); err != nil {
		t.Fatalf("SubmitDebateTurn(first) handler error = %v", err)
	}

	if _, err := _ReasoningEngineService_SubmitDebateTurn_Handler(handler, ctx, decodeMessage(&SubmitDebateTurnRequest{
		DebateId:     "debate-interceptor",
		AgentFqn:     "agent.beta",
		StepType:     "synthesis",
		Content:      "shared answer for consensus",
		QualityScore: 0.92,
		TokensUsed:   18,
		OccurredAt:   timestamppb.Now(),
	}), unaryInterceptor); err != nil {
		t.Fatalf("SubmitDebateTurn(second) handler error = %v", err)
	}

	if _, err := _ReasoningEngineService_FinalizeDebateSession_Handler(handler, ctx, decodeMessage(&FinalizeDebateSessionRequest{
		DebateId: "debate-interceptor",
	}), unaryInterceptor); err != nil {
		t.Fatalf("FinalizeDebateSession handler error = %v", err)
	}

	if _, err := _ReasoningEngineService_GetReasoningTrace_Handler(handler, ctx, decodeMessage(&GetReasoningTraceRequest{
		ExecutionId: "exec-debate-interceptor",
		StepId:      "debate-interceptor",
	}), unaryInterceptor); err != nil {
		t.Fatalf("GetReasoningTrace handler error = %v", err)
	}
}

func TestHandlerValidationAndHelpers(t *testing.T) {
	handler := NewHandler(HandlerDependencies{})
	if _, err := handler.SelectReasoningMode(context.Background(), &SelectReasoningModeRequest{}); status.Code(err) != codes.InvalidArgument {
		t.Fatalf("SelectReasoningMode() error code = %s", status.Code(err))
	}
	if _, err := handler.GetReasoningBudgetStatus(context.Background(), &GetBudgetStatusRequest{}); status.Code(err) != codes.Unimplemented {
		t.Fatalf("GetReasoningBudgetStatus() error code = %s", status.Code(err))
	}

	if modeToProto("DEBATE") != ReasoningMode_DEBATE {
		t.Fatal("modeToProto() did not map DEBATE")
	}
	if convergenceToProto(correction_loop.StatusEscalateToHuman) != ConvergenceStatus_ESCALATE_TO_HUMAN {
		t.Fatal("convergenceToProto() did not map ESCALATE_TO_HUMAN")
	}
	if safeInt32(1<<62) != 2147483647 {
		t.Fatal("safeInt32() did not clamp upper bound")
	}

	envelope := envelopeFromBudgetStatus(&budget_tracker.BudgetStatus{
		ExecutionID: "exec-1",
		StepID:      "step-1",
		Limits:      budget_tracker.BudgetAllocation{Tokens: 10},
		Used:        budget_tracker.BudgetAllocation{Tokens: 5},
		Status:      "ACTIVE",
		AllocatedAt: time.Now().UTC(),
	})
	if envelope.GetUsed().GetTokens() != 5 {
		t.Fatalf("envelope used tokens = %d, want 5", envelope.GetUsed().GetTokens())
	}
	if (traceStreamAdapter{stream: &fakeReasoningTraceStream{ctx: context.Background()}}).Context() == nil {
		t.Fatal("traceStreamAdapter Context() returned nil")
	}
}

func TestHandlerErrorMappings(t *testing.T) {
	registry := budget_tracker.NewEventRegistry()
	budgets := newBudgetTrackerStub(registry)
	handler := NewHandler(HandlerDependencies{
		ModeSelector:   modeSelectorStub{err: mode_selector.ErrNoModeFits},
		BudgetTracker:  budgets,
		EventRegistry:  registry,
		CoTCoordinator: traceCoordinatorStub{err: errors.New("trace failed")},
		ToTManager:     totManagerStub{createErr: tot_manager.ErrConcurrencyLimit, evalErr: tot_manager.ErrTreeNotFound},
		CorrectionLoop: correctionLoopStub{startErr: correction_loop.ErrLoopExists},
	})

	_, err := handler.SelectReasoningMode(context.Background(), &SelectReasoningModeRequest{
		ExecutionId: "exec-1",
		TaskBrief:   "complex",
	})
	if status.Code(err) != codes.ResourceExhausted {
		t.Fatalf("SelectReasoningMode() code = %s", status.Code(err))
	}

	budgets.allocateErr = budget_tracker.ErrAlreadyExists
	_, err = handler.AllocateReasoningBudget(context.Background(), &AllocateReasoningBudgetRequest{
		ExecutionId: "exec-1",
		StepId:      "step-1",
		Limits:      &BudgetAllocation{Tokens: 1},
	})
	if status.Code(err) != codes.AlreadyExists {
		t.Fatalf("AllocateReasoningBudget() code = %s", status.Code(err))
	}

	budgets.allocateErr = nil
	_, err = handler.AllocateReasoningBudget(context.Background(), &AllocateReasoningBudgetRequest{
		ExecutionId: "exec-1",
		StepId:      "step-1",
		Limits:      &BudgetAllocation{Tokens: -1},
	})
	if status.Code(err) != codes.InvalidArgument {
		t.Fatalf("AllocateReasoningBudget() invalid code = %s", status.Code(err))
	}

	budgets.statusErr = errors.New("boom")
	_, err = handler.GetReasoningBudgetStatus(context.Background(), &GetBudgetStatusRequest{ExecutionId: "exec-1", StepId: "step-1"})
	if status.Code(err) != codes.Internal {
		t.Fatalf("GetReasoningBudgetStatus() code = %s", status.Code(err))
	}

	err = handler.StreamReasoningTrace(&fakeReasoningTraceStream{ctx: context.Background()})
	if status.Code(err) != codes.Internal {
		t.Fatalf("StreamReasoningTrace() code = %s", status.Code(err))
	}

	_, err = handler.CreateTreeBranch(context.Background(), &CreateTreeBranchRequest{})
	if status.Code(err) != codes.ResourceExhausted {
		t.Fatalf("CreateTreeBranch() code = %s", status.Code(err))
	}

	_, err = handler.EvaluateTreeBranches(context.Background(), &EvaluateTreeBranchesRequest{})
	if status.Code(err) != codes.NotFound {
		t.Fatalf("EvaluateTreeBranches() code = %s", status.Code(err))
	}

	_, err = handler.StartSelfCorrectionLoop(context.Background(), &StartSelfCorrectionRequest{LoopId: "loop-1", ExecutionId: "exec-1", MaxIterations: 3, CostCap: 1, Epsilon: 0.01})
	if status.Code(err) != codes.AlreadyExists {
		t.Fatalf("StartSelfCorrectionLoop() code = %s", status.Code(err))
	}

	handler = NewHandler(HandlerDependencies{
		CorrectionLoop: correctionLoopStub{submitErr: correction_loop.ErrLoopNotRunning},
	})
	handler.selfCorrectionSessions["loop-1"] = &selfCorrectionSession{LoopID: "loop-1", ExecutionID: "exec-1", StepID: "step-1", MaxIterations: 3, BestQuality: -1}
	_, err = handler.SubmitCorrectionIteration(context.Background(), &CorrectionIterationEvent{LoopId: "loop-1"})
	if status.Code(err) != codes.FailedPrecondition {
		t.Fatalf("SubmitCorrectionIteration() code = %s", status.Code(err))
	}
}

func TestInterceptorsRecoverPanics(t *testing.T) {
	unary := UnaryInterceptor(slog.New(slog.NewTextHandler(io.Discard, nil)))
	if _, err := unary(context.Background(), nil, &grpc.UnaryServerInfo{FullMethod: "/test"}, func(context.Context, any) (any, error) {
		panic("boom")
	}); status.Code(err) != codes.Internal {
		t.Fatalf("UnaryInterceptor() code = %s", status.Code(err))
	}

	stream := StreamInterceptor(slog.New(slog.NewTextHandler(io.Discard, nil)))
	if err := stream(nil, &fakeServerStream{ctx: context.Background()}, &grpc.StreamServerInfo{FullMethod: "/test"}, func(any, grpc.ServerStream) error {
		panic("boom")
	}); status.Code(err) != codes.Internal {
		t.Fatalf("StreamInterceptor() code = %s", status.Code(err))
	}
}

func TestHandlerAdditionalBranches(t *testing.T) { //nolint:gocyclo // This test intentionally drives the public handler through many error-mapping branches.
	t.Run("unimplemented dependencies", func(t *testing.T) {
		handler := NewHandler(HandlerDependencies{})

		if _, err := handler.SelectReasoningMode(context.Background(), &SelectReasoningModeRequest{ExecutionId: "exec", TaskBrief: "brief"}); status.Code(err) != codes.Unimplemented {
			t.Fatalf("SelectReasoningMode() code = %s", status.Code(err))
		}
		if _, err := handler.AllocateReasoningBudget(context.Background(), &AllocateReasoningBudgetRequest{ExecutionId: "exec", StepId: "step"}); status.Code(err) != codes.Unimplemented {
			t.Fatalf("AllocateReasoningBudget() code = %s", status.Code(err))
		}
		if err := handler.StreamBudgetEvents(&StreamBudgetEventsRequest{ExecutionId: "exec", StepId: "step"}, &fakeBudgetEventStream{ctx: context.Background()}); status.Code(err) != codes.Unimplemented {
			t.Fatalf("StreamBudgetEvents() code = %s", status.Code(err))
		}
		if err := handler.StreamReasoningTrace(&fakeReasoningTraceStream{ctx: context.Background()}); status.Code(err) != codes.Unimplemented {
			t.Fatalf("StreamReasoningTrace() code = %s", status.Code(err))
		}
		if _, err := handler.CreateTreeBranch(context.Background(), &CreateTreeBranchRequest{}); status.Code(err) != codes.Unimplemented {
			t.Fatalf("CreateTreeBranch() code = %s", status.Code(err))
		}
		if _, err := handler.EvaluateTreeBranches(context.Background(), &EvaluateTreeBranchesRequest{}); status.Code(err) != codes.Unimplemented {
			t.Fatalf("EvaluateTreeBranches() code = %s", status.Code(err))
		}
		if _, err := handler.StartSelfCorrectionLoop(context.Background(), &StartSelfCorrectionRequest{}); status.Code(err) != codes.Unimplemented {
			t.Fatalf("StartSelfCorrectionLoop() code = %s", status.Code(err))
		}
		if _, err := handler.SubmitCorrectionIteration(context.Background(), &CorrectionIterationEvent{}); status.Code(err) != codes.Unimplemented {
			t.Fatalf("SubmitCorrectionIteration() code = %s", status.Code(err))
		}
	})

	t.Run("generic handler mappings", func(t *testing.T) {
		registry := budget_tracker.NewEventRegistry()
		budgets := newBudgetTrackerStub(registry)
		handler := NewHandler(HandlerDependencies{
			ModeSelector:   modeSelectorStub{err: errors.New("selector failed")},
			BudgetTracker:  budgets,
			EventRegistry:  registry,
			CoTCoordinator: traceCoordinatorStub{},
			ToTManager:     totManagerStub{createErr: tot_manager.ErrBranchExists, evalErr: errors.New("eval failed")},
			CorrectionLoop: correctionLoopStub{startErr: errors.New("bad config"), submitErr: correction_loop.ErrLoopNotFound},
			Metrics:        metrics.New(),
		})

		if _, err := handler.SelectReasoningMode(context.Background(), &SelectReasoningModeRequest{ExecutionId: "exec", TaskBrief: "brief"}); status.Code(err) != codes.Internal {
			t.Fatalf("SelectReasoningMode() code = %s", status.Code(err))
		}
		budgets.allocateErr = errors.New("allocate failed")
		if _, err := handler.AllocateReasoningBudget(context.Background(), &AllocateReasoningBudgetRequest{ExecutionId: "exec", StepId: "step", Limits: &BudgetAllocation{Tokens: 1}}); status.Code(err) != codes.Internal {
			t.Fatalf("AllocateReasoningBudget() code = %s", status.Code(err))
		}
		budgets.allocateErr = nil
		budgets.statusErr = budget_tracker.ErrBudgetNotFound
		if _, err := handler.GetReasoningBudgetStatus(context.Background(), &GetBudgetStatusRequest{ExecutionId: "exec", StepId: "step"}); status.Code(err) != codes.NotFound {
			t.Fatalf("GetReasoningBudgetStatus() code = %s", status.Code(err))
		}
		budgets.statusErr = nil

		if _, err := handler.CreateTreeBranch(context.Background(), &CreateTreeBranchRequest{BranchBudget: &BudgetAllocation{}}); status.Code(err) != codes.AlreadyExists {
			t.Fatalf("CreateTreeBranch() code = %s", status.Code(err))
		}
		if _, err := handler.EvaluateTreeBranches(context.Background(), &EvaluateTreeBranchesRequest{}); status.Code(err) != codes.Internal {
			t.Fatalf("EvaluateTreeBranches() code = %s", status.Code(err))
		}
		if _, err := handler.StartSelfCorrectionLoop(context.Background(), &StartSelfCorrectionRequest{}); status.Code(err) != codes.InvalidArgument {
			t.Fatalf("StartSelfCorrectionLoop() code = %s", status.Code(err))
		}
		if _, err := handler.SubmitCorrectionIteration(context.Background(), &CorrectionIterationEvent{LoopId: "loop"}); status.Code(err) != codes.NotFound {
			t.Fatalf("SubmitCorrectionIteration() code = %s", status.Code(err))
		}
	})

	t.Run("stream branches", func(t *testing.T) {
		registry := budget_tracker.NewEventRegistry()
		handler := NewHandler(HandlerDependencies{EventRegistry: registry, CoTCoordinator: traceCoordinatorStub{}})

		if err := handler.StreamBudgetEvents(&StreamBudgetEventsRequest{ExecutionId: "exec", StepId: "missing"}, &fakeBudgetEventStream{ctx: context.Background()}); status.Code(err) != codes.NotFound {
			t.Fatalf("StreamBudgetEvents() code = %s", status.Code(err))
		}

		key := budget_tracker.Key("exec", "step")
		registry.Register(key)
		streamCtx, cancelStream := context.WithTimeout(context.Background(), time.Second)
		defer cancelStream()
		stream := &fakeBudgetEventStream{ctx: streamCtx, sendErr: errors.New("send failed")}
		go func() {
			waitForBudgetSubscriber(registry, key)
			registry.Publish(key, budget_tracker.BudgetEvent{ExecutionID: "exec", StepID: "step", EventType: "THRESHOLD_80", OccurredAt: time.Now().UTC()})
		}()
		if err := handler.StreamBudgetEvents(&StreamBudgetEventsRequest{ExecutionId: "exec", StepId: "step"}, stream); err == nil || err.Error() != "send failed" {
			t.Fatalf("StreamBudgetEvents() error = %v", err)
		}

		cancelCtx, cancel := context.WithCancel(context.Background())
		cancel()
		registry.Register(key)
		if err := handler.StreamBudgetEvents(&StreamBudgetEventsRequest{ExecutionId: "exec", StepId: "step"}, &fakeBudgetEventStream{ctx: cancelCtx}); !errors.Is(err, context.Canceled) {
			t.Fatalf("StreamBudgetEvents() error = %v", err)
		}

		if err := handler.StreamReasoningTrace(&fakeReasoningTraceStream{ctx: context.Background(), sendErr: errors.New("close failed")}); err == nil || err.Error() != "close failed" {
			t.Fatalf("StreamReasoningTrace() error = %v", err)
		}
	})
}

func TestGeneratedProtoHelpers(t *testing.T) {
	messages := []proto.Message{
		&SelectReasoningModeRequest{ExecutionId: "exec", TaskBrief: "brief", BudgetConstraints: &BudgetConstraints{MaxTokens: 1}},
		&BudgetConstraints{MaxTokens: 1, MaxRounds: 2, MaxCost: 0.1, MaxTimeMs: 3},
		&ReasoningModeConfig{Mode: ReasoningMode_DIRECT, RecommendedBudget: &BudgetAllocation{Tokens: 1}},
		&BudgetAllocation{Tokens: 1, Rounds: 2, Cost: 0.1, TimeMs: 3},
		&AllocateReasoningBudgetRequest{ExecutionId: "exec", StepId: "step", Limits: &BudgetAllocation{Tokens: 1}},
		&ReasoningBudgetEnvelope{ExecutionId: "exec", StepId: "step", Limits: &BudgetAllocation{Tokens: 1}, Used: &BudgetAllocation{}},
		&GetBudgetStatusRequest{ExecutionId: "exec", StepId: "step"},
		&BudgetStatusResponse{Envelope: &ReasoningBudgetEnvelope{}},
		&StreamBudgetEventsRequest{ExecutionId: "exec", StepId: "step"},
		&BudgetEvent{ExecutionId: "exec", StepId: "step", EventType: "ALLOCATED"},
		&ReasoningTraceEvent{ExecutionId: "exec", StepId: "step", EventId: "event", Payload: []byte("x")},
		&ReasoningTraceAck{ExecutionId: "exec"},
		&CreateTreeBranchRequest{TreeId: "tree", BranchId: "branch", BranchBudget: &BudgetAllocation{Tokens: 1}},
		&TreeBranchHandle{TreeId: "tree", BranchId: "branch"},
		&EvaluateTreeBranchesRequest{TreeId: "tree"},
		&BranchSelectionResult{SelectedBranchId: "branch", AllBranches: []*BranchSummary{{BranchId: "branch"}}},
		&BranchSummary{BranchId: "branch"},
		&StartSelfCorrectionRequest{LoopId: "loop", ExecutionId: "exec", MaxIterations: 1, CostCap: 1},
		&SelfCorrectionHandle{LoopId: "loop"},
		&CorrectionIterationEvent{LoopId: "loop", QualityScore: 0.5},
		&ConvergenceResult{Status: ConvergenceStatus_CONTINUE, LoopId: "loop"},
	}

	for _, message := range messages {
		if stringer, ok := message.(interface{ String() string }); ok {
			_ = stringer.String()
		}
		_ = message.ProtoReflect().Descriptor()
	}

	mode := ReasoningMode_DIRECT
	_ = mode.Enum()
	_ = mode.String()
	_ = mode.Descriptor()
	_ = mode.Type()
	_ = mode.Number()
	_, _ = mode.EnumDescriptor()

	statusValue := ConvergenceStatus_CONVERGED
	_ = statusValue.Enum()
	_ = statusValue.String()
	_ = statusValue.Descriptor()
	_ = statusValue.Type()
	_ = statusValue.Number()
	_, _ = statusValue.EnumDescriptor()
}

type fakeServerStream struct {
	grpc.ServerStream
	ctx context.Context
}

func (s *fakeServerStream) Context() context.Context { return s.ctx }

type fakeBudgetEventStream struct {
	ctx     context.Context
	events  []*BudgetEvent
	sendErr error
}

func (s *fakeBudgetEventStream) Context() context.Context { return s.ctx }
func (s *fakeBudgetEventStream) Send(event *BudgetEvent) error {
	if s.sendErr != nil {
		return s.sendErr
	}
	s.events = append(s.events, event)
	return nil
}
func (s *fakeBudgetEventStream) SetHeader(metadata.MD) error  { return nil }
func (s *fakeBudgetEventStream) SendHeader(metadata.MD) error { return nil }
func (s *fakeBudgetEventStream) SetTrailer(metadata.MD)       {}
func (s *fakeBudgetEventStream) SendMsg(any) error            { return nil }
func (s *fakeBudgetEventStream) RecvMsg(any) error            { return nil }

type fakeReasoningTraceStream struct {
	grpc.ServerStream
	ctx      context.Context
	recvErr  error
	ack      *ReasoningTraceAck
	sendErr  error
	received bool
}

func (s *fakeReasoningTraceStream) Context() context.Context { return s.ctx }
func (s *fakeReasoningTraceStream) SendAndClose(ack *ReasoningTraceAck) error {
	if s.sendErr != nil {
		return s.sendErr
	}
	s.ack = ack
	return nil
}
func (s *fakeReasoningTraceStream) Recv() (*ReasoningTraceEvent, error) {
	if s.recvErr != nil {
		return nil, s.recvErr
	}
	if s.received {
		return nil, io.EOF
	}
	s.received = true
	return &ReasoningTraceEvent{
		ExecutionId: "exec-1",
		StepId:      "step-1",
		EventId:     "event-1",
		EventType:   "reasoning_step",
		Payload:     []byte("payload"),
		OccurredAt:  timestamppb.Now(),
	}, nil
}

type generatedBudgetEventServerStream struct {
	grpc.ServerStream
	ctx    context.Context
	req    *StreamBudgetEventsRequest
	events []*BudgetEvent
}

func (s *generatedBudgetEventServerStream) Context() context.Context { return s.ctx }
func (s *generatedBudgetEventServerStream) SetHeader(metadata.MD) error {
	return nil
}
func (s *generatedBudgetEventServerStream) SendHeader(metadata.MD) error { return nil }
func (s *generatedBudgetEventServerStream) SetTrailer(metadata.MD)       {}
func (s *generatedBudgetEventServerStream) SendMsg(msg any) error {
	event, ok := msg.(*BudgetEvent)
	if !ok {
		return nil
	}
	s.events = append(s.events, event)
	return nil
}
func (s *generatedBudgetEventServerStream) RecvMsg(msg any) error {
	request, ok := msg.(*StreamBudgetEventsRequest)
	if !ok {
		return nil
	}
	proto.Reset(request)
	proto.Merge(request, s.req)
	return nil
}

func decodeMessage[T any](message *T) func(any) error {
	return func(target any) error {
		typed, ok := target.(*T)
		if !ok {
			return nil
		}
		*typed = *message
		return nil
	}
}

func waitForBudgetSubscriber(registry *budget_tracker.EventRegistry, key string) {
	deadline := time.Now().Add(time.Second)
	for time.Now().Before(deadline) {
		if registry.SubscriberCount(key) > 0 {
			return
		}
		time.Sleep(time.Millisecond)
	}
}
