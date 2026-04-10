package correction_loop

import (
	"context"
	"errors"
	"time"
)

var (
	ErrLoopExists     = errors.New("loop already exists")
	ErrLoopNotFound   = errors.New("loop not found")
	ErrLoopNotRunning = errors.New("loop is not running")
)

type Status string

const (
	StatusContinue        Status = "CONTINUE"
	StatusConverged       Status = "CONVERGED"
	StatusBudgetExceeded  Status = "BUDGET_EXCEEDED"
	StatusEscalateToHuman Status = "ESCALATE_TO_HUMAN"
)

type LoopConfig struct {
	MaxIterations            int
	CostCap                  float64
	Epsilon                  float64
	EscalateOnBudgetExceeded bool
}

type LoopHandle struct {
	LoopID      string
	ExecutionID string
	Status      string
	StartedAt   time.Time
}

type CorrectionLoop interface {
	Start(ctx context.Context, loopID, execID string, cfg LoopConfig) (*LoopHandle, error)
	Submit(ctx context.Context, loopID string, quality, cost float64, durationMs int64) (Status, int, float64, error)
}
