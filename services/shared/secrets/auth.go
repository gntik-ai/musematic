package secrets

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	vaultapi "github.com/hashicorp/vault/api"
)

func (p *VaultSecretProvider) ensureAuthenticated(ctx context.Context) error {
	p.authMu.Lock()
	defer p.authMu.Unlock()

	if p.hasUsableTokenLocked() {
		return nil
	}
	return p.authenticateLocked(ctx)
}

func (p *VaultSecretProvider) reauthenticate(ctx context.Context) error {
	p.authMu.Lock()
	defer p.authMu.Unlock()
	return p.authenticateLocked(ctx)
}

func (p *VaultSecretProvider) hasUsableTokenLocked() bool {
	if p.client.Token() == "" {
		return false
	}
	if p.tokenExpiryAt.IsZero() {
		return true
	}
	return time.Now().Before(p.tokenExpiryAt)
}

func (p *VaultSecretProvider) authenticateLocked(ctx context.Context) error {
	var (
		secret *vaultapi.Secret
		err    error
	)

	switch p.settings.AuthMethod {
	case AuthMethodKubernetes:
		secret, err = p.authenticateKubernetes(ctx)
	case AuthMethodAppRole:
		secret, err = p.authenticateAppRole(ctx)
	case AuthMethodToken:
		err = p.authenticateToken(ctx)
	default:
		err = fmt.Errorf("unsupported Vault auth method: %s", p.settings.AuthMethod)
	}

	if err != nil {
		p.metrics.authFailure.WithLabelValues(string(p.settings.AuthMethod)).Inc()
		p.rememberFailure(err)
		return fmt.Errorf("%w: auth failed via %s", ErrCredentialUnavailable, p.settings.AuthMethod)
	}
	if secret != nil {
		p.applyAuthResponseLocked(secret)
	}
	LogVaultEvent(
		ctx,
		p.logger,
		"vault.authenticated",
		"auth_method", string(p.settings.AuthMethod),
		"token_expiry_at", p.tokenExpiryAt.Format(time.RFC3339),
	)
	return nil
}

func (p *VaultSecretProvider) authenticateKubernetes(ctx context.Context) (*vaultapi.Secret, error) {
	jwt, err := os.ReadFile(p.settings.ServiceAccountTokenPath)
	if err != nil {
		return nil, err
	}
	return p.client.Logical().WriteWithContext(ctx, "auth/kubernetes/login", map[string]interface{}{
		"role": p.settings.KubernetesRole,
		"jwt":  strings.TrimSpace(string(jwt)),
	})
}

func (p *VaultSecretProvider) authenticateAppRole(ctx context.Context) (*vaultapi.Secret, error) {
	if p.settings.AppRoleRoleID == "" {
		return nil, fmt.Errorf("missing AppRole role_id")
	}
	secretID, err := os.ReadFile(p.settings.AppRoleSecretIDPath)
	if err != nil {
		return nil, err
	}
	return p.client.Logical().WriteWithContext(ctx, "auth/approle/login", map[string]interface{}{
		"role_id":   p.settings.AppRoleRoleID,
		"secret_id": strings.TrimSpace(string(secretID)),
	})
}

func (p *VaultSecretProvider) authenticateToken(ctx context.Context) error {
	if p.settings.Token == "" {
		return fmt.Errorf("missing Vault token")
	}
	p.client.SetToken(p.settings.Token)
	secret, err := p.client.Auth().Token().LookupSelfWithContext(ctx)
	if err != nil {
		return err
	}
	p.applyLookupResponseLocked(secret)
	return nil
}

func (p *VaultSecretProvider) applyAuthResponseLocked(secret *vaultapi.Secret) {
	if secret == nil || secret.Auth == nil {
		return
	}
	if secret.Auth.ClientToken != "" {
		p.client.SetToken(secret.Auth.ClientToken)
	}
	p.leaseID = secret.LeaseID
	ttl := time.Duration(secret.Auth.LeaseDuration) * time.Second
	if ttl <= 0 {
		ttl = time.Duration(secret.LeaseDuration) * time.Second
	}
	p.applyTTLLocked(ttl, secret.Auth.Renewable)
}

func (p *VaultSecretProvider) applyLookupResponseLocked(secret *vaultapi.Secret) {
	if secret == nil {
		return
	}
	ttl, err := secret.TokenTTL()
	if err != nil || ttl <= 0 {
		return
	}
	p.applyTTLLocked(ttl, true)
}

func (p *VaultSecretProvider) applyTTLLocked(ttl time.Duration, renewable bool) {
	p.tokenTTL = ttl
	p.tokenExpiryAt = time.Now().Add(ttl)
	p.metrics.setTokenExpiry(p.tokenExpiryAt)
	if renewable {
		p.startRenewalLoopLocked()
	}
}

func (p *VaultSecretProvider) startRenewalLoopLocked() {
	if p.renewalCancel != nil {
		return
	}
	ctx, cancel := context.WithCancel(context.Background())
	p.renewalCancel = cancel
	go p.renewalLoop(ctx)
}

func (p *VaultSecretProvider) renewalLoop(ctx context.Context) {
	for {
		p.authMu.Lock()
		ttl := p.tokenTTL
		expiry := p.tokenExpiryAt
		threshold := p.settings.LeaseRenewalThreshold
		p.authMu.Unlock()

		if ttl <= 0 || expiry.IsZero() {
			return
		}
		delay := time.Until(expiry.Add(-durationRatio(ttl, threshold)))
		if delay < time.Second {
			delay = time.Second
		}

		timer := time.NewTimer(delay)
		select {
		case <-ctx.Done():
			timer.Stop()
			return
		case <-timer.C:
		}

		secret, err := p.client.Auth().Token().RenewSelfWithContext(ctx, 0)
		if err != nil {
			p.metrics.renewalFailure.Inc()
			p.rememberFailure(err)
			p.authMu.Lock()
			p.consecutiveRenewalFailures++
			failures := p.consecutiveRenewalFailures
			p.authMu.Unlock()
			if failures >= 3 {
				_ = p.reauthenticate(ctx)
			}
			continue
		}

		p.metrics.renewalSuccess.Inc()
		p.authMu.Lock()
		p.consecutiveRenewalFailures = 0
		if secret != nil && secret.Auth != nil {
			p.applyAuthResponseLocked(secret)
		} else if secret != nil {
			p.applyLookupResponseLocked(secret)
		}
		p.authMu.Unlock()
		LogVaultEvent(ctx, p.logger, "vault.lease_renewed", "token_expiry_at", p.tokenExpiryAt.Format(time.RFC3339))
	}
}

func durationRatio(duration time.Duration, ratio float64) time.Duration {
	if ratio <= 0 || ratio >= 1 {
		ratio = 0.5
	}
	return time.Duration(float64(duration) * ratio)
}

func (p *VaultSecretProvider) registerSignalHandler() {
	if p.settings.DisableSignalHandler {
		return
	}
	p.signalOnce.Do(func() {
		p.signalCh = make(chan os.Signal, 1)
		signal.Notify(p.signalCh, syscall.SIGTERM)
		go func() {
			<-p.signalCh
			_ = p.RevokeSelf(context.Background())
		}()
	})
}

func (p *VaultSecretProvider) RevokeSelf(ctx context.Context) error {
	var err error
	p.revokeOnce.Do(func() {
		currentToken := p.client.Token()
		if currentToken == "" {
			return
		}
		err = p.client.Auth().Token().RevokeSelfWithContext(ctx, currentToken)
		if err == nil {
			LogVaultEvent(ctx, p.logger, "vault.lease_revoked", "auth_method", string(p.settings.AuthMethod))
		}
	})
	return err
}

func (p *VaultSecretProvider) Close() {
	p.authMu.Lock()
	if p.renewalCancel != nil {
		p.renewalCancel()
		p.renewalCancel = nil
	}
	if p.signalCh != nil {
		signal.Stop(p.signalCh)
		p.signalCh = nil
	}
	p.authMu.Unlock()
}

func (p *VaultSecretProvider) rememberFailure(err error) {
	if err == nil {
		return
	}
	p.failuresMu.Lock()
	defer p.failuresMu.Unlock()
	if len(p.recentFailures) == 10 {
		copy(p.recentFailures, p.recentFailures[1:])
		p.recentFailures = p.recentFailures[:9]
	}
	p.recentFailures = append(p.recentFailures, err.Error())
}

func (p *VaultSecretProvider) failuresSnapshot() []string {
	p.failuresMu.Lock()
	defer p.failuresMu.Unlock()
	result := make([]string, len(p.recentFailures))
	copy(result, p.recentFailures)
	return result
}
