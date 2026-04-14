package redis

import (
	"context"
	"errors"
	"os"
	"strconv"
	"time"

	goredis "github.com/redis/go-redis/v9"
)

type BudgetConfig struct {
	MaxTokens int64
	MaxRounds int64
	MaxCost   float64
	MaxTimeMS int64
}

type BudgetResult struct {
	Allowed         bool
	RemainingTokens int64
	RemainingRounds int64
	RemainingCost   float64
	RemainingTimeMS int64
}

type BudgetClient struct {
	client       redisCloser
	budgetScript budgetScriptRunner
}

type redisCloser interface {
	Close() error
}

type budgetScriptRunner interface {
	Run(ctx context.Context, key string, now int64, dimension string, amount int64) (any, error)
}

type redisBudgetScript struct {
	client *goredis.ClusterClient
	script *goredis.Script
}

func (r redisBudgetScript) Run(ctx context.Context, key string, now int64, dimension string, amount int64) (any, error) {
	return r.script.Run(
		ctx,
		r.client,
		[]string{key},
		now,
		dimension,
		amount,
	).Result()
}

func NewClusterClient(addrs []string, password string) (*BudgetClient, error) {
	source, err := os.ReadFile("lua/budget_decrement.lua")
	if err != nil {
		return nil, err
	}

	client := goredis.NewClusterClient(&goredis.ClusterOptions{
		Addrs:        addrs,
		Password:     password,
		PoolSize:     50,
		MinIdleConns: 25,
	})

	return &BudgetClient{
		client:       client,
		budgetScript: redisBudgetScript{client: client, script: goredis.NewScript(string(source))},
	}, nil
}

func (c *BudgetClient) DecrementBudget(
	ctx context.Context,
	executionID string,
	stepID string,
	dimension string,
	amount int64,
) (BudgetResult, error) {
	timeoutCtx, cancel := context.WithTimeout(ctx, 10*time.Millisecond)
	defer cancel()

	if c == nil || c.budgetScript == nil {
		return BudgetResult{}, errors.New("budget client is not initialized")
	}

	key := "budget:" + executionID + ":" + stepID
	now := time.Now().UnixMilli()
	raw, err := c.budgetScript.Run(timeoutCtx, key, now, dimension, amount)
	if err != nil {
		return BudgetResult{}, err
	}

	values, ok := raw.([]interface{})
	if !ok || len(values) != 5 {
		return BudgetResult{}, errors.New("unexpected redis budget response")
	}

	return BudgetResult{
		Allowed:         toInt64(values[0]) == 1,
		RemainingTokens: toInt64(values[1]),
		RemainingRounds: toInt64(values[2]),
		RemainingCost:   toFloat64(values[3]),
		RemainingTimeMS: toInt64(values[4]),
	}, nil
}

func (c *BudgetClient) Close() error {
	if c == nil || c.client == nil {
		return nil
	}
	return c.client.Close()
}

func toInt64(value interface{}) int64 {
	switch v := value.(type) {
	case int64:
		return v
	case string:
		parsed, _ := strconv.ParseInt(v, 10, 64)
		return parsed
	default:
		return 0
	}
}

func toFloat64(value interface{}) float64 {
	switch v := value.(type) {
	case float64:
		return v
	case string:
		parsed, _ := strconv.ParseFloat(v, 64)
		return parsed
	default:
		return 0
	}
}
