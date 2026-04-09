package redis

import (
	"context"
	"errors"
	"os"
	"path/filepath"
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
	client       *goredis.ClusterClient
	budgetScript *goredis.Script
}

func NewClusterClient(addrs []string, password string) (*BudgetClient, error) {
	scriptPath := filepath.Join("lua", "budget_decrement.lua")
	source, err := os.ReadFile(scriptPath)
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
		budgetScript: goredis.NewScript(string(source)),
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

	key := "budget:" + executionID + ":" + stepID
	now := time.Now().UnixMilli()
	raw, err := c.budgetScript.Run(
		timeoutCtx,
		c.client,
		[]string{key},
		now,
		dimension,
		amount,
	).Result()
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

