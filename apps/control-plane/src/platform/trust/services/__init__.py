from __future__ import annotations

CANONICAL_CATEGORIES = {
    "toxicity",
    "hate_speech",
    "violence_self_harm",
    "sexually_explicit",
    "pii_leakage",
}
MODERATION_ACTIONS = {"block", "redact", "flag"}
SAFETY_ORDER = ("block", "redact", "flag")
PROVIDER_FAILURE_ACTIONS = {"fail_closed", "fail_open"}
TIE_BREAK_RULES = {"max_score", "min_score", "primary_only"}
