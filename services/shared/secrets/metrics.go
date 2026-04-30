package secrets

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"strings"
	"sync/atomic"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var forbiddenLogFields = map[string]struct{}{
	"token":         {},
	"secret_id":     {},
	"kv_value":      {},
	"client_secret": {},
}

type vaultMetrics struct {
	leaseCount     *prometheus.GaugeVec
	tokenExpiry    prometheus.Gauge
	renewalSuccess prometheus.Counter
	renewalFailure prometheus.Counter
	authFailure    *prometheus.CounterVec
	read           *prometheus.CounterVec
	write          *prometheus.CounterVec
	cacheHit       prometheus.Counter
	cacheMiss      prometheus.Counter
	cacheHitRatio  prometheus.Gauge
	servingStale   prometheus.Counter
	policyDenied   *prometheus.CounterVec
	hits           atomic.Uint64
	misses         atomic.Uint64
}

var defaultVaultMetrics = &vaultMetrics{
	leaseCount: promauto.NewGaugeVec(prometheus.GaugeOpts{
		Name: "vault_lease_count",
		Help: "Active Vault lease count.",
	}, []string{"pod"}),
	tokenExpiry: promauto.NewGauge(prometheus.GaugeOpts{
		Name: "vault_token_expiry_seconds",
		Help: "Seconds until the current Vault token expires.",
	}),
	renewalSuccess: promauto.NewCounter(prometheus.CounterOpts{
		Name: "vault_renewal_success_total",
		Help: "Vault token renewal successes.",
	}),
	renewalFailure: promauto.NewCounter(prometheus.CounterOpts{
		Name: "vault_renewal_failure_total",
		Help: "Vault token renewal failures.",
	}),
	authFailure: promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "vault_auth_failure_total",
		Help: "Vault auth failures.",
	}, []string{"auth_method"}),
	read: promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "vault_read_total",
		Help: "Vault secret reads.",
	}, []string{"domain"}),
	write: promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "vault_write_total",
		Help: "Vault secret writes.",
	}, []string{"domain"}),
	cacheHit: promauto.NewCounter(prometheus.CounterOpts{
		Name: "vault_cache_hit_total",
		Help: "Vault cache hits.",
	}),
	cacheMiss: promauto.NewCounter(prometheus.CounterOpts{
		Name: "vault_cache_miss_total",
		Help: "Vault cache misses.",
	}),
	cacheHitRatio: promauto.NewGauge(prometheus.GaugeOpts{
		Name: "vault_cache_hit_ratio",
		Help: "Vault cache hit ratio.",
	}),
	servingStale: promauto.NewCounter(prometheus.CounterOpts{
		Name: "vault_serving_stale_total",
		Help: "Vault stale secret reads.",
	}),
	policyDenied: promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "vault_policy_denied_total",
		Help: "Vault policy denied responses.",
	}, []string{"path"}),
}

func (m *vaultMetrics) recordCacheHit() {
	m.cacheHit.Inc()
	m.hits.Add(1)
	m.updateHitRatio()
}

func (m *vaultMetrics) recordCacheMiss() {
	m.cacheMiss.Inc()
	m.misses.Add(1)
	m.updateHitRatio()
}

func (m *vaultMetrics) updateHitRatio() {
	hits := m.hits.Load()
	misses := m.misses.Load()
	total := hits + misses
	if total == 0 {
		m.cacheHitRatio.Set(0)
		return
	}
	m.cacheHitRatio.Set(float64(hits) / float64(total))
}

func (m *vaultMetrics) setTokenExpiry(expiry time.Time) {
	seconds := time.Until(expiry).Seconds()
	if seconds < 0 {
		seconds = 0
	}
	m.tokenExpiry.Set(seconds)
}

func (m *vaultMetrics) hitRate() float64 {
	hits := m.hits.Load()
	misses := m.misses.Load()
	total := hits + misses
	if total == 0 {
		return 0
	}
	return float64(hits) / float64(total)
}

func domainFromPath(path string) string {
	parts := strings.Split(path, "/")
	if len(parts) > 4 {
		return parts[4]
	}
	return "unknown"
}

func podName() string {
	if name := os.Getenv("HOSTNAME"); name != "" {
		return name
	}
	return "unknown"
}

func ValidateVaultLogAttrs(args ...any) error {
	for i := 0; i < len(args); i++ {
		switch value := args[i].(type) {
		case string:
			if _, forbidden := forbiddenLogFields[value]; forbidden {
				return fmt.Errorf("forbidden Vault log field: %s", value)
			}
			i++
		case slog.Attr:
			if _, forbidden := forbiddenLogFields[value.Key]; forbidden {
				return fmt.Errorf("forbidden Vault log field: %s", value.Key)
			}
		}
	}
	return nil
}

func LogVaultEvent(ctx context.Context, logger *slog.Logger, event string, args ...any) {
	if logger == nil {
		logger = slog.Default()
	}
	if err := ValidateVaultLogAttrs(args...); err != nil {
		panic(err)
	}
	logger.InfoContext(ctx, event, args...)
}
