from __future__ import annotations

from platform.common.exceptions import PlatformError


class EvaluationError(PlatformError):
    pass


class RubricNotFoundError(EvaluationError):
    status_code = 404

    def __init__(self) -> None:
        super().__init__("EVALUATION_RUBRIC_NOT_FOUND", "Rubric not found")


class RubricValidationError(EvaluationError):
    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__("EVALUATION_RUBRIC_INVALID", message)


class RubricInFlightError(EvaluationError):
    status_code = 409

    def __init__(self) -> None:
        super().__init__(
            "EVALUATION_RUBRIC_IN_FLIGHT",
            "Rubric is referenced by in-flight evaluation runs",
        )


class RubricBuiltinProtectedError(EvaluationError):
    status_code = 403

    def __init__(self) -> None:
        super().__init__(
            "EVALUATION_RUBRIC_BUILTIN_PROTECTED",
            "Builtin rubrics cannot be modified",
        )


class RubricArchivedError(EvaluationError):
    status_code = 409

    def __init__(self) -> None:
        super().__init__("EVALUATION_RUBRIC_ARCHIVED", "Rubric is archived")


class CalibrationRunImmutableError(EvaluationError):
    status_code = 409

    def __init__(self) -> None:
        super().__init__(
            "EVALUATION_CALIBRATION_IMMUTABLE",
            "Calibration run is immutable once completed",
        )


class TemplateLoadError(EvaluationError):
    status_code = 500

    def __init__(self, template_name: str, message: str) -> None:
        super().__init__(
            "EVALUATION_TEMPLATE_LOAD_FAILED",
            f"Failed to load rubric template '{template_name}': {message}",
            {"template_name": template_name},
        )


class JudgeUnavailableError(EvaluationError):
    status_code = 503

    def __init__(self) -> None:
        super().__init__("EVALUATION_JUDGE_UNAVAILABLE", "Judge model is unavailable")


class CooperationModeTooFewAgentsError(EvaluationError):
    status_code = 400

    def __init__(self) -> None:
        super().__init__(
            "EVALUATION_COOPERATION_TOO_FEW_AGENTS",
            "Cooperation mode requires at least two execution ids",
        )


class InsufficientGroupsError(EvaluationError):
    status_code = 400

    def __init__(self, group_attribute: str) -> None:
        super().__init__(
            "EVALUATION_FAIRNESS_INSUFFICIENT_GROUPS",
            "At least two sufficiently-sized groups are required",
            {"group_attribute": group_attribute},
        )


class FairnessRunFailedError(EvaluationError):
    status_code = 500

    def __init__(self, message: str) -> None:
        super().__init__("EVALUATION_FAIRNESS_RUN_FAILED", message)


class FairnessConfigError(EvaluationError):
    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__("EVALUATION_FAIRNESS_CONFIG_INVALID", message)
