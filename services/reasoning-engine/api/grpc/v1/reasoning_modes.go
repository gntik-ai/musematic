package reasoningv1

import (
	"context"
	"errors"
	"strings"
	"time"

	"github.com/musematic/reasoning-engine/internal/correction_loop"
	"github.com/musematic/reasoning-engine/internal/debate"
	"github.com/musematic/reasoning-engine/pkg/persistence"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"
)

type traceUploader interface {
	UploadTrace(
		ctx context.Context,
		executionID string,
		traceType string,
		sessionID string,
		trace persistence.ConsolidatedTrace,
	) (string, error)
}

type reasoningEventProducer interface {
	ProduceDebateRoundCompleted(ctx context.Context, executionID string, payload map[string]any) error
	ProduceReactCycleCompleted(ctx context.Context, executionID string, payload map[string]any) error
}

type selfCorrectionIteration struct {
	IterationNum  int
	PriorAnswer   string
	Critique      string
	RefinedAnswer string
	QualityScore  float64
	Cost          float64
	DurationMS    int64
	OccurredAt    time.Time
}

type selfCorrectionSession struct {
	LoopID                   string
	ExecutionID              string
	StepID                   string
	Status                   string
	StartedAt                time.Time
	UpdatedAt                time.Time
	MaxIterations            int
	ComputeBudget            float64
	DegradationThreshold     float64
	EscalateOnBudgetExceeded bool
	ComputeBudgetUsed        float64
	ComputeBudgetExhausted   bool
	Stabilized               bool
	DegradationDetected      bool
	BestQuality              float64
	BestAnswer               string
	Iterations               []selfCorrectionIteration
}

func (h *Handler) StartDebateSession(
	ctx context.Context,
	req *StartDebateSessionRequest,
) (*DebateSessionHandle, error) {
	if h.debateService == nil {
		return nil, status.Error(codes.Unimplemented, "debate service is not configured")
	}
	if req.GetExecutionId() == "" || req.GetDebateId() == "" {
		return nil, status.Error(codes.InvalidArgument, "execution_id and debate_id are required")
	}
	if len(req.GetParticipantFqns()) < 2 {
		return nil, status.Error(codes.InvalidArgument, "debate requires at least two participants")
	}
	if req.GetRoundLimit() < 1 {
		return nil, status.Error(codes.InvalidArgument, "round_limit must be at least 1")
	}
	if req.ComputeBudget != nil && !isValidComputeBudget(req.GetComputeBudget()) {
		return nil, status.Error(codes.InvalidArgument, "compute_budget must be within (0,1]")
	}

	session, err := h.debateService.Start(ctx, debate.DebateConfig{
		ExecutionID:      req.GetExecutionId(),
		DebateID:         req.GetDebateId(),
		Participants:     append([]string(nil), req.GetParticipantFqns()...),
		RoundLimit:       int(req.GetRoundLimit()),
		PerTurnTimeout:   durationOrZero(req.GetPerTurnTimeoutMs()),
		ComputeBudget:    optionalFloat64(req.ComputeBudget),
		ConsensusEpsilon: req.GetConsensusEpsilon(),
	})
	if err != nil {
		return nil, mapDebateError(err)
	}
	return &DebateSessionHandle{
		ExecutionId:  session.ExecutionID,
		DebateId:     session.DebateID,
		Status:       string(session.Status),
		CurrentRound: safeInt32(session.CurrentRound),
	}, nil
}

func (h *Handler) SubmitDebateTurn(
	ctx context.Context,
	req *SubmitDebateTurnRequest,
) (*DebateRoundResult, error) {
	if h.debateService == nil {
		return nil, status.Error(codes.Unimplemented, "debate service is not configured")
	}
	if req.GetDebateId() == "" || req.GetAgentFqn() == "" {
		return nil, status.Error(codes.InvalidArgument, "debate_id and agent_fqn are required")
	}

	session, err := h.debateService.SubmitTurn(ctx, req.GetDebateId(), req.GetAgentFqn(), debate.RoundContribution{
		AgentFQN:     req.GetAgentFqn(),
		StepType:     req.GetStepType(),
		Content:      req.GetContent(),
		QualityScore: req.GetQualityScore(),
		TokensUsed:   req.GetTokensUsed(),
		Timestamp:    timestampOrZero(req.GetOccurredAt()),
	})
	if err != nil {
		return nil, mapDebateError(err)
	}

	roundNumber, consensusStatus := latestDebateRound(session)
	return &DebateRoundResult{
		DebateId:               req.GetDebateId(),
		RoundNumber:            safeInt32(roundNumber),
		ConsensusStatus:        consensusStatus,
		DebateComplete:         session.Status != debate.DebateRunning,
		ComputeBudgetUsed:      session.BudgetUsed,
		ComputeBudgetExhausted: session.ComputeBudgetExhausted,
	}, nil
}

func (h *Handler) FinalizeDebateSession(
	ctx context.Context,
	req *FinalizeDebateSessionRequest,
) (*DebateSessionResult, error) {
	if h.debateService == nil {
		return nil, status.Error(codes.Unimplemented, "debate service is not configured")
	}
	if req.GetDebateId() == "" {
		return nil, status.Error(codes.InvalidArgument, "debate_id is required")
	}

	session, err := h.debateService.Finalize(ctx, req.GetDebateId())
	if err != nil {
		return nil, mapDebateError(err)
	}
	return &DebateSessionResult{
		ExecutionId:            session.ExecutionID,
		DebateId:               session.DebateID,
		Status:                 string(session.Status),
		ConsensusReached:       session.ConsensusReached,
		ComputeBudgetUsed:      session.BudgetUsed,
		ComputeBudgetExhausted: session.ComputeBudgetExhausted,
		StorageKey:             session.StorageKey,
	}, nil
}

func (h *Handler) startSelfCorrectionLoop(
	ctx context.Context,
	req *StartSelfCorrectionRequest,
) (*SelfCorrectionHandle, error) {
	if h.correctionLoop == nil {
		return nil, status.Error(codes.Unimplemented, "correction loop is not configured")
	}
	if req.GetLoopId() == "" || req.GetExecutionId() == "" {
		return nil, status.Error(codes.InvalidArgument, "loop_id and execution_id are required")
	}
	if req.GetMaxIterations() < 1 || req.GetCostCap() <= 0 || req.GetEpsilon() < 0 || req.GetDegradationThreshold() < 0 {
		return nil, status.Error(codes.InvalidArgument, "invalid self-correction configuration")
	}
	if req.ComputeBudget != nil && !isValidComputeBudget(req.GetComputeBudget()) {
		return nil, status.Error(codes.InvalidArgument, "compute_budget must be within (0,1]")
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

	startedAt := handle.StartedAt
	if startedAt.IsZero() {
		startedAt = time.Now().UTC()
	}
	session := &selfCorrectionSession{
		LoopID:                   req.GetLoopId(),
		ExecutionID:              req.GetExecutionId(),
		StepID:                   normalizeStepID(req.GetStepId(), req.GetLoopId()),
		Status:                   handle.Status,
		StartedAt:                startedAt,
		UpdatedAt:                startedAt,
		MaxIterations:            int(req.GetMaxIterations()),
		ComputeBudget:            optionalFloat64(req.ComputeBudget),
		DegradationThreshold:     req.GetDegradationThreshold(),
		EscalateOnBudgetExceeded: req.GetEscalateOnBudgetExceeded(),
		BestQuality:              -1,
	}

	h.selfCorrectionMu.Lock()
	h.selfCorrectionSessions[req.GetLoopId()] = session
	h.selfCorrectionMu.Unlock()

	return &SelfCorrectionHandle{
		LoopId:    handle.LoopID,
		Status:    handle.Status,
		StartedAt: timestamppb.New(startedAt),
	}, nil
}

func (h *Handler) submitCorrectionIteration(
	ctx context.Context,
	req *CorrectionIterationEvent,
) (*ConvergenceResult, error) {
	if err := validateCorrectionIterationRequest(h.correctionLoop, req); err != nil {
		return nil, err
	}
	if _, err := h.requireSelfCorrectionSession(req.GetLoopId()); err != nil {
		return nil, err
	}

	statusValue, iterationNum, delta, err := h.submitCorrectionIterationState(ctx, req)
	if err != nil {
		return nil, err
	}

	return &ConvergenceResult{
		Status:       convergenceToProto(statusValue),
		IterationNum: safeInt32(iterationNum),
		Delta:        delta,
		LoopId:       req.GetLoopId(),
	}, nil
}

func validateCorrectionIterationRequest(
	loop correction_loop.CorrectionLoop,
	req *CorrectionIterationEvent,
) error {
	if loop == nil {
		return status.Error(codes.Unimplemented, "correction loop is not configured")
	}
	if req.GetLoopId() == "" {
		return status.Error(codes.InvalidArgument, "loop_id is required")
	}
	return nil
}

func (h *Handler) requireSelfCorrectionSession(loopID string) (*selfCorrectionSession, error) {
	h.selfCorrectionMu.Lock()
	defer h.selfCorrectionMu.Unlock()
	session := h.selfCorrectionSessions[loopID]
	if session == nil {
		return nil, status.Error(codes.NotFound, correction_loop.ErrLoopNotFound.Error())
	}
	return session, nil
}

func (h *Handler) submitCorrectionIterationState(
	ctx context.Context,
	req *CorrectionIterationEvent,
) (correction_loop.Status, int, float64, error) {
	statusValue, iterationNum, delta, err := h.correctionLoop.Submit(
		ctx,
		req.GetLoopId(),
		req.GetQualityScore(),
		req.GetCost(),
		req.GetDurationMs(),
	)
	if err != nil {
		return "", 0, 0, mapCorrectionIterationError(err)
	}
	if req.GetIterationNum() > 0 {
		iterationNum = int(req.GetIterationNum())
	}

	snapshot, terminal, statusValue, delta, err := h.updateSelfCorrectionSession(req, statusValue, iterationNum, delta)
	if err != nil {
		return "", 0, 0, err
	}
	if terminal {
		if err := h.persistSelfCorrectionTrace(ctx, snapshot); err != nil {
			return "", 0, 0, status.Error(codes.Internal, err.Error())
		}
	}
	return statusValue, iterationNum, delta, nil
}

func mapCorrectionIterationError(err error) error {
	switch {
	case errors.Is(err, correction_loop.ErrLoopNotFound):
		return status.Error(codes.NotFound, err.Error())
	case errors.Is(err, correction_loop.ErrLoopNotRunning):
		return status.Error(codes.FailedPrecondition, err.Error())
	default:
		return status.Error(codes.Internal, err.Error())
	}
}

func (h *Handler) updateSelfCorrectionSession(
	req *CorrectionIterationEvent,
	statusValue correction_loop.Status,
	iterationNum int,
	delta float64,
) (*selfCorrectionSession, bool, correction_loop.Status, float64, error) {
	now := time.Now().UTC()
	h.selfCorrectionMu.Lock()
	defer h.selfCorrectionMu.Unlock()
	session := h.selfCorrectionSessions[req.GetLoopId()]
	if session == nil {
		return nil, false, "", 0, status.Error(codes.NotFound, correction_loop.ErrLoopNotFound.Error())
	}

	recordCorrectionIteration(session, req, iterationNum, now)
	statusValue, delta = applyCorrectionOutcome(session, req, statusValue, delta)
	if statusValue == correction_loop.StatusContinue {
		session.Status = "RUNNING"
		return nil, false, statusValue, delta, nil
	}
	session.Status = string(statusValue)
	snapshot := cloneSelfCorrectionSession(session)
	delete(h.selfCorrectionSessions, req.GetLoopId())
	return snapshot, true, statusValue, delta, nil
}

func recordCorrectionIteration(
	session *selfCorrectionSession,
	req *CorrectionIterationEvent,
	iterationNum int,
	now time.Time,
) {
	session.UpdatedAt = now
	session.Iterations = append(session.Iterations, selfCorrectionIteration{
		IterationNum:  iterationNum,
		PriorAnswer:   req.GetPriorAnswer(),
		Critique:      req.GetCritique(),
		RefinedAnswer: req.GetRefinedAnswer(),
		QualityScore:  req.GetQualityScore(),
		Cost:          req.GetCost(),
		DurationMS:    req.GetDurationMs(),
		OccurredAt:    now,
	})
	if req.GetQualityScore() > session.BestQuality {
		session.BestQuality = req.GetQualityScore()
		session.BestAnswer = bestCorrectionAnswer(req)
	}
	if session.MaxIterations > 0 {
		session.ComputeBudgetUsed = float64(iterationNum) / float64(session.MaxIterations)
	}
}

func bestCorrectionAnswer(req *CorrectionIterationEvent) string {
	if req.GetRefinedAnswer() != "" {
		return req.GetRefinedAnswer()
	}
	return req.GetPriorAnswer()
}

func applyCorrectionOutcome(
	session *selfCorrectionSession,
	req *CorrectionIterationEvent,
	statusValue correction_loop.Status,
	delta float64,
) (correction_loop.Status, float64) {
	if isCorrectionDegraded(session, req) {
		session.DegradationDetected = true
		if statusValue == correction_loop.StatusContinue {
			statusValue = correction_loop.StatusConverged
			delta = 0
		}
	}
	if session.ComputeBudget > 0 && session.ComputeBudgetUsed >= session.ComputeBudget {
		session.ComputeBudgetExhausted = true
		if statusValue == correction_loop.StatusContinue {
			statusValue = correction_loop.StatusBudgetExceeded
		}
	}
	if statusValue == correction_loop.StatusConverged && !session.DegradationDetected {
		session.Stabilized = true
	}
	return statusValue, delta
}

func isCorrectionDegraded(session *selfCorrectionSession, req *CorrectionIterationEvent) bool {
	return session.DegradationThreshold > 0 &&
		session.BestQuality >= 0 &&
		req.GetQualityScore() < session.BestQuality-session.DegradationThreshold
}

func (h *Handler) persistSelfCorrectionTrace(ctx context.Context, session *selfCorrectionSession) error {
	if session == nil {
		return nil
	}
	trace := buildSelfCorrectionTrace(session)
	storageKey := ""
	if h.traceUploader != nil {
		key, err := h.traceUploader.UploadTrace(ctx, session.ExecutionID, "SELF_CORRECTION", session.StepID, trace)
		if err != nil {
			return err
		}
		storageKey = key
	}
	if h.traceStore != nil {
		if err := h.traceStore.InsertTraceRecord(ctx, persistence.ReasoningTraceRecord{
			ExecutionID:            session.ExecutionID,
			StepID:                 session.StepID,
			Technique:              "SELF_CORRECTION",
			StorageKey:             storageKey,
			StepCount:              len(trace.Steps),
			Status:                 trace.Status,
			ComputeBudgetUsed:      session.ComputeBudgetUsed,
			Stabilized:             boolPtr(session.Stabilized),
			DegradationDetected:    boolPtr(session.DegradationDetected),
			ComputeBudgetExhausted: session.ComputeBudgetExhausted,
		}); err != nil {
			return err
		}
	}
	return nil
}

func buildSelfCorrectionTrace(session *selfCorrectionSession) persistence.ConsolidatedTrace {
	steps := make([]persistence.TraceStep, 0, len(session.Iterations)*3)
	stepNumber := 1
	for _, iteration := range session.Iterations {
		timestamp := iteration.OccurredAt.UTC().Format(time.RFC3339Nano)
		steps = append(steps,
			persistence.TraceStep{
				StepNumber: stepNumber,
				Type:       "iteration_input",
				Content:    iteration.PriorAnswer,
				Timestamp:  timestamp,
			},
			persistence.TraceStep{
				StepNumber:   stepNumber + 1,
				Type:         "iteration_critique",
				Content:      iteration.Critique,
				QualityScore: iteration.QualityScore,
				Timestamp:    timestamp,
			},
			persistence.TraceStep{
				StepNumber:   stepNumber + 2,
				Type:         "iteration_output",
				Content:      iteration.RefinedAnswer,
				QualityScore: iteration.QualityScore,
				Timestamp:    timestamp,
			},
		)
		stepNumber += 3
	}
	return persistence.ConsolidatedTrace{
		ExecutionID:            session.ExecutionID,
		Technique:              "SELF_CORRECTION",
		SchemaVersion:          "1.0",
		Status:                 "complete",
		Steps:                  steps,
		TotalTokens:            0,
		ComputeBudgetUsed:      session.ComputeBudgetUsed,
		ComputeBudgetExhausted: session.ComputeBudgetExhausted,
		Stabilized:             session.Stabilized,
		DegradationDetected:    session.DegradationDetected,
		CreatedAt:              session.StartedAt.UTC().Format(time.RFC3339Nano),
		LastUpdatedAt:          session.UpdatedAt.UTC().Format(time.RFC3339Nano),
	}
}

func latestDebateRound(session *debate.DebateSession) (int, string) {
	if session == nil || len(session.Transcript) == 0 {
		return 0, "pending"
	}
	last := session.Transcript[len(session.Transcript)-1]
	if !last.CompletedAt.IsZero() {
		return last.RoundNumber, last.ConsensusStatus
	}
	if len(session.Transcript) > 1 {
		prev := session.Transcript[len(session.Transcript)-2]
		if !prev.CompletedAt.IsZero() {
			return prev.RoundNumber, prev.ConsensusStatus
		}
	}
	return last.RoundNumber, "pending"
}

func timestampOrZero(value *timestamppb.Timestamp) time.Time {
	if value == nil {
		return time.Time{}
	}
	return value.AsTime()
}

func durationOrZero(value int64) time.Duration {
	if value <= 0 {
		return 0
	}
	return time.Duration(value) * time.Millisecond
}

func optionalFloat64(value *float64) float64 {
	if value == nil {
		return 0
	}
	return *value
}

func normalizeStepID(stepID string, fallback string) string {
	if stepID != "" {
		return stepID
	}
	return fallback
}

func isValidComputeBudget(value float64) bool {
	return value > 0 && value <= 1
}

func cloneSelfCorrectionSession(session *selfCorrectionSession) *selfCorrectionSession {
	if session == nil {
		return nil
	}
	copySession := *session
	copySession.Iterations = append([]selfCorrectionIteration(nil), session.Iterations...)
	return &copySession
}

func boolPtr(value bool) *bool {
	return &value
}

func mapDebateError(err error) error {
	if err == nil {
		return nil
	}
	message := err.Error()
	switch {
	case strings.Contains(message, "already exists"):
		return status.Error(codes.AlreadyExists, message)
	case strings.Contains(message, "not found"):
		return status.Error(codes.NotFound, message)
	case strings.Contains(message, "not running"):
		return status.Error(codes.FailedPrecondition, message)
	case strings.Contains(message, "not part of debate"):
		return status.Error(codes.InvalidArgument, message)
	case strings.Contains(message, "requires at least two participants"), strings.Contains(message, "round_limit must be at least 1"), strings.Contains(message, "execution_id and debate_id are required"):
		return status.Error(codes.InvalidArgument, message)
	default:
		return status.Error(codes.Internal, message)
	}
}
