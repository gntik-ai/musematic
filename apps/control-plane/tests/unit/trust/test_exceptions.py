from __future__ import annotations

from platform.trust.exceptions import (
    ATERunError,
    CertificationNotFoundError,
    CertificationStateError,
    CircuitBreakerTrippedError,
    GuardrailBlockedError,
    InvalidStateTransitionError,
    OJEConfigError,
    PreScreenerError,
    TrustError,
)


def test_trust_exceptions_expose_expected_codes_and_details() -> None:
    generic = TrustError("TRUST_GENERIC", "generic")
    not_found = CertificationNotFoundError("cert-1")
    state_error = CertificationStateError("bad state", certification_id="cert-2")
    state_error_no_id = CertificationStateError("bad state")
    transition = InvalidStateTransitionError("pending", "active")
    blocked = GuardrailBlockedError("tool_control", "policy:block")
    breaker = CircuitBreakerTrippedError("agent-1")
    ate = ATERunError("simulation failed", simulation_id="sim-1")
    ate_no_id = ATERunError("simulation failed")
    oje = OJEConfigError("missing fqn", fqn="judge:one")
    oje_no_fqn = OJEConfigError("missing fqn")
    prescreener = PreScreenerError("bad rule set", rule_set_id="rule-1")
    prescreener_no_id = PreScreenerError("bad rule set")

    assert generic.code == "TRUST_GENERIC"
    assert generic.status_code == 400
    assert not_found.status_code == 404
    assert not_found.details == {"certification_id": "cert-1"}
    assert state_error.details == {"certification_id": "cert-2"}
    assert state_error_no_id.details == {}
    assert transition.details == {"current_state": "pending", "target_state": "active"}
    assert blocked.status_code == 403
    assert blocked.details == {"layer": "tool_control", "policy_basis": "policy:block"}
    assert breaker.status_code == 429
    assert breaker.details == {"agent_id": "agent-1"}
    assert ate.status_code == 502
    assert ate.details == {"simulation_id": "sim-1"}
    assert ate_no_id.details == {}
    assert oje.details == {"fqn": "judge:one"}
    assert oje_no_fqn.details == {}
    assert prescreener.details == {"rule_set_id": "rule-1"}
    assert prescreener_no_id.details == {}
