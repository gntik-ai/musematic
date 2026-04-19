package debate

import (
	"context"
	"errors"
	"testing"
	"time"
)

func TestCollectContributionsRecordsSuccessAndMissedTurns(t *testing.T) {
	now := time.Date(2026, time.April, 19, 10, 0, 0, 0, time.UTC)
	started := time.Now()
	contributions := CollectContributions(
		context.Background(),
		[]string{"agent:a", "agent:b"},
		"synthesis",
		10*time.Millisecond,
		func(ctx context.Context, agentFQN string) (string, int64, error) {
			switch agentFQN {
			case "agent:a":
				return "final answer", 13, nil
			case "agent:b":
				<-ctx.Done()
				return "late", 21, errors.New("timeout")
			default:
				return "", 0, nil
			}
		},
		func() time.Time { return now },
	)
	if len(contributions) != 2 {
		t.Fatalf("CollectContributions() len = %d, want 2", len(contributions))
	}
	if contributions[0].MissedTurn || contributions[0].Content != "final answer" || contributions[0].TokensUsed != 13 {
		t.Fatalf("first contribution = %+v", contributions[0])
	}
	if !contributions[1].MissedTurn || contributions[1].Content != "" || contributions[1].TokensUsed != 0 {
		t.Fatalf("second contribution = %+v", contributions[1])
	}
	if contributions[0].Timestamp != now || contributions[1].Timestamp != now {
		t.Fatalf("timestamps = %+v", contributions)
	}
	if time.Since(started) < 10*time.Millisecond {
		t.Fatal("expected timeout path to wait for per-turn timeout")
	}
}
