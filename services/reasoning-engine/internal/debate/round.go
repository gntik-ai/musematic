package debate

import (
	"context"
	"errors"
	"time"
)

type DebateStatus string

const (
	DebateRunning         DebateStatus = "RUNNING"
	DebateConsensus       DebateStatus = "CONSENSUS"
	DebateRoundLimit      DebateStatus = "ROUND_LIMIT"
	DebateBudgetExhausted DebateStatus = "BUDGET_EXHAUSTED"
)

type DebateConfig struct {
	ExecutionID      string
	DebateID         string
	Participants     []string
	RoundLimit       int
	PerTurnTimeout   time.Duration
	ComputeBudget    float64
	ConsensusEpsilon float64
}

type DebateSession struct {
	DebateID               string
	ExecutionID            string
	Participants           []string
	RoundLimit             int
	PerTurnTimeout         time.Duration
	CurrentRound           int
	Transcript             []DebateRound
	Status                 DebateStatus
	ConsensusReached       bool
	ComputeBudget          float64
	BudgetUsed             float64
	ComputeBudgetExhausted bool
	StorageKey             string
}

type DebateRound struct {
	RoundNumber      int
	Contributions    []RoundContribution
	ConsensusStatus  string
	CompletedAt      time.Time
	TerminationCause string
}

type RoundContribution struct {
	AgentFQN     string
	StepType     string
	Content      string
	QualityScore float64
	TokensUsed   int64
	MissedTurn   bool
	Timestamp    time.Time
}

type ContributionProvider func(ctx context.Context, agentFQN string) (string, int64, error)

func CollectContributions(
	ctx context.Context,
	participants []string,
	stepType string,
	perTurnTimeout time.Duration,
	provider ContributionProvider,
	now func() time.Time,
) []RoundContribution {
	clock := now
	if clock == nil {
		clock = func() time.Time { return time.Now().UTC() }
	}
	if perTurnTimeout <= 0 {
		perTurnTimeout = time.Second
	}
	contributions := make([]RoundContribution, 0, len(participants))
	for _, participant := range participants {
		turnCtx, cancel := context.WithTimeout(ctx, perTurnTimeout)
		content, tokensUsed, err := provider(turnCtx, participant)
		deadlineErr := turnCtx.Err()
		cancel()
		contribution := RoundContribution{
			AgentFQN:   participant,
			StepType:   stepType,
			Content:    content,
			TokensUsed: tokensUsed,
			Timestamp:  clock(),
		}
		if err != nil || errors.Is(deadlineErr, context.DeadlineExceeded) {
			contribution.Content = ""
			contribution.TokensUsed = 0
			contribution.MissedTurn = true
		}
		contributions = append(contributions, contribution)
	}
	return contributions
}
