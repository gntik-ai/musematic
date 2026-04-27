package secrets

import (
	"errors"
	"time"
)

var (
	ErrCredentialUnavailable  = errors.New("credential unavailable")
	ErrCredentialPolicyDenied = errors.New("policy denied")
	ErrInvalidVaultPath       = errors.New("invalid vault path")
)

type HealthStatus struct {
	Status         string
	AuthMethod     string
	TokenExpiryAt  *time.Time
	LeaseCount     int
	RecentFailures []string
	CacheHitRate   float64
	Error          string
}

func IsCredentialUnavailable(err error) bool {
	return errors.Is(err, ErrCredentialUnavailable)
}

func IsCredentialPolicyDenied(err error) bool {
	return errors.Is(err, ErrCredentialPolicyDenied)
}

func IsInvalidVaultPath(err error) bool {
	return errors.Is(err, ErrInvalidVaultPath)
}
