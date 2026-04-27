package secrets

import (
	"errors"
	"testing"
)

func TestValidatePathAcceptsCanonicalPaths(t *testing.T) {
	valid := []string{
		"secret/data/musematic/production/oauth/google",
		"secret/data/musematic/staging/model-providers/openai",
		"secret/data/musematic/dev/notifications/webhook-secrets/hook_1",
		"secret/data/musematic/test/ibor/source/primary",
		"secret/data/musematic/ci/audit-chain/signing-key",
		"secret/data/musematic/production/connectors/slack/bot-token",
		"secret/data/musematic/production/accounts/bootstrap",
	}
	for _, path := range valid {
		if err := ValidatePath(path); err != nil {
			t.Fatalf("expected %s to validate: %v", path, err)
		}
	}
}

func TestValidatePathRejectsInvalidPaths(t *testing.T) {
	invalid := []string{
		"vault/google",
		"secret/data/musematic/prod/oauth/google",
		"secret/data/musematic/dev/runtime/key",
		"secret/metadata/musematic/dev/oauth/google",
	}
	for _, path := range invalid {
		err := ValidatePath(path)
		if !errors.Is(err, ErrInvalidVaultPath) {
			t.Fatalf("expected invalid path error for %s, got %v", path, err)
		}
	}
}

func TestErrorHelpers(t *testing.T) {
	if !IsCredentialUnavailable(ErrCredentialUnavailable) {
		t.Fatal("expected unavailable helper to match")
	}
	if !IsCredentialPolicyDenied(ErrCredentialPolicyDenied) {
		t.Fatal("expected policy helper to match")
	}
	if !IsInvalidVaultPath(ErrInvalidVaultPath) {
		t.Fatal("expected invalid path helper to match")
	}
}
