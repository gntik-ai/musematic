package correction_loop

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"strconv"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/musematic/reasoning-engine/internal/escalation"
	"github.com/redis/go-redis/v9"
)

type Producer interface {
	Produce(ctx context.Context, topic, key string, value []byte) error
}

type LoopService struct {
	client   redis.Cmdable
	scripts  map[string]string
	producer Producer
	router   *escalation.Router
	pool     *pgxpool.Pool
	now      func() time.Time

	mu     sync.Mutex
	states map[string]*loopState
}

type loopState struct {
	LoopID          string
	ExecutionID     string
	Config          LoopConfig
	UsedIterations  int
	UsedCost        float64
	PrevQuality     float64
	PrevPrevQuality float64
	Status          string
	StartedAt       time.Time
}

func NewLoopService(client redis.Cmdable, scripts map[string]string, producer Producer, router *escalation.Router, pool *pgxpool.Pool) *LoopService {
	return &LoopService{
		client:   client,
		scripts:  scripts,
		producer: producer,
		router:   router,
		pool:     pool,
		now:      func() time.Time { return time.Now().UTC() },
		states:   map[string]*loopState{},
	}
}

func (s *LoopService) Start(ctx context.Context, loopID, execID string, cfg LoopConfig) (*LoopHandle, error) {
	if cfg.MaxIterations < 1 || cfg.CostCap <= 0 || cfg.Epsilon < 0 {
		return nil, fmt.Errorf("invalid loop configuration")
	}

	s.mu.Lock()
	defer s.mu.Unlock()
	if _, exists := s.states[loopID]; exists {
		return nil, ErrLoopExists
	}

	now := s.now()
	state := &loopState{
		LoopID:          loopID,
		ExecutionID:     execID,
		Config:          cfg,
		PrevQuality:     -1,
		PrevPrevQuality: -1,
		Status:          "RUNNING",
		StartedAt:       now,
	}
	s.states[loopID] = state

	if s.client != nil {
		values := map[string]any{
			"loop_id":           loopID,
			"execution_id":      execID,
			"max_iterations":    cfg.MaxIterations,
			"used_iterations":   0,
			"cost_cap":          cfg.CostCap,
			"max_cost":          cfg.CostCap,
			"used_cost":         0,
			"epsilon":           cfg.Epsilon,
			"prev_quality":      -1,
			"prev_prev_quality": -1,
			"status":            "RUNNING",
		}
		if err := s.client.HSet(ctx, redisKey(loopID), values).Err(); err != nil {
			return nil, err
		}
	}

	return &LoopHandle{
		LoopID:      loopID,
		ExecutionID: execID,
		Status:      "RUNNING",
		StartedAt:   now,
	}, nil
}

func (s *LoopService) Submit(ctx context.Context, loopID string, quality, cost float64, durationMs int64) (Status, int, float64, error) {
	if quality < 0 || quality > 1 {
		return "", 0, 0, fmt.Errorf("quality_score must be within [0,1]")
	}

	s.mu.Lock()
	state, ok := s.states[loopID]
	if !ok {
		s.mu.Unlock()
		return "", 0, 0, ErrLoopNotFound
	}
	if state.Status != "RUNNING" {
		s.mu.Unlock()
		return "", 0, 0, ErrLoopNotRunning
	}

	prevQuality := state.PrevQuality
	prevPrev := state.PrevPrevQuality
	delta := 0.0
	if prevQuality >= 0 {
		delta = math.Abs(quality - prevQuality)
	}

	state.PrevPrevQuality = prevQuality
	state.PrevQuality = quality
	state.UsedIterations++
	state.UsedCost += cost
	iterationNum := state.UsedIterations
	s.mu.Unlock()

	converged := false
	if s.client != nil && s.scripts["convergence_check"] != "" {
		result, err := s.client.EvalSha(ctx, s.scripts["convergence_check"], []string{redisKey(loopID)}, quality, state.Config.Epsilon).Result()
		if err != nil {
			return "", 0, 0, err
		}
		converged = parseEvalInt(result) == 1
	} else if state.Config.Epsilon > 0 && prevQuality >= 0 && prevPrev >= 0 {
		converged = math.Abs(quality-prevQuality) < state.Config.Epsilon && math.Abs(prevQuality-prevPrev) < state.Config.Epsilon
	}

	budgetExceeded := false
	if s.client != nil && s.scripts["budget_decrement"] != "" {
		iterationRes, err := s.client.EvalSha(ctx, s.scripts["budget_decrement"], []string{redisKey(loopID)}, "used_iterations", 1).Result()
		if err != nil {
			return "", 0, 0, err
		}
		costRes, err := s.client.EvalSha(ctx, s.scripts["budget_decrement"], []string{redisKey(loopID)}, "used_cost", cost).Result()
		if err != nil {
			return "", 0, 0, err
		}
		budgetExceeded = parseEvalFloat(iterationRes) < 0 || parseEvalFloat(costRes) < 0
	} else {
		budgetExceeded = state.UsedIterations >= state.Config.MaxIterations || state.UsedCost >= state.Config.CostCap
	}

	statusValue := StatusContinue
	if converged {
		statusValue = StatusConverged
	} else if budgetExceeded {
		if state.Config.EscalateOnBudgetExceeded {
			statusValue = StatusEscalateToHuman
		} else {
			statusValue = StatusBudgetExceeded
		}
	}

	s.mu.Lock()
	state.Status = string(statusValue)
	if statusValue == StatusContinue {
		state.Status = "RUNNING"
	}
	stateCopy := *state
	s.mu.Unlock()

	if s.client != nil {
		if err := s.client.HSet(ctx, redisKey(loopID), "status", stateCopy.Status).Err(); err != nil {
			return "", 0, 0, err
		}
	}

	if err := s.persistIteration(ctx, stateCopy, quality, delta, cost, durationMs); err != nil {
		return "", 0, 0, err
	}

	switch statusValue {
	case StatusConverged:
		_ = s.publishRuntimeEvent(ctx, "reasoning.loop_converged", stateCopy, quality)
	case StatusBudgetExceeded:
		_ = s.publishRuntimeEvent(ctx, "reasoning.loop_budget_exceeded", stateCopy, quality)
	case StatusEscalateToHuman:
		_ = s.publishRuntimeEvent(ctx, "reasoning.loop_budget_exceeded", stateCopy, quality)
		_ = s.router.Escalate(ctx, stateCopy.LoopID, stateCopy.ExecutionID, stateCopy.UsedIterations, stateCopy.UsedCost, quality)
	}

	return statusValue, iterationNum, delta, nil
}

func (s *LoopService) publishRuntimeEvent(ctx context.Context, eventType string, state loopState, quality float64) error {
	if s == nil || s.producer == nil {
		return nil
	}
	payload, err := json.Marshal(map[string]any{
		"event_type":   eventType,
		"version":      "1.0",
		"source":       "reasoning-engine",
		"execution_id": state.ExecutionID,
		"occurred_at":  s.now().Format(time.RFC3339Nano),
		"payload": map[string]any{
			"loop_id":         state.LoopID,
			"iterations_used": state.UsedIterations,
			"cost_used":       state.UsedCost,
			"last_quality":    quality,
		},
	})
	if err != nil {
		return err
	}
	return s.producer.Produce(ctx, "runtime.reasoning", state.ExecutionID, payload)
}

func (s *LoopService) persistIteration(ctx context.Context, state loopState, quality, delta, cost float64, durationMs int64) error {
	if s == nil || s.pool == nil {
		return nil
	}

	_, err := s.pool.Exec(ctx, `
INSERT INTO correction_iterations (id, loop_id, iteration_num, quality_score, delta, cost, duration_ms)
VALUES ($1, $2, $3, $4, $5, $6, $7)
ON CONFLICT (loop_id, iteration_num) DO NOTHING
`, uuid.New(), uuidFor(state.LoopID), state.UsedIterations, quality, nullableDelta(state.UsedIterations, delta), cost, durationMs)
	return err
}

func redisKey(loopID string) string {
	return "correction:" + loopID
}

func parseEvalInt(value any) int {
	switch typed := value.(type) {
	case int64:
		return int(typed)
	case string:
		parsed, _ := strconv.Atoi(typed)
		return parsed
	case float64:
		return int(typed)
	default:
		return 0
	}
}

func parseEvalFloat(value any) float64 {
	switch typed := value.(type) {
	case int64:
		return float64(typed)
	case string:
		parsed, _ := strconv.ParseFloat(typed, 64)
		return parsed
	case float64:
		return typed
	default:
		return 0
	}
}

func nullableDelta(iterationNum int, delta float64) any {
	if iterationNum <= 1 {
		return nil
	}
	return delta
}

func uuidFor(value string) uuid.UUID {
	if parsed, err := uuid.Parse(value); err == nil {
		return parsed
	}
	return uuid.NewMD5(uuid.Nil, []byte(value))
}
