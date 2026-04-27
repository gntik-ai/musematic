# Model Catalog and Fallback

Feature 075 introduces a governed model catalogue for the control plane. Approved entries define
provider/model bindings, cost metadata, quality tier, context window, allowed use cases, prohibited
use cases, and an approval expiry. Agents reference catalogue entries through
`default_model_binding` using the `provider:model_id` format.

## Runtime Routing

The `ModelRouter` validates each binding before dispatch. Blocked models fail fast, deprecated
models remain callable for migration windows, and missing credentials raise a configuration error
before provider traffic leaves the platform.

Provider calls use per-workspace Vault-backed credential references. The router resolves the
credential at call time and never logs the resolved secret material.

## Fallback Policies

Fallback policies are scoped in this order: agent, workspace, then global. Policies define a primary
catalogue entry, a fallback chain, primary retry count, backoff strategy, quality degradation budget,
and recovery window. The router sets a Redis sticky fallback key after primary failure so repeated
calls avoid a thundering herd against the failing provider until the recovery window expires.

## Prompt-Injection Defence

Three optional layers are available:

- Input sanitizer applies platform-wide and workspace-scoped regex patterns with strip, quote, or
  reject actions.
- System prompt hardener wraps untrusted user text with stable delimiters and a versioned preamble.
- Output validator applies debug-redaction secret patterns and model-specific role-reversal checks.

## Operations

The scheduler profile runs the auto-deprecation scanner. It transitions expired approved catalogue
entries to deprecated, emits `model.deprecated`, writes audit-chain evidence, and records compliance
evidence for approved models that remain without model cards after seven days.
