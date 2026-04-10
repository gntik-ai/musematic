package reasoningv1

import (
	"context"
	"io"
	"log/slog"
	"net"
	"testing"
	"time"

	"github.com/musematic/reasoning-engine/internal/budget_tracker"
	"github.com/musematic/reasoning-engine/internal/correction_loop"
	"github.com/musematic/reasoning-engine/internal/cot_coordinator"
	"github.com/musematic/reasoning-engine/internal/mode_selector"
	"github.com/musematic/reasoning-engine/internal/tot_manager"
	"github.com/musematic/reasoning-engine/pkg/metrics"
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
	statuses map[string]*budget_tracker.BudgetStatus
	registry *budget_tracker.EventRegistry
}

func newBudgetTrackerStub(registry *budget_tracker.EventRegistry) *budgetTrackerStub {
	return &budgetTrackerStub{
		statuses: map[string]*budget_tracker.BudgetStatus{},
		registry: registry,
	}
}

func (b *budgetTrackerStub) Allocate(_ context.Context, execID, stepID string, limits budget_tracker.BudgetAllocation, _ int64) error {
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
	statusValue, ok := b.statuses[budget_tracker.Key(execID, stepID)]
	if !ok {
		return nil, budget_tracker.ErrBudgetNotFound
	}
	return statusValue, nil
}

type traceCoordinatorStub struct{}

func (traceCoordinatorStub) ProcessStream(_ context.Context, stream cot_coordinator.TraceStream) (*cot_coordinator.TraceAck, error) {
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

type totManagerStub struct{}

func (totManagerStub) CreateBranch(_ context.Context, treeID, branchID, hypothesis string, _ budget_tracker.BudgetAllocation) (*tot_manager.BranchHandle, error) {
	return &tot_manager.BranchHandle{TreeID: treeID, BranchID: branchID, Status: "CREATED", CreatedAt: time.Now().UTC()}, nil
}

func (totManagerStub) EvaluateBranches(context.Context, string, string) (*tot_manager.SelectionResult, error) {
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

type correctionLoopStub struct{}

func (correctionLoopStub) Start(context.Context, string, string, correction_loop.LoopConfig) (*correction_loop.LoopHandle, error) {
	return &correction_loop.LoopHandle{LoopID: "loop-1", Status: "RUNNING", StartedAt: time.Now().UTC()}, nil
}

func (correctionLoopStub) Submit(context.Context, string, float64, float64, int64) (correction_loop.Status, int, float64, error) {
	return correction_loop.StatusConverged, 6, 0.003, nil
}

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
	defer conn.Close()

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

	registry.Register(budget_tracker.Key("exec-1", "step-1"))
	directStream := &fakeBudgetEventStream{ctx: context.Background()}
	go registry.Close(budget_tracker.Key("exec-1", "step-1"), budget_tracker.BudgetEvent{
		ExecutionID: "exec-1",
		StepID:      "step-1",
		EventType:   "COMPLETED",
		OccurredAt:  time.Now().UTC(),
	})
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

	stream := &generatedBudgetEventServerStream{
		ctx: context.Background(),
		req: &StreamBudgetEventsRequest{ExecutionId: "exec-2", StepId: "step-1"},
	}
	go registry.Close(budget_tracker.Key("exec-2", "step-1"), budget_tracker.BudgetEvent{
		ExecutionID: "exec-2",
		StepID:      "step-1",
		EventType:   "COMPLETED",
		OccurredAt:  time.Now().UTC(),
	})
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
	ctx    context.Context
	events []*BudgetEvent
}

func (s *fakeBudgetEventStream) Context() context.Context { return s.ctx }
func (s *fakeBudgetEventStream) Send(event *BudgetEvent) error {
	s.events = append(s.events, event)
	return nil
}
func (s *fakeBudgetEventStream) SetHeader(metadata.MD) error  { return nil }
func (s *fakeBudgetEventStream) SendHeader(metadata.MD) error { return nil }
func (s *fakeBudgetEventStream) SetTrailer(metadata.MD)       {}
func (s *fakeBudgetEventStream) SendMsg(any) error            { return nil }
func (s *fakeBudgetEventStream) RecvMsg(any) error            { return nil }

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
	*request = *s.req
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
