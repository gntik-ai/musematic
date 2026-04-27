package secrets

import "context"

type SecretProvider interface {
	Get(ctx context.Context, path string, key string) (string, error)
	Put(ctx context.Context, path string, values map[string]string) error
	DeleteVersion(ctx context.Context, path string, version int) error
	ListVersions(ctx context.Context, path string) ([]int, error)
	HealthCheck(ctx context.Context) (*HealthStatus, error)
}
