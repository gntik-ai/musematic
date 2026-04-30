package secrets

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	vaultapi "github.com/hashicorp/vault/api"
)

type AuthMethod string

const (
	AuthMethodKubernetes AuthMethod = "kubernetes"
	AuthMethodAppRole    AuthMethod = "approle"
	AuthMethodToken      AuthMethod = "token"
)

type VaultSettings struct {
	Addr                    string
	Namespace               string
	CACertPath              string
	AuthMethod              AuthMethod
	KubernetesRole          string
	ServiceAccountTokenPath string
	AppRoleRoleID           string
	AppRoleSecretIDPath     string
	Token                   string
	KVMount                 string
	CacheTTL                time.Duration
	CacheMaxStaleness       time.Duration
	RetryAttempts           int
	RetryTimeout            time.Duration
	LeaseRenewalThreshold   float64
	DisableSignalHandler    bool
}

func DefaultVaultSettings() VaultSettings {
	return VaultSettings{
		AuthMethod:              AuthMethodKubernetes,
		KubernetesRole:          "musematic-platform",
		ServiceAccountTokenPath: "/var/run/secrets/tokens/vault-token",
		KVMount:                 "secret",
		CacheTTL:                time.Minute,
		CacheMaxStaleness:       5 * time.Minute,
		RetryAttempts:           3,
		RetryTimeout:            10 * time.Second,
		LeaseRenewalThreshold:   0.5,
	}
}

type VaultSecretProvider struct {
	settings VaultSettings
	client   *vaultapi.Client
	cache    *secretCache
	metrics  *vaultMetrics
	logger   *slog.Logger

	authMu                     sync.Mutex
	tokenExpiryAt              time.Time
	tokenTTL                   time.Duration
	leaseID                    string
	renewalCancel              context.CancelFunc
	consecutiveRenewalFailures int
	failuresMu                 sync.Mutex
	recentFailures             []string
	signalOnce                 sync.Once
	signalCh                   chan os.Signal
	revokeOnce                 sync.Once
}

type VaultOption func(*VaultSecretProvider)

func WithVaultClient(client *vaultapi.Client) VaultOption {
	return func(provider *VaultSecretProvider) {
		provider.client = client
	}
}

func WithVaultLogger(logger *slog.Logger) VaultOption {
	return func(provider *VaultSecretProvider) {
		provider.logger = logger
	}
}

func NewVaultSecretProvider(settings VaultSettings, opts ...VaultOption) (*VaultSecretProvider, error) {
	settings = normalizeVaultSettings(settings)
	provider := &VaultSecretProvider{
		settings: settings,
		cache:    newSecretCache(settings.CacheTTL, settings.CacheMaxStaleness),
		metrics:  defaultVaultMetrics,
		logger:   slog.Default(),
	}
	for _, opt := range opts {
		opt(provider)
	}
	if provider.client == nil {
		client, err := newVaultClient(settings)
		if err != nil {
			return nil, err
		}
		provider.client = client
	}
	provider.registerSignalHandler()
	return provider, nil
}

func normalizeVaultSettings(settings VaultSettings) VaultSettings {
	defaults := DefaultVaultSettings()
	if settings.AuthMethod == "" {
		settings.AuthMethod = defaults.AuthMethod
	}
	if settings.KubernetesRole == "" {
		settings.KubernetesRole = defaults.KubernetesRole
	}
	if settings.ServiceAccountTokenPath == "" {
		settings.ServiceAccountTokenPath = defaults.ServiceAccountTokenPath
	}
	if settings.KVMount == "" {
		settings.KVMount = defaults.KVMount
	}
	if settings.CacheTTL <= 0 {
		settings.CacheTTL = defaults.CacheTTL
	}
	if settings.CacheMaxStaleness <= 0 {
		settings.CacheMaxStaleness = defaults.CacheMaxStaleness
	}
	if settings.RetryAttempts <= 0 {
		settings.RetryAttempts = defaults.RetryAttempts
	}
	if settings.RetryTimeout <= 0 {
		settings.RetryTimeout = defaults.RetryTimeout
	}
	if settings.LeaseRenewalThreshold <= 0 || settings.LeaseRenewalThreshold >= 1 {
		settings.LeaseRenewalThreshold = defaults.LeaseRenewalThreshold
	}
	return settings
}

func newVaultClient(settings VaultSettings) (*vaultapi.Client, error) {
	config := vaultapi.DefaultConfig()
	if settings.Addr != "" {
		config.Address = settings.Addr
	}
	config.Timeout = settings.RetryTimeout
	if settings.CACertPath != "" {
		if err := config.ConfigureTLS(&vaultapi.TLSConfig{CACert: settings.CACertPath}); err != nil {
			return nil, err
		}
	}
	client, err := vaultapi.NewClient(config)
	if err != nil {
		return nil, err
	}
	if settings.Namespace != "" {
		client.SetNamespace(settings.Namespace)
	}
	return client, nil
}

func (p *VaultSecretProvider) Get(ctx context.Context, path string, key string) (string, error) {
	return p.get(ctx, path, key, false)
}

func (p *VaultSecretProvider) GetCritical(ctx context.Context, path string, key string) (string, error) {
	return p.get(ctx, path, key, true)
}

func (p *VaultSecretProvider) get(ctx context.Context, path string, key string, critical bool) (string, error) {
	if key == "" {
		key = "value"
	}
	if err := ValidatePath(path); err != nil {
		return "", err
	}
	if value, ok := p.cache.getFresh(path, key); ok {
		p.metrics.recordCacheHit()
		return value, nil
	}
	p.metrics.recordCacheMiss()

	if err := p.ensureAuthenticated(ctx); err != nil {
		return p.staleOrError(ctx, path, key, critical, err)
	}

	secret, err := p.readSecret(ctx, path)
	if isStatus(err, http.StatusForbidden) {
		if authErr := p.reauthenticate(ctx); authErr == nil {
			secret, err = p.readSecret(ctx, path)
		}
	}
	if err != nil {
		return p.staleOrError(ctx, path, key, critical, err)
	}
	raw, ok := secret.Data[key]
	if !ok {
		return "", fmt.Errorf("%w: %s[%s]", ErrCredentialUnavailable, path, key)
	}
	value, ok := raw.(string)
	if !ok {
		return "", fmt.Errorf("%w: %s[%s] is not a string", ErrCredentialUnavailable, path, key)
	}
	p.cache.set(path, key, value)
	p.metrics.read.WithLabelValues(domainFromPath(path)).Inc()
	return value, nil
}

func (p *VaultSecretProvider) Put(ctx context.Context, path string, values map[string]string) error {
	if err := ValidatePath(path); err != nil {
		return err
	}
	if err := p.ensureAuthenticated(ctx); err != nil {
		return err
	}
	relative := relativeKVPath(path, p.settings.KVMount)
	kv := p.client.KVv2(p.settings.KVMount)
	data := make(map[string]interface{}, len(values))
	for key, value := range values {
		data[key] = value
	}
	var lastErr error
	for attempt := 0; attempt < p.settings.RetryAttempts; attempt++ {
		cas, err := p.currentVersion(ctx, relative)
		if err != nil && !isStatus(err, http.StatusNotFound) {
			return translateVaultError(path, err)
		}
		_, err = kv.Put(ctx, relative, data, vaultapi.WithCheckAndSet(cas))
		if err == nil {
			p.cache.flush(path)
			p.metrics.write.WithLabelValues(domainFromPath(path)).Inc()
			return nil
		}
		if isCASConflict(err) {
			lastErr = err
			continue
		}
		if isStatus(err, http.StatusForbidden) {
			_ = p.reauthenticate(ctx)
		}
		return translateVaultError(path, err)
	}
	return fmt.Errorf("%w: CAS conflict after retries for %s: %v", ErrCredentialUnavailable, path, lastErr)
}

func (p *VaultSecretProvider) DeleteVersion(ctx context.Context, path string, version int) error {
	if err := ValidatePath(path); err != nil {
		return err
	}
	if version <= 0 {
		return fmt.Errorf("%w: version must be positive", ErrInvalidVaultPath)
	}
	if err := p.ensureAuthenticated(ctx); err != nil {
		return err
	}
	err := p.client.KVv2(p.settings.KVMount).Destroy(ctx, relativeKVPath(path, p.settings.KVMount), []int{version})
	if isStatus(err, http.StatusForbidden) {
		_ = p.reauthenticate(ctx)
		err = p.client.KVv2(p.settings.KVMount).Destroy(ctx, relativeKVPath(path, p.settings.KVMount), []int{version})
	}
	if err != nil {
		return translateVaultError(path, err)
	}
	p.cache.flush(path)
	return nil
}

func (p *VaultSecretProvider) ListVersions(ctx context.Context, path string) ([]int, error) {
	if err := ValidatePath(path); err != nil {
		return nil, err
	}
	if err := p.ensureAuthenticated(ctx); err != nil {
		return nil, err
	}
	metadata, err := p.client.KVv2(p.settings.KVMount).GetMetadata(ctx, relativeKVPath(path, p.settings.KVMount))
	if isStatus(err, http.StatusForbidden) {
		_ = p.reauthenticate(ctx)
		metadata, err = p.client.KVv2(p.settings.KVMount).GetMetadata(ctx, relativeKVPath(path, p.settings.KVMount))
	}
	if err != nil {
		return nil, translateVaultError(path, err)
	}
	versions := make([]int, 0, len(metadata.Versions))
	for key := range metadata.Versions {
		version, err := strconv.Atoi(key)
		if err == nil {
			versions = append(versions, version)
		}
	}
	sort.Ints(versions)
	return versions, nil
}

func (p *VaultSecretProvider) HealthCheck(ctx context.Context) (*HealthStatus, error) {
	status := &HealthStatus{
		Status:         "green",
		AuthMethod:     string(p.settings.AuthMethod),
		RecentFailures: p.failuresSnapshot(),
		CacheHitRate:   p.metrics.hitRate(),
	}
	p.authMu.Lock()
	if !p.tokenExpiryAt.IsZero() {
		expiry := p.tokenExpiryAt
		status.TokenExpiryAt = &expiry
		p.metrics.setTokenExpiry(expiry)
	}
	p.authMu.Unlock()

	health, err := p.client.Sys().HealthWithContext(ctx)
	if err != nil {
		status.Status = "red"
		status.Error = err.Error()
		p.rememberFailure(err)
		return status, nil
	}
	if health.Sealed || !health.Initialized {
		status.Status = "red"
	} else if health.Standby || health.PerformanceStandby {
		status.Status = "yellow"
	}
	if leaseCount, err := p.countLeases(ctx); err == nil {
		status.LeaseCount = leaseCount
		p.metrics.leaseCount.WithLabelValues(podName()).Set(float64(leaseCount))
	}
	return status, nil
}

func (p *VaultSecretProvider) FlushCache(path string) int {
	return p.cache.flush(path)
}

func (p *VaultSecretProvider) readSecret(ctx context.Context, path string) (*vaultapi.KVSecret, error) {
	return p.client.KVv2(p.settings.KVMount).Get(ctx, relativeKVPath(path, p.settings.KVMount))
}

func (p *VaultSecretProvider) currentVersion(ctx context.Context, relativePath string) (int, error) {
	metadata, err := p.client.KVv2(p.settings.KVMount).GetMetadata(ctx, relativePath)
	if err != nil {
		return 0, err
	}
	return metadata.CurrentVersion, nil
}

func (p *VaultSecretProvider) countLeases(ctx context.Context) (int, error) {
	secret, err := p.client.Logical().ListWithContext(ctx, "sys/leases/lookup/")
	if err != nil || secret == nil || secret.Data == nil {
		return 0, err
	}
	keys, ok := secret.Data["keys"].([]interface{})
	if !ok {
		return 0, nil
	}
	return len(keys), nil
}

func (p *VaultSecretProvider) staleOrError(ctx context.Context, path string, key string, critical bool, cause error) (string, error) {
	p.rememberFailure(cause)
	if isStatus(cause, http.StatusForbidden) {
		p.metrics.policyDenied.WithLabelValues(path).Inc()
		LogVaultEvent(ctx, p.logger, "vault.policy_denied", "path", path)
		return "", translateVaultError(path, cause)
	}
	if critical {
		return "", translateVaultError(path, cause)
	}
	if value, age, ok := p.cache.getStale(path, key); ok {
		p.metrics.servingStale.Inc()
		LogVaultEvent(ctx, p.logger, "vault.serving_stale", "path", path, "stale_age_seconds", int(age.Seconds()))
		return value, nil
	}
	LogVaultEvent(ctx, p.logger, "vault.unreachable", "path", path, "error", cause.Error())
	return "", translateVaultError(path, cause)
}

func relativeKVPath(path string, mount string) string {
	prefix := strings.TrimSuffix(mount, "/") + "/data/"
	return strings.TrimPrefix(path, prefix)
}

func translateVaultError(path string, err error) error {
	if err == nil {
		return nil
	}
	var responseErr *vaultapi.ResponseError
	if errors.As(err, &responseErr) {
		switch responseErr.StatusCode {
		case http.StatusForbidden:
			return fmt.Errorf("%w: %s", ErrCredentialPolicyDenied, path)
		case http.StatusNotFound:
			return fmt.Errorf("%w: %s", ErrCredentialUnavailable, path)
		default:
			if responseErr.StatusCode >= 500 {
				return fmt.Errorf("%w: %s", ErrCredentialUnavailable, path)
			}
		}
	}
	return fmt.Errorf("%w: %s: %v", ErrCredentialUnavailable, path, err)
}

func isStatus(err error, status int) bool {
	var responseErr *vaultapi.ResponseError
	if errors.As(err, &responseErr) {
		return responseErr.StatusCode == status
	}
	return false
}

func isCASConflict(err error) bool {
	if err == nil {
		return false
	}
	var responseErr *vaultapi.ResponseError
	if errors.As(err, &responseErr) {
		if responseErr.StatusCode == http.StatusBadRequest || responseErr.StatusCode == http.StatusPreconditionFailed {
			return strings.Contains(strings.ToLower(responseErr.Error()), "check-and-set")
		}
	}
	return false
}

var _ SecretProvider = (*VaultSecretProvider)(nil)
