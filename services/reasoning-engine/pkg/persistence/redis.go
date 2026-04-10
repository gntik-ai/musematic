package persistence

import (
	"context"
	"os"
	"strings"

	"github.com/redis/go-redis/v9"
)

func NewRedisClient(addr string) *redis.ClusterClient {
	addrs := splitCSV(addr)
	if len(addrs) == 0 {
		return nil
	}

	opts := &redis.ClusterOptions{
		Addrs: addrs,
	}
	if os.Getenv("REDIS_TEST_MODE") == "standalone" {
		opts.ClusterSlots = func(context.Context) ([]redis.ClusterSlot, error) {
			return []redis.ClusterSlot{{
				Start: 0,
				End:   16383,
				Nodes: []redis.ClusterNode{{Addr: addrs[0]}},
			}}, nil
		}
	}

	return redis.NewClusterClient(opts)
}

func splitCSV(value string) []string {
	parts := strings.Split(value, ",")
	out := make([]string, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part != "" {
			out = append(out, part)
		}
	}
	return out
}
