package reasoningv1

import (
	"context"
	"fmt"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/musematic/reasoning-engine/internal/debate"
	"github.com/musematic/reasoning-engine/pkg/persistence"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"
)

type capturingTraceUploader struct {
	err      error
	uploads  []persistence.ConsolidatedTrace
	traceIDs []string
}

func (u *capturingTraceUploader) UploadTrace(
	_ context.Context,
	executionID string,
	traceType string,
	sessionID string,
	trace persistence.ConsolidatedTrace,
) (string, error) {
	if u.err != nil {
		return "", u.err
	}
	key := fmt.Sprintf("reasoning-traces/%s/%s/%s.json", executionID, traceType, sessionID)
	u.uploads = append(u.uploads, trace)
	u.traceIDs = append(u.traceIDs, key)
	return key, nil
}

type capturingTraceStore struct {
	err     error
	records []persistence.ReasoningTraceRecord
}

func (s *capturingTraceStore) InsertTraceRecord(_ context.Context, record persistence.ReasoningTraceRecord) error {
	if s.err != nil {
		return s.err
	}
	s.records = append(s.records, record)
	return nil
}

func (s *capturingTraceStore) GetTraceRecord(context.Context, string, string) (*persistence.ReasoningTraceRecord, error) {
	return nil, pgx.ErrNoRows
}

type capturingReasoningEvents struct {
	debatePayloads []map[string]any
	reactPayloads  []map[string]any
	debateDone     chan map[string]any
	reactDone      chan map[string]any
}

func (s *capturingReasoningEvents) ProduceDebateRoundCompleted(_ context.Context, _ string, payload map[string]any) error {
	copyPayload := cloneAnyMap(payload)
	s.debatePayloads = append(s.debatePayloads, copyPayload)
	if s.debateDone != nil {
		select {
		case s.debateDone <- copyPayload:
		default:
		}
	}
	return nil
}

func (s *capturingReasoningEvents) ProduceReactCycleCompleted(_ context.Context, _ string, payload map[string]any) error {
	copyPayload := cloneAnyMap(payload)
	s.reactPayloads = append(s.reactPayloads, copyPayload)
	if s.reactDone != nil {
		select {
		case s.reactDone <- copyPayload:
		default:
		}
	}
	return nil
}

func cloneAnyMap(payload map[string]any) map[string]any {
	copyPayload := make(map[string]any, len(payload))
	for key, value := range payload {
		copyPayload[key] = value
	}
	return copyPayload
}

func TestDebateRPCsReachConsensusAndPersistTrace(t *testing.T) {
	uploader := &capturingTraceUploader{}
	traceStore := &capturingTraceStore{}
	events := &capturingReasoningEvents{debateDone: make(chan map[string]any, 1)}
	handler := NewHandler(HandlerDependencies{
		DebateService:   debate.NewService(debate.NewConsensusDetector(nil, 0.05), uploader, traceStore, events),
		TraceStore:      traceStore,
		TraceUploader:   uploader,
		ReasoningEvents: events,
	})

	started, err := handler.StartDebateSession(context.Background(), &StartDebateSessionRequest{
		ExecutionId:      "exec-debate-1",
		DebateId:         "debate-1",
		ParticipantFqns:  []string{"agent.alpha", "agent.beta"},
		RoundLimit:       3,
		PerTurnTimeoutMs: 250,
	})
	if err != nil {
		t.Fatalf("StartDebateSession() error = %v", err)
	}
	if started.GetStatus() != "RUNNING" || started.GetCurrentRound() != 1 {
		t.Fatalf("unexpected session handle: %+v", started)
	}

	if _, err := handler.SubmitDebateTurn(context.Background(), &SubmitDebateTurnRequest{
		DebateId:   "debate-1",
		AgentFqn:   "agent.alpha",
		StepType:   "synthesis",
		Content:    "aligned answer for consensus",
		TokensUsed: 21,
		OccurredAt: timestamppb.New(time.Now().UTC()),
	}); err != nil {
		t.Fatalf("SubmitDebateTurn(first) error = %v", err)
	}

	round, err := handler.SubmitDebateTurn(context.Background(), &SubmitDebateTurnRequest{
		DebateId:     "debate-1",
		AgentFqn:     "agent.beta",
		StepType:     "synthesis",
		Content:      "shared answer for consensus",
		QualityScore: 0.92,
		TokensUsed:   18,
		OccurredAt:   timestamppb.New(time.Now().UTC()),
	})
	if err != nil {
		t.Fatalf("SubmitDebateTurn(second) error = %v", err)
	}
	if !round.GetDebateComplete() || round.GetConsensusStatus() != "consensus" || round.GetRoundNumber() != 1 {
		t.Fatalf("unexpected round result: %+v", round)
	}

	select {
	case payload := <-events.debateDone:
		if payload["terminated_by"] != "consensus" {
			t.Fatalf("round event termination = %#v, want consensus", payload["terminated_by"])
		}
		if payload["round_number"] != 1 {
			t.Fatalf("round number = %#v, want 1", payload["round_number"])
		}
	case <-time.After(time.Second):
		t.Fatal("timed out waiting for debate round event")
	}

	final, err := handler.FinalizeDebateSession(context.Background(), &FinalizeDebateSessionRequest{DebateId: "debate-1"})
	if err != nil {
		t.Fatalf("FinalizeDebateSession() error = %v", err)
	}
	if final.GetStatus() != "CONSENSUS" || !final.GetConsensusReached() || final.GetStorageKey() == "" {
		t.Fatalf("unexpected final debate result: %+v", final)
	}
	if len(uploader.uploads) != 1 || len(uploader.uploads[0].Steps) != 2 {
		t.Fatalf("unexpected uploaded trace: %+v", uploader.uploads)
	}
	if len(traceStore.records) != 1 {
		t.Fatalf("trace records = %d, want 1", len(traceStore.records))
	}
	if traceStore.records[0].ConsensusReached == nil || !*traceStore.records[0].ConsensusReached {
		t.Fatalf("trace record consensus = %+v", traceStore.records[0])
	}
}

func TestDebateRPCsHonorBudgetExhaustionAndValidateInputs(t *testing.T) {
	handler := NewHandler(HandlerDependencies{
		DebateService: debate.NewService(debate.NewConsensusDetector(nil, 0.05), &capturingTraceUploader{}, &capturingTraceStore{}, &capturingReasoningEvents{debateDone: make(chan map[string]any, 1)}),
	})

	if _, err := handler.StartDebateSession(context.Background(), &StartDebateSessionRequest{
		ExecutionId:     "exec-debate-invalid",
		DebateId:        "debate-invalid",
		ParticipantFqns: []string{"agent.alpha"},
		RoundLimit:      1,
	}); status.Code(err) != codes.InvalidArgument {
		t.Fatalf("single participant code = %s", status.Code(err))
	}
	if _, err := handler.StartDebateSession(context.Background(), &StartDebateSessionRequest{
		ExecutionId:     "exec-debate-invalid",
		DebateId:        "debate-invalid",
		ParticipantFqns: []string{"agent.alpha", "agent.beta"},
		RoundLimit:      1,
		ComputeBudget:   float64Ptr(0),
	}); status.Code(err) != codes.InvalidArgument {
		t.Fatalf("zero compute budget code = %s", status.Code(err))
	}

	uploader := &capturingTraceUploader{}
	traceStore := &capturingTraceStore{}
	events := &capturingReasoningEvents{debateDone: make(chan map[string]any, 1)}
	handler = NewHandler(HandlerDependencies{
		DebateService:   debate.NewService(debate.NewConsensusDetector(nil, 0.05), uploader, traceStore, events),
		TraceStore:      traceStore,
		TraceUploader:   uploader,
		ReasoningEvents: events,
	})
	if _, err := handler.StartDebateSession(context.Background(), &StartDebateSessionRequest{
		ExecutionId:     "exec-debate-2",
		DebateId:        "debate-2",
		ParticipantFqns: []string{"agent.alpha", "agent.beta"},
		RoundLimit:      2,
		ComputeBudget:   float64Ptr(0.5),
	}); err != nil {
		t.Fatalf("StartDebateSession(valid) error = %v", err)
	}
	if _, err := handler.SubmitDebateTurn(context.Background(), &SubmitDebateTurnRequest{
		DebateId:   "debate-2",
		AgentFqn:   "agent.alpha",
		StepType:   "synthesis",
		Content:    "short",
		TokensUsed: 10,
	}); err != nil {
		t.Fatalf("SubmitDebateTurn(first) error = %v", err)
	}
	round, err := handler.SubmitDebateTurn(context.Background(), &SubmitDebateTurnRequest{
		DebateId:   "debate-2",
		AgentFqn:   "agent.beta",
		StepType:   "synthesis",
		Content:    "this answer intentionally has many extra words to avoid consensus",
		TokensUsed: 30,
	})
	if err != nil {
		t.Fatalf("SubmitDebateTurn(second) error = %v", err)
	}
	if !round.GetDebateComplete() || !round.GetComputeBudgetExhausted() {
		t.Fatalf("unexpected budget round result: %+v", round)
	}
	select {
	case payload := <-events.debateDone:
		if payload["terminated_by"] != "compute_budget_exhausted" {
			t.Fatalf("terminated_by = %#v, want compute_budget_exhausted", payload["terminated_by"])
		}
	case <-time.After(time.Second):
		t.Fatal("timed out waiting for budget exhaustion event")
	}
	final, err := handler.FinalizeDebateSession(context.Background(), &FinalizeDebateSessionRequest{DebateId: "debate-2"})
	if err != nil {
		t.Fatalf("FinalizeDebateSession() error = %v", err)
	}
	if final.GetStatus() != "BUDGET_EXHAUSTED" || final.GetConsensusReached() {
		t.Fatalf("unexpected budget final result: %+v", final)
	}
}
