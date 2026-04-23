package reasoningv1

import (
	"context"
	"errors"
	"math"
	"sync"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/musematic/reasoning-engine/internal/budget_tracker"
	"github.com/musematic/reasoning-engine/internal/correction_loop"
	"github.com/musematic/reasoning-engine/internal/cot_coordinator"
	"github.com/musematic/reasoning-engine/internal/debate"
	"github.com/musematic/reasoning-engine/internal/mode_selector"
	"github.com/musematic/reasoning-engine/internal/tot_manager"
	"github.com/musematic/reasoning-engine/pkg/metrics"
	"github.com/musematic/reasoning-engine/pkg/persistence"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"
)

type HandlerDependencies struct {
	ModeSelector    mode_selector.ModeSelector
	BudgetTracker   budget_tracker.BudgetTracker
	EventRegistry   *budget_tracker.EventRegistry
	CoTCoordinator  cot_coordinator.CoTCoordinator
	ToTManager      tot_manager.ToTManager
	DebateService   debate.DebateOrchestrator
	CorrectionLoop  correction_loop.CorrectionLoop
	TraceStore      persistence.TraceRecordStore
	TraceUploader   traceUploader
	ReasoningEvents reasoningEventProducer
	Metrics         *metrics.Metrics
}

type Handler struct {
	UnimplementedReasoningEngineServiceServer
	modeSelector           mode_selector.ModeSelector
	budgetTracker          budget_tracker.BudgetTracker
	eventRegistry          *budget_tracker.EventRegistry
	cotCoordinator         cot_coordinator.CoTCoordinator
	totManager             tot_manager.ToTManager
	debateService          debate.DebateOrchestrator
	correctionLoop         correction_loop.CorrectionLoop
	traceStore             persistence.TraceRecordStore
	traceUploader          traceUploader
	reasoningEvents        reasoningEventProducer
	metrics                *metrics.Metrics
	selfCorrectionMu       sync.Mutex
	selfCorrectionSessions map[string]*selfCorrectionSession
}

func NewHandler(deps HandlerDependencies) *Handler {
	return &Handler{
		modeSelector:           deps.ModeSelector,
		budgetTracker:          deps.BudgetTracker,
		eventRegistry:          deps.EventRegistry,
		cotCoordinator:         deps.CoTCoordinator,
		totManager:             deps.ToTManager,
		debateService:          deps.DebateService,
		correctionLoop:         deps.CorrectionLoop,
		traceStore:             deps.TraceStore,
		traceUploader:          deps.TraceUploader,
		reasoningEvents:        deps.ReasoningEvents,
		metrics:                deps.Metrics,
		selfCorrectionSessions: map[string]*selfCorrectionSession{},
	}
}

func (h *Handler) SelectReasoningMode(ctx context.Context, req *SelectReasoningModeRequest) (*ReasoningModeConfig, error) {
	if req.GetExecutionId() == "" || req.GetTaskBrief() == "" {
		return nil, status.Error(codes.InvalidArgument, "execution_id and task_brief are required")
	}
	if h.modeSelector == nil {
		return nil, status.Error(codes.Unimplemented, "mode selector is not configured")
	}

	selection, err := h.modeSelector.Select(ctx, mode_selector.Request{
		TaskBrief:  req.GetTaskBrief(),
		ForcedMode: req.GetForcedMode(),
		Budget: mode_selector.BudgetConstraints{
			MaxTokens: req.GetBudgetConstraints().GetMaxTokens(),
			MaxRounds: req.GetBudgetConstraints().GetMaxRounds(),
			MaxCost:   req.GetBudgetConstraints().GetMaxCost(),
			MaxTimeMS: req.GetBudgetConstraints().GetMaxTimeMs(),
		},
	})
	if err != nil {
		if errors.Is(err, mode_selector.ErrNoModeFits) {
			return nil, status.Error(codes.ResourceExhausted, err.Error())
		}
		return nil, status.Error(codes.Internal, err.Error())
	}

	if req.ComputeBudget != nil {
		computeBudget := req.GetComputeBudget()
		if computeBudget <= 0 || computeBudget > 1 {
			return nil, status.Error(codes.InvalidArgument, "compute_budget must be within (0,1]")
		}
		selection.RecommendedBudget = mapComputeBudgetToAllocation(
			selection.Mode,
			computeBudget,
			selection.RecommendedBudget,
		)
	}

	h.metrics.RecordModeSelection(ctx, selection.Mode)
	return &ReasoningModeConfig{
		Mode:            modeToProto(selection.Mode),
		ComplexityScore: safeInt32(selection.ComplexityScore),
		RecommendedBudget: &BudgetAllocation{
			Tokens: selection.RecommendedBudget.Tokens,
			Rounds: selection.RecommendedBudget.Rounds,
			Cost:   selection.RecommendedBudget.Cost,
			TimeMs: selection.RecommendedBudget.TimeMS,
		},
		Rationale: selection.Rationale,
	}, nil
}

func (h *Handler) AllocateReasoningBudget(ctx context.Context, req *AllocateReasoningBudgetRequest) (*ReasoningBudgetEnvelope, error) {
	if req.GetExecutionId() == "" || req.GetStepId() == "" {
		return nil, status.Error(codes.InvalidArgument, "execution_id and step_id are required")
	}
	if h.budgetTracker == nil {
		return nil, status.Error(codes.Unimplemented, "budget tracker is not configured")
	}

	limits := budget_tracker.BudgetAllocation{
		Tokens: req.GetLimits().GetTokens(),
		Rounds: req.GetLimits().GetRounds(),
		Cost:   req.GetLimits().GetCost(),
		TimeMS: req.GetLimits().GetTimeMs(),
	}
	if limits.Tokens < 0 || limits.Rounds < 0 || limits.Cost < 0 || limits.TimeMS < 0 {
		return nil, status.Error(codes.InvalidArgument, "budget limits must be non-negative")
	}

	if err := h.budgetTracker.Allocate(ctx, req.GetExecutionId(), req.GetStepId(), limits, req.GetTtlSeconds()); err != nil {
		switch {
		case errors.Is(err, budget_tracker.ErrAlreadyExists):
			return nil, status.Error(codes.AlreadyExists, err.Error())
		default:
			return nil, status.Error(codes.Internal, err.Error())
		}
	}

	statusValue, err := h.budgetTracker.GetStatus(ctx, req.GetExecutionId(), req.GetStepId())
	if err != nil {
		return nil, status.Error(codes.Internal, err.Error())
	}
	return envelopeFromBudgetStatus(statusValue), nil
}

func (h *Handler) GetReasoningBudgetStatus(ctx context.Context, req *GetBudgetStatusRequest) (*BudgetStatusResponse, error) {
	if h.budgetTracker == nil {
		return nil, status.Error(codes.Unimplemented, "budget tracker is not configured")
	}

	statusValue, err := h.budgetTracker.GetStatus(ctx, req.GetExecutionId(), req.GetStepId())
	if err != nil {
		if errors.Is(err, budget_tracker.ErrBudgetNotFound) {
			return nil, status.Error(codes.NotFound, err.Error())
		}
		return nil, status.Error(codes.Internal, err.Error())
	}

	return &BudgetStatusResponse{Envelope: envelopeFromBudgetStatus(statusValue)}, nil
}

func (h *Handler) StreamBudgetEvents(req *StreamBudgetEventsRequest, stream ReasoningEngineService_StreamBudgetEventsServer) error {
	if h.eventRegistry == nil {
		return status.Error(codes.Unimplemented, "budget event registry is not configured")
	}

	key := budget_tracker.Key(req.GetExecutionId(), req.GetStepId())
	ch, ok := h.eventRegistry.SubscribeIfActive(key)
	if !ok {
		return status.Error(codes.NotFound, "budget not found")
	}
	defer h.eventRegistry.Unsubscribe(key, ch)

	for {
		select {
		case <-stream.Context().Done():
			return stream.Context().Err()
		case event, ok := <-ch:
			if !ok {
				return nil
			}
			if err := stream.Send(&BudgetEvent{
				ExecutionId:  event.ExecutionID,
				StepId:       event.StepID,
				EventType:    event.EventType,
				Dimension:    event.Dimension,
				CurrentValue: event.CurrentValue,
				MaxValue:     event.MaxValue,
				OccurredAt:   timestamppb.New(event.OccurredAt),
			}); err != nil {
				return err
			}
			if event.EventType == "COMPLETED" || event.EventType == "EXCEEDED" {
				return nil
			}
		}
	}
}

func (h *Handler) StreamReasoningTrace(stream ReasoningEngineService_StreamReasoningTraceServer) error {
	if h.cotCoordinator == nil {
		return status.Error(codes.Unimplemented, "trace coordinator is not configured")
	}

	ack, err := h.cotCoordinator.ProcessStream(stream.Context(), traceStreamAdapter{stream})
	if err != nil {
		return status.Error(codes.Internal, err.Error())
	}

	return stream.SendAndClose(&ReasoningTraceAck{
		ExecutionId:    ack.ExecutionID,
		TotalReceived:  ack.TotalReceived,
		TotalPersisted: ack.TotalPersisted,
		TotalDropped:   ack.TotalDropped,
		FailedEventIds: ack.FailedEventIDs,
	})
}

func (h *Handler) CreateTreeBranch(ctx context.Context, req *CreateTreeBranchRequest) (*TreeBranchHandle, error) {
	if h.totManager == nil {
		return nil, status.Error(codes.Unimplemented, "tot manager is not configured")
	}
	handle, err := h.totManager.CreateBranch(ctx, req.GetTreeId(), req.GetBranchId(), req.GetHypothesis(), budget_tracker.BudgetAllocation{
		Tokens: req.GetBranchBudget().GetTokens(),
		Rounds: req.GetBranchBudget().GetRounds(),
		Cost:   req.GetBranchBudget().GetCost(),
		TimeMS: req.GetBranchBudget().GetTimeMs(),
	})
	if err != nil {
		switch {
		case errors.Is(err, tot_manager.ErrBranchExists):
			return nil, status.Error(codes.AlreadyExists, err.Error())
		case errors.Is(err, tot_manager.ErrConcurrencyLimit):
			return nil, status.Error(codes.ResourceExhausted, err.Error())
		default:
			return nil, status.Error(codes.Internal, err.Error())
		}
	}

	return &TreeBranchHandle{
		TreeId:    handle.TreeID,
		BranchId:  handle.BranchID,
		Status:    handle.Status,
		CreatedAt: timestamppb.New(handle.CreatedAt),
	}, nil
}

func (h *Handler) EvaluateTreeBranches(ctx context.Context, req *EvaluateTreeBranchesRequest) (*BranchSelectionResult, error) {
	if h.totManager == nil {
		return nil, status.Error(codes.Unimplemented, "tot manager is not configured")
	}
	result, err := h.totManager.EvaluateBranches(ctx, req.GetTreeId(), req.GetScoringFunction())
	if err != nil {
		if errors.Is(err, tot_manager.ErrTreeNotFound) {
			return nil, status.Error(codes.NotFound, err.Error())
		}
		return nil, status.Error(codes.Internal, err.Error())
	}

	summaries := make([]*BranchSummary, 0, len(result.AllBranches))
	for _, branch := range result.AllBranches {
		summaries = append(summaries, &BranchSummary{
			BranchId:     branch.BranchID,
			Hypothesis:   branch.Hypothesis,
			QualityScore: branch.QualityScore,
			TokenCost:    branch.TokenCost,
			Status:       branch.Status,
			Score:        branch.Score,
		})
	}

	return &BranchSelectionResult{
		SelectedBranchId:    result.SelectedBranchID,
		SelectedQuality:     result.SelectedQuality,
		SelectedTokenCost:   result.SelectedTokenCost,
		AllBranches:         summaries,
		NoViableBranches:    result.NoViableBranches,
		BestPartialBranchId: result.BestPartialBranchID,
	}, nil
}

func (h *Handler) StartSelfCorrectionLoop(ctx context.Context, req *StartSelfCorrectionRequest) (*SelfCorrectionHandle, error) {
	return h.startSelfCorrectionLoop(ctx, req)
}

func (h *Handler) SubmitCorrectionIteration(ctx context.Context, req *CorrectionIterationEvent) (*ConvergenceResult, error) {
	return h.submitCorrectionIteration(ctx, req)
}

func (h *Handler) GetReasoningTrace(
	ctx context.Context,
	req *GetReasoningTraceRequest,
) (*GetReasoningTraceResponse, error) {
	if req.GetExecutionId() == "" {
		return nil, status.Error(codes.InvalidArgument, "execution_id is required")
	}
	if h.traceStore == nil {
		return nil, status.Error(codes.Unimplemented, "trace store is not configured")
	}
	record, err := h.traceStore.GetTraceRecord(ctx, req.GetExecutionId(), req.GetStepId())
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, status.Error(codes.NotFound, "reasoning trace not found")
		}
		return nil, status.Error(codes.Internal, err.Error())
	}
	response := &GetReasoningTraceResponse{
		ExecutionId:            record.ExecutionID,
		Technique:              record.Technique,
		Status:                 record.Status,
		StorageKey:             record.StorageKey,
		StepCount:              int64(record.StepCount),
		ComputeBudgetUsed:      record.ComputeBudgetUsed,
		ComputeBudgetExhausted: record.ComputeBudgetExhausted,
	}
	if record.ConsensusReached != nil {
		response.ConsensusReached = *record.ConsensusReached
	}
	if record.Stabilized != nil {
		response.Stabilized = *record.Stabilized
	}
	if record.DegradationDetected != nil {
		response.DegradationDetected = *record.DegradationDetected
	}
	if record.Status != "complete" && !record.UpdatedAt.IsZero() {
		response.LastUpdatedAt = record.UpdatedAt.UTC().Format(time.RFC3339)
	}
	response.EffectiveBudgetScope = record.EffectiveBudgetScope
	return response, nil
}

type traceStreamAdapter struct {
	stream ReasoningEngineService_StreamReasoningTraceServer
}

func (a traceStreamAdapter) Context() context.Context {
	return a.stream.Context()
}

func (a traceStreamAdapter) Recv() (*cot_coordinator.TraceEvent, error) {
	event, err := a.stream.Recv()
	if err != nil {
		return nil, err
	}

	traceEvent := &cot_coordinator.TraceEvent{
		ExecutionID: event.GetExecutionId(),
		StepID:      event.GetStepId(),
		EventID:     event.GetEventId(),
		EventType:   event.GetEventType(),
		SequenceNum: event.GetSequenceNum(),
		Payload:     event.GetPayload(),
	}
	if event.GetOccurredAt() != nil {
		traceEvent.OccurredAt = event.GetOccurredAt().AsTime()
	}
	return traceEvent, nil
}

func envelopeFromBudgetStatus(statusValue *budget_tracker.BudgetStatus) *ReasoningBudgetEnvelope {
	return &ReasoningBudgetEnvelope{
		ExecutionId: statusValue.ExecutionID,
		StepId:      statusValue.StepID,
		Limits: &BudgetAllocation{
			Tokens: statusValue.Limits.Tokens,
			Rounds: statusValue.Limits.Rounds,
			Cost:   statusValue.Limits.Cost,
			TimeMs: statusValue.Limits.TimeMS,
		},
		Used: &BudgetAllocation{
			Tokens: statusValue.Used.Tokens,
			Rounds: statusValue.Used.Rounds,
			Cost:   statusValue.Used.Cost,
			TimeMs: statusValue.Used.TimeMS,
		},
		Status:      statusValue.Status,
		AllocatedAt: timestamppb.New(statusValue.AllocatedAt),
	}
}

func modeToProto(mode string) ReasoningMode {
	switch mode {
	case "DIRECT":
		return ReasoningMode_DIRECT
	case "CHAIN_OF_THOUGHT":
		return ReasoningMode_CHAIN_OF_THOUGHT
	case "TREE_OF_THOUGHT":
		return ReasoningMode_TREE_OF_THOUGHT
	case "REACT":
		return ReasoningMode_REACT
	case "CODE_AS_REASONING":
		return ReasoningMode_CODE_AS_REASONING
	case "DEBATE":
		return ReasoningMode_DEBATE
	case "SELF_CORRECTION":
		return ReasoningMode_SELF_CORRECTION
	default:
		return ReasoningMode_REASONING_MODE_UNSPECIFIED
	}
}

func convergenceToProto(value correction_loop.Status) ConvergenceStatus {
	switch value {
	case correction_loop.StatusContinue:
		return ConvergenceStatus_CONTINUE
	case correction_loop.StatusConverged:
		return ConvergenceStatus_CONVERGED
	case correction_loop.StatusBudgetExceeded:
		return ConvergenceStatus_BUDGET_EXCEEDED
	case correction_loop.StatusEscalateToHuman:
		return ConvergenceStatus_ESCALATE_TO_HUMAN
	default:
		return ConvergenceStatus_CONVERGENCE_STATUS_UNSPECIFIED
	}
}

func safeInt32(value int) int32 {
	if value > math.MaxInt32 {
		return math.MaxInt32
	}
	if value < math.MinInt32 {
		return math.MinInt32
	}
	return int32(value)
}

func mapComputeBudgetToAllocation(
	mode string,
	computeBudget float64,
	allocation mode_selector.BudgetAllocation,
) mode_selector.BudgetAllocation {
	if computeBudget <= 0 {
		return allocation
	}
	scaled := allocation
	switch mode {
	case "CHAIN_OF_THOUGHT", "DIRECT", "CODE_AS_REASONING":
		scaled.Tokens = scaleInt64(allocation.Tokens, computeBudget)
	case "TREE_OF_THOUGHT", "REACT", "DEBATE", "SELF_CORRECTION":
		scaled.Rounds = scaleInt64(allocation.Rounds, computeBudget)
	default:
		scaled.Tokens = scaleInt64(allocation.Tokens, computeBudget)
	}
	scaled.Cost = scaleFloat64(allocation.Cost, computeBudget)
	scaled.TimeMS = scaleInt64(allocation.TimeMS, computeBudget)
	return scaled
}

func scaleInt64(value int64, factor float64) int64 {
	if value <= 0 || factor <= 0 {
		return value
	}
	scaled := int64(math.Round(float64(value) * factor))
	if scaled < 1 {
		return 1
	}
	return scaled
}

func scaleFloat64(value float64, factor float64) float64 {
	if value <= 0 || factor <= 0 {
		return value
	}
	return value * factor
}
