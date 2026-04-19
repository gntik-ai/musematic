package debate

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"time"

	"github.com/musematic/reasoning-engine/pkg/persistence"
)

type RoundEventProducer interface {
	ProduceDebateRoundCompleted(ctx context.Context, executionID string, payload map[string]any) error
}

type TraceUploader interface {
	UploadTrace(
		ctx context.Context,
		executionID string,
		traceType string,
		sessionID string,
		trace persistence.ConsolidatedTrace,
	) (string, error)
}

type TraceRecordWriter interface {
	InsertTraceRecord(ctx context.Context, record persistence.ReasoningTraceRecord) error
}

type DebateOrchestrator interface {
	Start(ctx context.Context, cfg DebateConfig) (*DebateSession, error)
	SubmitTurn(ctx context.Context, debateID string, agentFQN string, contribution RoundContribution) (*DebateSession, error)
	Finalize(ctx context.Context, debateID string) (*DebateSession, error)
}

type Service struct {
	detector   ConsensusDetector
	uploader   TraceUploader
	traceStore TraceRecordWriter
	producer   RoundEventProducer
	now        func() time.Time

	mu       sync.Mutex
	sessions map[string]*DebateSession
}

func NewService(
	detector ConsensusDetector,
	uploader TraceUploader,
	traceStore TraceRecordWriter,
	producer RoundEventProducer,
) *Service {
	if detector == nil {
		detector = NewConsensusDetector(nil, 0.05)
	}
	return &Service{
		detector:   detector,
		uploader:   uploader,
		traceStore: traceStore,
		producer:   producer,
		now:        func() time.Time { return time.Now().UTC() },
		sessions:   map[string]*DebateSession{},
	}
}

func (s *Service) Start(_ context.Context, cfg DebateConfig) (*DebateSession, error) {
	if len(cfg.Participants) < 2 {
		return nil, errors.New("debate requires at least two participants")
	}
	if cfg.RoundLimit < 1 {
		return nil, errors.New("round_limit must be at least 1")
	}
	if cfg.DebateID == "" || cfg.ExecutionID == "" {
		return nil, errors.New("execution_id and debate_id are required")
	}
	if cfg.PerTurnTimeout <= 0 {
		cfg.PerTurnTimeout = 5 * time.Second
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, exists := s.sessions[cfg.DebateID]; exists {
		return nil, fmt.Errorf("debate session %s already exists", cfg.DebateID)
	}
	session := &DebateSession{
		DebateID:       cfg.DebateID,
		ExecutionID:    cfg.ExecutionID,
		Participants:   append([]string(nil), cfg.Participants...),
		RoundLimit:     cfg.RoundLimit,
		PerTurnTimeout: cfg.PerTurnTimeout,
		CurrentRound:   1,
		Transcript: []DebateRound{{
			RoundNumber: 1,
		}},
		Status:        DebateRunning,
		ComputeBudget: cfg.ComputeBudget,
	}
	s.sessions[cfg.DebateID] = session
	return cloneSession(session), nil
}

func (s *Service) SubmitTurn(
	ctx context.Context,
	debateID string,
	agentFQN string,
	contribution RoundContribution,
) (*DebateSession, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	session, ok := s.sessions[debateID]
	if !ok {
		return nil, fmt.Errorf("debate session %s not found", debateID)
	}
	if session.Status != DebateRunning {
		return nil, fmt.Errorf("debate session %s is not running", debateID)
	}
	if !containsParticipant(session.Participants, agentFQN) {
		return nil, fmt.Errorf("participant %s is not part of debate", agentFQN)
	}
	if len(session.Transcript) == 0 {
		session.Transcript = append(session.Transcript, DebateRound{RoundNumber: 1})
	}
	if contribution.AgentFQN == "" {
		contribution.AgentFQN = agentFQN
	}
	if contribution.Timestamp.IsZero() {
		contribution.Timestamp = s.now()
	}
	current := &session.Transcript[len(session.Transcript)-1]
	current.Contributions = append(current.Contributions, contribution)
	if !roundComplete(*current, session.Participants) {
		return cloneSession(session), nil
	}
	consensus, err := s.detector.Detect(current.Contributions)
	if err != nil {
		return nil, err
	}
	current.CompletedAt = s.now()
	current.ConsensusStatus = "no_consensus"
	if consensus {
		current.ConsensusStatus = "consensus"
		session.ConsensusReached = true
		session.Status = DebateConsensus
	}
	session.BudgetUsed = float64(current.RoundNumber) / float64(session.RoundLimit)
	if session.ComputeBudget > 0 && session.BudgetUsed >= session.ComputeBudget {
		session.ComputeBudgetExhausted = true
		session.Status = DebateBudgetExhausted
		current.TerminationCause = "compute_budget_exhausted"
	} else if session.Status == DebateConsensus {
		current.TerminationCause = "consensus"
	} else if current.RoundNumber >= session.RoundLimit {
		session.Status = DebateRoundLimit
		current.TerminationCause = "round_limit"
	}
	s.emitRoundCompleted(ctx, session, *current)
	if session.Status == DebateRunning {
		session.CurrentRound++
		session.Transcript = append(session.Transcript, DebateRound{RoundNumber: session.CurrentRound})
	}
	return cloneSession(session), nil
}

func (s *Service) Finalize(ctx context.Context, debateID string) (*DebateSession, error) {
	s.mu.Lock()
	session, ok := s.sessions[debateID]
	if !ok {
		s.mu.Unlock()
		return nil, fmt.Errorf("debate session %s not found", debateID)
	}
	if session.Status == DebateRunning && len(session.Transcript) > 0 {
		current := &session.Transcript[len(session.Transcript)-1]
		if current.RoundNumber >= session.RoundLimit {
			session.Status = DebateRoundLimit
		}
	}
	final := cloneSession(session)
	delete(s.sessions, debateID)
	s.mu.Unlock()

	trace := buildTrace(final)
	if s.uploader != nil {
		storageKey, err := s.uploader.UploadTrace(ctx, final.ExecutionID, "DEBATE", final.DebateID, trace)
		if err != nil {
			return nil, err
		}
		final.StorageKey = storageKey
	}
	if s.traceStore != nil {
		status := "in_progress"
		if final.Status != DebateRunning {
			status = "complete"
		}
		if err := s.traceStore.InsertTraceRecord(ctx, persistence.ReasoningTraceRecord{
			ExecutionID:            final.ExecutionID,
			StepID:                 final.DebateID,
			Technique:              "DEBATE",
			StorageKey:             final.StorageKey,
			StepCount:              len(trace.Steps),
			Status:                 status,
			ComputeBudgetUsed:      final.BudgetUsed,
			ConsensusReached:       boolPtr(final.ConsensusReached),
			ComputeBudgetExhausted: final.ComputeBudgetExhausted,
		}); err != nil {
			return nil, err
		}
	}
	return final, nil
}

func (s *Service) emitRoundCompleted(ctx context.Context, session *DebateSession, round DebateRound) {
	if s.producer == nil {
		return
	}
	payload := map[string]any{
		"debate_id":             session.DebateID,
		"round_number":          round.RoundNumber,
		"participants":          append([]string(nil), session.Participants...),
		"consensus_status":      round.ConsensusStatus,
		"step_count_this_round": len(round.Contributions),
		"compute_budget_used":   session.BudgetUsed,
	}
	if round.TerminationCause != "" {
		payload["terminated_by"] = round.TerminationCause
	}
	// Best-effort emission: reasoning completion must not block on Kafka delivery.
	go func(payloadCopy map[string]any) {
		_ = s.producer.ProduceDebateRoundCompleted(ctx, session.ExecutionID, payloadCopy)
	}(payload)
}

func roundComplete(round DebateRound, participants []string) bool {
	count := 0
	for _, contribution := range round.Contributions {
		if contribution.StepType == "synthesis" {
			count++
		}
	}
	return count >= len(participants)
}

func buildTrace(session *DebateSession) persistence.ConsolidatedTrace {
	steps := make([]persistence.TraceStep, 0)
	stepNumber := 1
	var totalTokens int64
	for _, round := range session.Transcript {
		for _, contribution := range round.Contributions {
			steps = append(steps, persistence.TraceStep{
				StepNumber:   stepNumber,
				Type:         contribution.StepType,
				AgentFQN:     contribution.AgentFQN,
				Content:      contribution.Content,
				QualityScore: contribution.QualityScore,
				TokensUsed:   contribution.TokensUsed,
				Timestamp:    contribution.Timestamp.UTC().Format(time.RFC3339Nano),
			})
			totalTokens += contribution.TokensUsed
			stepNumber++
		}
	}
	status := "in_progress"
	if session.Status != DebateRunning {
		status = "complete"
	}
	return persistence.ConsolidatedTrace{
		ExecutionID:            session.ExecutionID,
		Technique:              "DEBATE",
		SchemaVersion:          "1.0",
		Status:                 status,
		Steps:                  steps,
		TotalTokens:            totalTokens,
		ComputeBudgetUsed:      session.BudgetUsed,
		ComputeBudgetExhausted: session.ComputeBudgetExhausted,
		ConsensusReached:       session.ConsensusReached,
		CreatedAt:              time.Now().UTC().Format(time.RFC3339Nano),
		LastUpdatedAt:          time.Now().UTC().Format(time.RFC3339Nano),
	}
}

func cloneSession(session *DebateSession) *DebateSession {
	copySession := *session
	copySession.Participants = append([]string(nil), session.Participants...)
	copySession.Transcript = make([]DebateRound, 0, len(session.Transcript))
	for _, round := range session.Transcript {
		copiedRound := round
		copiedRound.Contributions = append([]RoundContribution(nil), round.Contributions...)
		copySession.Transcript = append(copySession.Transcript, copiedRound)
	}
	return &copySession
}

func containsParticipant(participants []string, value string) bool {
	for _, participant := range participants {
		if participant == value {
			return true
		}
	}
	return false
}

func boolPtr(value bool) *bool {
	return &value
}
