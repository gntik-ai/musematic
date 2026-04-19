package debate

import (
	"context"
	"errors"
	"testing"
	"time"
)

func TestCollectContributionsDefaultsAndMissedTurns(t *testing.T) {
	fixedNow := time.Date(2026, time.April, 19, 13, 0, 0, 0, time.UTC)

	t.Run("uses default timeout and provided clock", func(t *testing.T) {
		contributions := CollectContributions(
			context.Background(),
			[]string{"agent:a"},
			"synthesis",
			0,
			func(context.Context, string) (string, int64, error) {
				return "answer", 7, nil
			},
			func() time.Time { return fixedNow },
		)

		if len(contributions) != 1 {
			t.Fatalf("len(contributions) = %d, want 1", len(contributions))
		}
		if contributions[0].MissedTurn {
			t.Fatalf("expected completed turn, got %+v", contributions[0])
		}
		if contributions[0].Timestamp != fixedNow {
			t.Fatalf("timestamp = %v, want %v", contributions[0].Timestamp, fixedNow)
		}
		if contributions[0].TokensUsed != 7 || contributions[0].Content != "answer" {
			t.Fatalf("unexpected contribution = %+v", contributions[0])
		}
	})

	t.Run("marks provider errors and deadlines as missed turns", func(t *testing.T) {
		calls := 0
		contributions := CollectContributions(
			context.Background(),
			[]string{"agent:a", "agent:b"},
			"synthesis",
			time.Millisecond,
			func(ctx context.Context, _ string) (string, int64, error) {
				calls++
				if calls == 1 {
					return "ignored", 99, errors.New("boom")
				}
				<-ctx.Done()
				return "late", 5, ctx.Err()
			},
			func() time.Time { return fixedNow },
		)

		if len(contributions) != 2 {
			t.Fatalf("len(contributions) = %d, want 2", len(contributions))
		}
		for _, contribution := range contributions {
			if !contribution.MissedTurn {
				t.Fatalf("expected missed turn, got %+v", contribution)
			}
			if contribution.Content != "" || contribution.TokensUsed != 0 {
				t.Fatalf("missed turn should clear content and tokens: %+v", contribution)
			}
		}
	})
}
