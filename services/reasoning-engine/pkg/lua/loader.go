package lua

import (
	"context"
	_ "embed"
	"fmt"

	"github.com/redis/go-redis/v9"
)

//go:embed budget_decrement.lua
var budgetDecrementScript string

//go:embed convergence_check.lua
var convergenceCheckScript string

func Load(ctx context.Context, rdb redis.Scripter) (map[string]string, error) {
	scripts := map[string]string{
		"budget_decrement":  budgetDecrementScript,
		"convergence_check": convergenceCheckScript,
	}
	loaded := make(map[string]string, len(scripts))
	for name, script := range scripts {
		sha, err := rdb.ScriptLoad(ctx, script).Result()
		if err != nil {
			return nil, fmt.Errorf("load %s: %w", name, err)
		}
		loaded[name] = sha
	}
	return loaded, nil
}
