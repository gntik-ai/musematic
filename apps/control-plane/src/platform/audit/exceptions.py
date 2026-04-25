from __future__ import annotations


class AuditChainError(Exception):
    """Base exception for audit-chain failures."""


class AuditChainIntegrityError(AuditChainError):
    """Raised when an attestation is requested for an invalid chain range."""
