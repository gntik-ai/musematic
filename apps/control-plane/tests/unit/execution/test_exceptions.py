from __future__ import annotations

from platform.execution.exceptions import (
    ApprovalAlreadyDecidedError,
    ExecutionAlreadyRunningError,
    ExecutionNotFoundError,
    HotChangeIncompatibleError,
)


def test_execution_exceptions_expose_expected_codes_and_details() -> None:
    not_found = ExecutionNotFoundError("exec-1")
    already_running = ExecutionAlreadyRunningError("exec-2")
    incompatible = HotChangeIncompatibleError(["step_a removed"])
    approval = ApprovalAlreadyDecidedError("exec-3", "approval_step")

    assert not_found.code == "EXECUTION_NOT_FOUND"
    assert "exec-1" in not_found.message
    assert already_running.code == "EXECUTION_ALREADY_RUNNING"
    assert "exec-2" in already_running.message
    assert incompatible.code == "HOT_CHANGE_INCOMPATIBLE"
    assert incompatible.details == {"issues": ["step_a removed"]}
    assert approval.code == "APPROVAL_ALREADY_DECIDED"
    assert "approval_step" in approval.message
