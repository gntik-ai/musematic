package budget_tracker

import (
	"context"
	"errors"
	"time"
)

var (
	ErrAlreadyExists  = errors.New("budget already exists")
	ErrBudgetExceeded = errors.New("budget exceeded")
	ErrBudgetNotFound = errors.New("budget not found")
)

type BudgetAllocation struct {
	Tokens int64
	Rounds int64
	Cost   float64
	TimeMS int64
}

type BudgetStatus struct {
	ExecutionID string
	StepID      string
	Limits      BudgetAllocation
	Used        BudgetAllocation
	Status      string
	AllocatedAt time.Time
}

type BudgetTracker interface {
	Allocate(ctx context.Context, execID, stepID string, limits BudgetAllocation, ttlSecs int64) error
	Decrement(ctx context.Context, execID, stepID, dimension string, amount float64) (float64, error)
	GetStatus(ctx context.Context, execID, stepID string) (*BudgetStatus, error)
}

func Key(execID, stepID string) string {
	return execID + ":" + stepID
}
