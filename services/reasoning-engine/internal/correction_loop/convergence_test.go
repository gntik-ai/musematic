package correction_loop

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/musematic/reasoning-engine/internal/escalation"
)

type recordingProducer struct {
	topics []string
	err    error
}

func (p *recordingProducer) Produce(_ context.Context, topic, _ string, _ []byte) error {
	if p.err != nil {
		return p.err
	}
	p.topics = append(p.topics, topic)
	return nil
}

type scriptedRedisClient struct {
	hsetErr    error
	evalErr    error
	evalResult []any
	hashes     map[string]map[string]any
}

func newScriptedRedisClient() *scriptedRedisClient {
	return &scriptedRedisClient{hashes: map[string]map[string]any{}}
}

func (c *scriptedRedisClient) HSet(_ context.Context, key string, values ...any) error {
	if c.hsetErr != nil {
		return c.hsetErr
	}
	if _, ok := c.hashes[key]; !ok {
		c.hashes[key] = map[string]any{}
	}
	if len(values) == 1 {
		if mapped, ok := values[0].(map[string]any); ok {
			for field, value := range mapped {
				c.hashes[key][field] = value
			}
			return nil
		}
	}
	for index := 0; index < len(values); index += 2 {
		c.hashes[key][values[index].(string)] = values[index+1]
	}
	return nil
}

func (c *scriptedRedisClient) EvalSha(_ context.Context, _ string, _ []string, _ ...any) (any, error) {
	if c.evalErr != nil {
		return nil, c.evalErr
	}
	if len(c.evalResult) == 0 {
		return nil, nil
	}
	result := c.evalResult[0]
	c.evalResult = c.evalResult[1:]
	return result, nil
}

type fakeIterationStore struct {
	err  error
	sql  string
	args []any
}

func (s *fakeIterationStore) Exec(_ context.Context, sql string, arguments ...any) (pgconn.CommandTag, error) {
	s.sql = sql
	s.args = arguments
	return pgconn.NewCommandTag("INSERT 0 1"), s.err
}

func TestLoopServiceConvergesAtIterationSix(t *testing.T) {
	producer := &recordingProducer{}
	service := NewLoopService(nil, nil, producer, escalation.NewRouter(producer), nil)
	if _, err := service.Start(context.Background(), "loop-1", "exec-1", LoopConfig{
		MaxIterations: 10,
		CostCap:       5,
		Epsilon:       0.01,
	}); err != nil {
		t.Fatalf("Start() error = %v", err)
	}

	scores := []float64{0.5, 0.7, 0.78, 0.80, 0.805, 0.808}
	var (
		statusValue Status
		iteration   int
		err         error
	)
	for _, score := range scores {
		statusValue, iteration, _, err = service.Submit(context.Background(), "loop-1", score, 0.1, 500)
		if err != nil {
			t.Fatalf("Submit() error = %v", err)
		}
	}
	if statusValue != StatusConverged || iteration != 6 {
		t.Fatalf("status = %s iteration = %d, want %s/6", statusValue, iteration, StatusConverged)
	}
}

func TestLoopServiceBudgetExceededAndEscalation(t *testing.T) {
	producer := &recordingProducer{}
	service := NewLoopService(nil, nil, producer, escalation.NewRouter(producer), nil)
	if _, err := service.Start(context.Background(), "loop-2", "exec-2", LoopConfig{
		MaxIterations:            3,
		CostCap:                  100,
		Epsilon:                  0.0001,
		EscalateOnBudgetExceeded: true,
	}); err != nil {
		t.Fatalf("Start() error = %v", err)
	}

	statusValue := StatusContinue
	for _, score := range []float64{0.5, 0.7, 0.9} {
		var err error
		statusValue, _, _, err = service.Submit(context.Background(), "loop-2", score, 0.1, 100)
		if err != nil {
			t.Fatalf("Submit() error = %v", err)
		}
	}

	if statusValue != StatusEscalateToHuman {
		t.Fatalf("status = %s, want %s", statusValue, StatusEscalateToHuman)
	}
	if len(producer.topics) < 2 {
		t.Fatalf("expected runtime and escalation events, got %+v", producer.topics)
	}
}

func TestLoopServiceCostCapAndDisabledConvergence(t *testing.T) {
	service := NewLoopService(nil, nil, nil, nil, nil)
	if _, err := service.Start(context.Background(), "loop-3", "exec-3", LoopConfig{
		MaxIterations: 5,
		CostCap:       0.2,
		Epsilon:       0,
	}); err != nil {
		t.Fatalf("Start() error = %v", err)
	}

	statusValue, _, _, err := service.Submit(context.Background(), "loop-3", 0.5, 0.1, 100)
	if err != nil {
		t.Fatalf("Submit() error = %v", err)
	}
	if statusValue != StatusContinue {
		t.Fatalf("status = %s, want %s", statusValue, StatusContinue)
	}

	statusValue, _, _, err = service.Submit(context.Background(), "loop-3", 0.51, 0.11, 100)
	if err != nil {
		t.Fatalf("Submit() error = %v", err)
	}
	if statusValue != StatusBudgetExceeded {
		t.Fatalf("status = %s, want %s", statusValue, StatusBudgetExceeded)
	}
}

func TestLoopServiceValidationAndStateErrors(t *testing.T) {
	service := NewLoopService(nil, nil, nil, nil, nil)
	if _, err := service.Start(context.Background(), "loop-4", "exec-4", LoopConfig{}); err == nil {
		t.Fatal("expected invalid config error")
	}
	if _, err := service.Start(context.Background(), "loop-5", "exec-5", LoopConfig{MaxIterations: 2, CostCap: 1, Epsilon: 0.1}); err != nil {
		t.Fatalf("Start() error = %v", err)
	}
	if _, err := service.Start(context.Background(), "loop-5", "exec-5", LoopConfig{MaxIterations: 2, CostCap: 1, Epsilon: 0.1}); err != ErrLoopExists {
		t.Fatalf("duplicate start error = %v, want %v", err, ErrLoopExists)
	}
	if _, _, _, err := service.Submit(context.Background(), "missing", 0.5, 0.1, 10); err != ErrLoopNotFound {
		t.Fatalf("missing loop error = %v, want %v", err, ErrLoopNotFound)
	}
	if _, _, _, err := service.Submit(context.Background(), "loop-5", 2, 0.1, 10); err == nil {
		t.Fatal("expected invalid quality error")
	}
	if _, _, _, err := service.Submit(context.Background(), "loop-5", 0.2, 0.1, 10); err != nil {
		t.Fatalf("Submit() error = %v", err)
	}
	if _, _, _, err := service.Submit(context.Background(), "loop-5", 0.4, 0.1, 10); err != nil {
		t.Fatalf("Submit() error = %v", err)
	}
	if _, _, _, err := service.Submit(context.Background(), "loop-5", 0.4, 0.1, 10); err == nil {
		t.Fatal("expected loop-not-running error after convergence/budget update path")
	}
}

func TestLoopHelpers(t *testing.T) {
	service := NewLoopService(nil, nil, nil, nil, nil)
	if err := service.publishRuntimeEvent(context.Background(), "type", loopState{ExecutionID: "exec"}, 0.5); err != nil {
		t.Fatalf("publishRuntimeEvent() error = %v", err)
	}
	if err := service.persistIteration(context.Background(), loopState{LoopID: "loop", UsedIterations: 1}, 0.5, 0, 0.1, 10); err != nil {
		t.Fatalf("persistIteration() error = %v", err)
	}
	if redisKey("loop") != "correction:loop" {
		t.Fatalf("redisKey() returned %s", redisKey("loop"))
	}
	if parseEvalInt("3") != 3 || parseEvalFloat("1.5") != 1.5 {
		t.Fatal("parseEval helpers did not parse strings")
	}
	if parseEvalInt(2.9) != 2 {
		t.Fatalf("parseEvalInt(float64) = %d", parseEvalInt(2.9))
	}
	if parseEvalInt(struct{}{}) != 0 {
		t.Fatalf("parseEvalInt(default) = %d", parseEvalInt(struct{}{}))
	}
	if parseEvalFloat(int64(7)) != 7 {
		t.Fatalf("parseEvalFloat(int64) = %v", parseEvalFloat(int64(7)))
	}
	if parseEvalFloat(struct{}{}) != 0 {
		t.Fatalf("parseEvalFloat(default) = %v", parseEvalFloat(struct{}{}))
	}
	if nullableDelta(2, 0.1) != 0.1 {
		t.Fatal("nullableDelta() should return delta after first iteration")
	}
	if nullableDelta(1, 0.1) != nil {
		t.Fatal("nullableDelta() should return nil on first iteration")
	}
	if uuidFor("loop") == uuid.Nil {
		t.Fatal("uuidFor() should create deterministic uuid")
	}
	if uuidFor("123e4567-e89b-12d3-a456-426614174000") != uuid.MustParse("123e4567-e89b-12d3-a456-426614174000") {
		t.Fatal("uuidFor() should keep valid UUIDs unchanged")
	}
}

func TestLoopServiceScriptedRedisPaths(t *testing.T) {
	t.Run("start writes state into redis wrapper", func(t *testing.T) {
		client := newScriptedRedisClient()
		service := &LoopService{
			client: client,
			now:    func() time.Time { return time.Unix(5, 0).UTC() },
			states: map[string]*loopState{},
		}

		handle, err := service.Start(context.Background(), "loop-redis", "exec-redis", LoopConfig{
			MaxIterations: 3,
			CostCap:       2,
			Epsilon:       0.1,
		})
		if err != nil {
			t.Fatalf("Start() error = %v", err)
		}
		if handle.Status != "RUNNING" {
			t.Fatalf("handle status = %s", handle.Status)
		}
		if got := client.hashes[redisKey("loop-redis")]["status"]; got != "RUNNING" {
			t.Fatalf("stored status = %#v", got)
		}
	})

	t.Run("start propagates redis errors", func(t *testing.T) {
		service := &LoopService{
			client: &scriptedRedisClient{hsetErr: errors.New("hset failed"), hashes: map[string]map[string]any{}},
			now:    time.Now,
			states: map[string]*loopState{},
		}
		if _, err := service.Start(context.Background(), "loop-err", "exec-err", LoopConfig{
			MaxIterations: 2,
			CostCap:       1,
			Epsilon:       0.1,
		}); err == nil {
			t.Fatal("expected Start() error")
		}
	})

	t.Run("submit uses redis script results", func(t *testing.T) {
		client := newScriptedRedisClient()
		client.evalResult = []any{int64(1), float64(1), float64(0.2)}
		service := &LoopService{
			client:   client,
			scripts:  map[string]string{"convergence_check": "conv", "budget_decrement": "budget"},
			producer: &recordingProducer{},
			router:   escalation.NewRouter(&recordingProducer{}),
			now:      func() time.Time { return time.Unix(10, 0).UTC() },
			states: map[string]*loopState{
				"loop-script": {
					LoopID:      "loop-script",
					ExecutionID: "exec-script",
					Config:      LoopConfig{MaxIterations: 4, CostCap: 5, Epsilon: 0.05},
					PrevQuality: -1, PrevPrevQuality: -1, Status: "RUNNING",
				},
			},
		}

		statusValue, iteration, delta, err := service.Submit(context.Background(), "loop-script", 0.8, 0.2, 100)
		if err != nil {
			t.Fatalf("Submit() error = %v", err)
		}
		if statusValue != StatusConverged || iteration != 1 || delta != 0 {
			t.Fatalf("unexpected result: %s %d %v", statusValue, iteration, delta)
		}
		if got := client.hashes[redisKey("loop-script")]["status"]; got != string(StatusConverged) {
			t.Fatalf("stored status = %#v", got)
		}
	})

	t.Run("submit propagates eval errors", func(t *testing.T) {
		client := newScriptedRedisClient()
		client.evalErr = errors.New("eval failed")
		service := &LoopService{
			client:  client,
			scripts: map[string]string{"convergence_check": "conv"},
			states: map[string]*loopState{
				"loop-eval": {
					LoopID: "loop-eval", ExecutionID: "exec-eval",
					Config: LoopConfig{MaxIterations: 4, CostCap: 5, Epsilon: 0.05},
					Status: "RUNNING",
				},
			},
		}
		if _, _, _, err := service.Submit(context.Background(), "loop-eval", 0.8, 0.2, 100); err == nil {
			t.Fatal("expected Submit() error")
		}
	})
}

func TestPersistIterationUsesStore(t *testing.T) {
	recorder := &fakeIterationStore{}
	service := &LoopService{pool: recorder}

	if err := service.persistIteration(context.Background(), loopState{LoopID: "loop-db", UsedIterations: 2}, 0.7, 0.2, 0.1, 50); err != nil {
		t.Fatalf("persistIteration() error = %v", err)
	}
	if recorder.sql == "" || len(recorder.args) != 7 {
		t.Fatalf("unexpected exec call: sql=%q args=%d", recorder.sql, len(recorder.args))
	}
	if recorder.args[4] == nil {
		t.Fatal("expected delta to be stored after first iteration")
	}

	service.pool = &fakeIterationStore{err: errors.New("insert failed")}
	if err := service.persistIteration(context.Background(), loopState{LoopID: "loop-db", UsedIterations: 2}, 0.7, 0.2, 0.1, 50); err == nil {
		t.Fatal("expected persistIteration() error")
	}
}
