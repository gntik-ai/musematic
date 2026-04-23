package debate

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/musematic/reasoning-engine/pkg/persistence"
)

type detectorStub struct {
	consensus bool
	err       error
}

func (s detectorStub) Detect([]RoundContribution) (bool, error) {
	return s.consensus, s.err
}

type uploaderStub struct {
	key   string
	err   error
	calls int
	trace persistence.ConsolidatedTrace
}

func (s *uploaderStub) UploadTrace(_ context.Context, executionID, traceType, sessionID string, trace persistence.ConsolidatedTrace) (string, error) {
	s.calls++
	s.trace = trace
	if s.err != nil {
		return "", s.err
	}
	if s.key != "" {
		return s.key, nil
	}
	return "reasoning-debates/" + executionID + "/" + sessionID + "/trace.json", nil
}

type traceStoreStub struct {
	err     error
	records []persistence.ReasoningTraceRecord
}

func (s *traceStoreStub) InsertTraceRecord(_ context.Context, record persistence.ReasoningTraceRecord) error {
	if s.err != nil {
		return s.err
	}
	s.records = append(s.records, record)
	return nil
}

type producerStub struct {
	calls    int
	payloads []map[string]any
	ch       chan struct{}
}

func (s *producerStub) ProduceDebateRoundCompleted(_ context.Context, _ string, payload map[string]any) error {
	s.calls++
	s.payloads = append(s.payloads, payload)
	if s.ch != nil {
		select {
		case s.ch <- struct{}{}:
		default:
		}
	}
	return nil
}

func fixedContribution(agent string, missed bool) RoundContribution {
	return RoundContribution{AgentFQN: agent, StepType: "synthesis", Content: "shared answer", TokensUsed: 7, MissedTurn: missed}
}

func waitForEmission(t *testing.T, ch <-chan struct{}) {
	t.Helper()
	select {
	case <-ch:
	case <-time.After(time.Second):
		t.Fatal("timed out waiting for debate event emission")
	}
}

func TestDebateServiceStartValidation(t *testing.T) {
	service := NewService(nil, nil, nil, nil)
	if _, err := service.Start(context.Background(), DebateConfig{ExecutionID: "exec", DebateID: "deb", Participants: []string{"only-one"}, RoundLimit: 1}); err == nil {
		t.Fatal("expected validation error for a single participant")
	}
	if _, err := service.Start(context.Background(), DebateConfig{ExecutionID: "exec", DebateID: "deb", Participants: []string{"a", "b"}, RoundLimit: 0}); err == nil {
		t.Fatal("expected validation error for round limit")
	}
}

//nolint:gocyclo // This test intentionally exercises the full happy-path debate lifecycle.
func TestDebateServiceConsensusFinalizePersistsTrace(t *testing.T) {
	uploader := &uploaderStub{key: "reasoning-debates/exec/debate-1/trace.json"}
	store := &traceStoreStub{}
	producer := &producerStub{ch: make(chan struct{}, 1)}
	service := NewService(detectorStub{consensus: true}, uploader, store, producer)
	service.now = func() time.Time { return time.Date(2026, time.April, 19, 12, 0, 0, 0, time.UTC) }

	session, err := service.Start(context.Background(), DebateConfig{
		ExecutionID:  "exec",
		DebateID:     "debate-1",
		Participants: []string{"agent:a", "agent:b"},
		RoundLimit:   3,
	})
	if err != nil {
		t.Fatalf("Start() error = %v", err)
	}
	if session.Status != DebateRunning || session.CurrentRound != 1 {
		t.Fatalf("session after start = %+v", session)
	}

	if _, err := service.SubmitTurn(context.Background(), "debate-1", "agent:a", fixedContribution("agent:a", false)); err != nil {
		t.Fatalf("SubmitTurn(agent:a) error = %v", err)
	}
	if _, err := service.SubmitTurn(context.Background(), "debate-1", "agent:b", fixedContribution("agent:b", false)); err != nil {
		t.Fatalf("SubmitTurn(agent:b) error = %v", err)
	}
	waitForEmission(t, producer.ch)

	final, err := service.Finalize(context.Background(), "debate-1")
	if err != nil {
		t.Fatalf("Finalize() error = %v", err)
	}
	if final.Status != DebateConsensus || !final.ConsensusReached {
		t.Fatalf("final session = %+v", final)
	}
	if final.StorageKey != uploader.key {
		t.Fatalf("storage key = %q, want %q", final.StorageKey, uploader.key)
	}
	if uploader.calls != 1 || len(uploader.trace.Steps) != 2 {
		t.Fatalf("uploader calls=%d trace=%+v", uploader.calls, uploader.trace)
	}
	if len(store.records) != 1 || store.records[0].Technique != "DEBATE" || store.records[0].ConsensusReached == nil || !*store.records[0].ConsensusReached {
		t.Fatalf("trace record = %+v", store.records)
	}
	if producer.calls != 1 || producer.payloads[0]["terminated_by"] != "consensus" {
		t.Fatalf("producer payloads = %+v", producer.payloads)
	}
}

//nolint:gocyclo // This test intentionally covers the main non-consensus termination scenarios.
func TestDebateServiceRoundLimitAndBudgetAndMissedTurn(t *testing.T) {
	t.Run("continues after missed turn", func(t *testing.T) {
		producer := &producerStub{ch: make(chan struct{}, 1)}
		service := NewService(detectorStub{consensus: false}, nil, nil, producer)
		_, err := service.Start(context.Background(), DebateConfig{ExecutionID: "exec", DebateID: "debate-missed", Participants: []string{"agent:a", "agent:b"}, RoundLimit: 2})
		if err != nil {
			t.Fatalf("Start() error = %v", err)
		}
		if _, err := service.SubmitTurn(context.Background(), "debate-missed", "agent:a", fixedContribution("agent:a", false)); err != nil {
			t.Fatalf("SubmitTurn(agent:a) error = %v", err)
		}
		if _, err := service.SubmitTurn(context.Background(), "debate-missed", "agent:b", fixedContribution("agent:b", true)); err != nil {
			t.Fatalf("SubmitTurn(agent:b) error = %v", err)
		}
		waitForEmission(t, producer.ch)
		session := service.sessions["debate-missed"]
		if session.Status != DebateRunning || session.CurrentRound != 2 || len(session.Transcript) != 2 {
			t.Fatalf("session = %+v", session)
		}
	})

	t.Run("terminates at round limit", func(t *testing.T) {
		producer := &producerStub{ch: make(chan struct{}, 1)}
		service := NewService(detectorStub{consensus: false}, nil, nil, producer)
		_, err := service.Start(context.Background(), DebateConfig{ExecutionID: "exec", DebateID: "debate-limit", Participants: []string{"agent:a", "agent:b"}, RoundLimit: 1})
		if err != nil {
			t.Fatalf("Start() error = %v", err)
		}
		_, _ = service.SubmitTurn(context.Background(), "debate-limit", "agent:a", fixedContribution("agent:a", false))
		_, _ = service.SubmitTurn(context.Background(), "debate-limit", "agent:b", fixedContribution("agent:b", false))
		waitForEmission(t, producer.ch)
		final, err := service.Finalize(context.Background(), "debate-limit")
		if err != nil {
			t.Fatalf("Finalize() error = %v", err)
		}
		if final.Status != DebateRoundLimit || final.ComputeBudgetExhausted {
			t.Fatalf("final = %+v", final)
		}
		if producer.payloads[0]["terminated_by"] != "round_limit" {
			t.Fatalf("payload = %+v", producer.payloads[0])
		}
	})

	t.Run("terminates on compute budget exhaustion", func(t *testing.T) {
		producer := &producerStub{ch: make(chan struct{}, 1)}
		service := NewService(detectorStub{consensus: false}, nil, nil, producer)
		_, err := service.Start(context.Background(), DebateConfig{ExecutionID: "exec", DebateID: "debate-budget", Participants: []string{"agent:a", "agent:b"}, RoundLimit: 5, ComputeBudget: 0.2})
		if err != nil {
			t.Fatalf("Start() error = %v", err)
		}
		_, _ = service.SubmitTurn(context.Background(), "debate-budget", "agent:a", fixedContribution("agent:a", false))
		_, _ = service.SubmitTurn(context.Background(), "debate-budget", "agent:b", fixedContribution("agent:b", false))
		waitForEmission(t, producer.ch)
		final, err := service.Finalize(context.Background(), "debate-budget")
		if err != nil {
			t.Fatalf("Finalize() error = %v", err)
		}
		if final.Status != DebateBudgetExhausted || !final.ComputeBudgetExhausted {
			t.Fatalf("final = %+v", final)
		}
		if producer.payloads[0]["terminated_by"] != "compute_budget_exhausted" {
			t.Fatalf("payload = %+v", producer.payloads[0])
		}
	})
}

func TestDebateServiceFinalizeErrors(t *testing.T) {
	service := NewService(detectorStub{}, &uploaderStub{err: errors.New("upload failed")}, nil, nil)
	if _, err := service.Finalize(context.Background(), "missing"); err == nil {
		t.Fatal("expected finalize error for missing session")
	}
	_, err := service.Start(context.Background(), DebateConfig{ExecutionID: "exec", DebateID: "debate-error", Participants: []string{"agent:a", "agent:b"}, RoundLimit: 1})
	if err != nil {
		t.Fatalf("Start() error = %v", err)
	}
	_, _ = service.SubmitTurn(context.Background(), "debate-error", "agent:a", fixedContribution("agent:a", false))
	_, _ = service.SubmitTurn(context.Background(), "debate-error", "agent:b", fixedContribution("agent:b", false))
	if _, err := service.Finalize(context.Background(), "debate-error"); err == nil || err.Error() != "upload failed" {
		t.Fatalf("Finalize() error = %v", err)
	}
}

func TestDebateServiceSubmitValidationAndDetectorErrors(t *testing.T) {
	t.Run("start and submit validation", func(t *testing.T) {
		service := NewService(detectorStub{}, nil, nil, nil)
		if _, err := service.Start(context.Background(), DebateConfig{ExecutionID: "exec", Participants: []string{"agent:a", "agent:b"}, RoundLimit: 1}); err == nil {
			t.Fatal("expected missing debate id validation error")
		}
		if _, err := service.Start(context.Background(), DebateConfig{ExecutionID: "exec", DebateID: "debate-validation", Participants: []string{"agent:a", "agent:b"}, RoundLimit: 1}); err != nil {
			t.Fatalf("Start() error = %v", err)
		}
		if _, err := service.Start(context.Background(), DebateConfig{ExecutionID: "exec", DebateID: "debate-validation", Participants: []string{"agent:a", "agent:b"}, RoundLimit: 1}); err == nil {
			t.Fatal("expected duplicate session error")
		}
		if _, err := service.SubmitTurn(context.Background(), "missing", "agent:a", fixedContribution("agent:a", false)); err == nil {
			t.Fatal("expected missing session error")
		}
		if _, err := service.SubmitTurn(context.Background(), "debate-validation", "outsider", fixedContribution("outsider", false)); err == nil {
			t.Fatal("expected outsider validation error")
		}
		if _, err := service.SubmitTurn(context.Background(), "debate-validation", "agent:a", fixedContribution("agent:a", false)); err != nil {
			t.Fatalf("SubmitTurn(agent:a) error = %v", err)
		}
		if _, err := service.SubmitTurn(context.Background(), "debate-validation", "agent:b", fixedContribution("agent:b", false)); err != nil {
			t.Fatalf("SubmitTurn(agent:b) error = %v", err)
		}
		if _, err := service.SubmitTurn(context.Background(), "debate-validation", "agent:a", fixedContribution("agent:a", false)); err == nil {
			t.Fatal("expected not-running error after debate termination")
		}
	})

	t.Run("detector errors propagate", func(t *testing.T) {
		service := NewService(detectorStub{err: errors.New("detect failed")}, nil, nil, nil)
		if _, err := service.Start(context.Background(), DebateConfig{ExecutionID: "exec", DebateID: "debate-detect", Participants: []string{"agent:a", "agent:b"}, RoundLimit: 1}); err != nil {
			t.Fatalf("Start() error = %v", err)
		}
		if _, err := service.SubmitTurn(context.Background(), "debate-detect", "agent:a", fixedContribution("agent:a", false)); err != nil {
			t.Fatalf("SubmitTurn(agent:a) error = %v", err)
		}
		if _, err := service.SubmitTurn(context.Background(), "debate-detect", "agent:b", fixedContribution("agent:b", false)); err == nil || err.Error() != "detect failed" {
			t.Fatalf("SubmitTurn(agent:b) error = %v", err)
		}
	})
}

func TestDebateServiceFinalizeAdditionalPaths(t *testing.T) {
	t.Run("running session at round limit finalizes as round limit", func(t *testing.T) {
		service := NewService(detectorStub{}, nil, nil, nil)
		if _, err := service.Start(context.Background(), DebateConfig{ExecutionID: "exec", DebateID: "debate-finalize-limit", Participants: []string{"agent:a", "agent:b"}, RoundLimit: 1}); err != nil {
			t.Fatalf("Start() error = %v", err)
		}
		final, err := service.Finalize(context.Background(), "debate-finalize-limit")
		if err != nil {
			t.Fatalf("Finalize() error = %v", err)
		}
		if final.Status != DebateRoundLimit || final.StorageKey != "" {
			t.Fatalf("final = %+v", final)
		}
	})

	t.Run("trace store errors propagate", func(t *testing.T) {
		uploader := &uploaderStub{}
		store := &traceStoreStub{err: errors.New("insert failed")}
		service := NewService(detectorStub{consensus: true}, uploader, store, nil)
		if _, err := service.Start(context.Background(), DebateConfig{ExecutionID: "exec", DebateID: "debate-store-error", Participants: []string{"agent:a", "agent:b"}, RoundLimit: 1}); err != nil {
			t.Fatalf("Start() error = %v", err)
		}
		if _, err := service.SubmitTurn(context.Background(), "debate-store-error", "agent:a", fixedContribution("agent:a", false)); err != nil {
			t.Fatalf("SubmitTurn(agent:a) error = %v", err)
		}
		if _, err := service.SubmitTurn(context.Background(), "debate-store-error", "agent:b", fixedContribution("agent:b", false)); err != nil {
			t.Fatalf("SubmitTurn(agent:b) error = %v", err)
		}
		if _, err := service.Finalize(context.Background(), "debate-store-error"); err == nil || err.Error() != "insert failed" {
			t.Fatalf("Finalize() error = %v", err)
		}
		if uploader.calls != 1 {
			t.Fatalf("uploader calls = %d, want 1", uploader.calls)
		}
	})
}
