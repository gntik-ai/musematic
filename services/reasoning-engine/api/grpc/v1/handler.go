package reasoningv1

import (
	"context"
	"errors"

	"github.com/musematic/reasoning-engine/internal/budget_tracker"
	"github.com/musematic/reasoning-engine/internal/correction_loop"
	"github.com/musematic/reasoning-engine/internal/cot_coordinator"
	"github.com/musematic/reasoning-engine/internal/mode_selector"
	"github.com/musematic/reasoning-engine/internal/tot_manager"
	"github.com/musematic/reasoning-engine/pkg/metrics"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"
)

type HandlerDependencies struct {
	ModeSelector   mode_selector.ModeSelector
	BudgetTracker  budget_tracker.BudgetTracker
	EventRegistry  *budget_tracker.EventRegistry
	CoTCoordinator cot_coordinator.CoTCoordinator
	ToTManager     tot_manager.ToTManager
	CorrectionLoop correction_loop.CorrectionLoop
	Metrics        *metrics.Metrics
}

type Handler struct {
	UnimplementedReasoningEngineServiceServer
	modeSelector   mode_selector.ModeSelector
	budgetTracker  budget_tracker.BudgetTracker
	eventRegistry  *budget_tracker.EventRegistry
	cotCoordinator cot_coordinator.CoTCoordinator
	totManager     tot_manager.ToTManager
	correctionLoop correction_loop.CorrectionLoop
	metrics        *metrics.Metrics
}

func NewHandler(deps HandlerDependencies) *Handler {
	return &Handler{
		modeSelector:   deps.ModeSelector,
		budgetTracker:  deps.BudgetTracker,
		eventRegistry:  deps.EventRegistry,
		cotCoordinator: deps.CoTCoordinator,
		totManager:     deps.ToTManager,
		correctionLoop: deps.CorrectionLoop,
		metrics:        deps.Metrics,
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

	h.metrics.RecordModeSelection(ctx, selection.Mode)
	return &ReasoningModeConfig{
		Mode:            modeToProto(selection.Mode),
		ComplexityScore: int32(selection.ComplexityScore),
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
	if !h.eventRegistry.Exists(key) {
		return status.Error(codes.NotFound, "budget not found")
	}

	ch := h.eventRegistry.Subscribe(key)
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
	if h.correctionLoop == nil {
		return nil, status.Error(codes.Unimplemented, "correction loop is not configured")
	}

	handle, err := h.correctionLoop.Start(ctx, req.GetLoopId(), req.GetExecutionId(), correction_loop.LoopConfig{
		MaxIterations:            int(req.GetMaxIterations()),
		CostCap:                  req.GetCostCap(),
		Epsilon:                  req.GetEpsilon(),
		EscalateOnBudgetExceeded: req.GetEscalateOnBudgetExceeded(),
	})
	if err != nil {
		switch {
		case errors.Is(err, correction_loop.ErrLoopExists):
			return nil, status.Error(codes.AlreadyExists, err.Error())
		default:
			return nil, status.Error(codes.InvalidArgument, err.Error())
		}
	}

	return &SelfCorrectionHandle{
		LoopId:    handle.LoopID,
		Status:    handle.Status,
		StartedAt: timestamppb.New(handle.StartedAt),
	}, nil
}

func (h *Handler) SubmitCorrectionIteration(ctx context.Context, req *CorrectionIterationEvent) (*ConvergenceResult, error) {
	if h.correctionLoop == nil {
		return nil, status.Error(codes.Unimplemented, "correction loop is not configured")
	}

	statusValue, iterationNum, delta, err := h.correctionLoop.Submit(ctx, req.GetLoopId(), req.GetQualityScore(), req.GetCost(), req.GetDurationMs())
	if err != nil {
		switch {
		case errors.Is(err, correction_loop.ErrLoopNotFound):
			return nil, status.Error(codes.NotFound, err.Error())
		case errors.Is(err, correction_loop.ErrLoopNotRunning):
			return nil, status.Error(codes.FailedPrecondition, err.Error())
		default:
			return nil, status.Error(codes.InvalidArgument, err.Error())
		}
	}

	h.metrics.RecordCorrectionIteration(ctx, string(statusValue))
	return &ConvergenceResult{
		Status:       convergenceToProto(statusValue),
		IterationNum: int32(iterationNum),
		Delta:        delta,
		LoopId:       req.GetLoopId(),
	}, nil
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
