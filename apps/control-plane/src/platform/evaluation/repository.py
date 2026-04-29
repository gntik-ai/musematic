from __future__ import annotations

from datetime import UTC, datetime
from platform.evaluation.models import (
    AbExperiment,
    ATEConfig,
    ATERun,
    BenchmarkCase,
    CalibrationRun,
    EvalSet,
    EvaluationRun,
    FairnessEvaluation,
    HumanAiGrade,
    JudgeVerdict,
    RobustnessTestRun,
    Rubric,
    RunStatus,
)
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


class EvaluationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert_fairness_evaluation_rows(
        self,
        rows: list[FairnessEvaluation],
    ) -> list[FairnessEvaluation]:
        self.session.add_all(rows)
        await self.session.flush()
        return rows

    async def get_fairness_evaluation_run(
        self,
        evaluation_run_id: UUID,
    ) -> list[FairnessEvaluation]:
        result = await self.session.execute(
            select(FairnessEvaluation)
            .where(FairnessEvaluation.evaluation_run_id == evaluation_run_id)
            .order_by(
                FairnessEvaluation.metric_name.asc(), FairnessEvaluation.group_attribute.asc()
            )
        )
        return list(result.scalars().all())

    async def get_latest_passing_fairness_evaluation(
        self,
        agent_id: UUID,
        agent_revision_id: str,
        staleness_cutoff: datetime,
    ) -> FairnessEvaluation | None:
        result = await self.session.execute(
            select(FairnessEvaluation)
            .where(
                FairnessEvaluation.agent_id == agent_id,
                FairnessEvaluation.agent_revision_id == agent_revision_id,
                FairnessEvaluation.passed.is_(True),
                FairnessEvaluation.computed_at >= staleness_cutoff,
            )
            .order_by(FairnessEvaluation.computed_at.desc(), FairnessEvaluation.id.desc())
        )
        return result.scalars().first()

    async def get_latest_passing_fairness_evaluation_any_age(
        self,
        agent_id: UUID,
        agent_revision_id: str,
    ) -> FairnessEvaluation | None:
        result = await self.session.execute(
            select(FairnessEvaluation)
            .where(
                FairnessEvaluation.agent_id == agent_id,
                FairnessEvaluation.agent_revision_id == agent_revision_id,
                FairnessEvaluation.passed.is_(True),
            )
            .order_by(FairnessEvaluation.computed_at.desc(), FairnessEvaluation.id.desc())
        )
        return result.scalars().first()

    async def create_eval_set(self, eval_set: EvalSet) -> EvalSet:
        self.session.add(eval_set)
        await self.session.flush()
        return eval_set

    async def get_eval_set(
        self, eval_set_id: UUID, workspace_id: UUID | None = None
    ) -> EvalSet | None:
        query = select(EvalSet).where(EvalSet.id == eval_set_id, EvalSet.deleted_at.is_(None))
        if workspace_id is not None:
            query = query.where(EvalSet.workspace_id == workspace_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_eval_sets(
        self,
        workspace_id: UUID,
        *,
        status: Any | None = None,
        page: int,
        page_size: int,
    ) -> tuple[list[EvalSet], int]:
        filters = [EvalSet.workspace_id == workspace_id, EvalSet.deleted_at.is_(None)]
        if status is not None:
            filters.append(EvalSet.status == status)
        total = await self.session.scalar(select(func.count()).select_from(EvalSet).where(*filters))
        result = await self.session.execute(
            select(EvalSet)
            .where(*filters)
            .order_by(EvalSet.created_at.desc(), EvalSet.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), int(total or 0)

    async def update_eval_set(self, eval_set: EvalSet, **fields: Any) -> EvalSet:
        for key, value in fields.items():
            setattr(eval_set, key, value)
        await self.session.flush()
        return eval_set

    async def soft_delete_eval_set(self, eval_set: EvalSet) -> EvalSet:
        eval_set.deleted_at = datetime.now(UTC)
        await self.session.flush()
        return eval_set

    async def count_benchmark_cases(self, eval_set_id: UUID) -> int:
        total = await self.session.scalar(
            select(func.count())
            .select_from(BenchmarkCase)
            .where(BenchmarkCase.eval_set_id == eval_set_id)
        )
        return int(total or 0)

    async def get_next_case_position(self, eval_set_id: UUID) -> int:
        current = await self.session.scalar(
            select(func.max(BenchmarkCase.position)).where(BenchmarkCase.eval_set_id == eval_set_id)
        )
        return int(current or -1) + 1

    async def create_benchmark_case(self, case: BenchmarkCase) -> BenchmarkCase:
        self.session.add(case)
        await self.session.flush()
        return case

    async def get_benchmark_case(
        self,
        case_id: UUID,
        *,
        eval_set_id: UUID | None = None,
    ) -> BenchmarkCase | None:
        query = select(BenchmarkCase).where(BenchmarkCase.id == case_id)
        if eval_set_id is not None:
            query = query.where(BenchmarkCase.eval_set_id == eval_set_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_benchmark_cases(
        self,
        eval_set_id: UUID,
        *,
        category: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[BenchmarkCase], int]:
        filters = [BenchmarkCase.eval_set_id == eval_set_id]
        if category is not None:
            filters.append(BenchmarkCase.category == category)
        total = await self.session.scalar(
            select(func.count()).select_from(BenchmarkCase).where(*filters)
        )
        result = await self.session.execute(
            select(BenchmarkCase)
            .where(*filters)
            .order_by(BenchmarkCase.position.asc(), BenchmarkCase.created_at.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), int(total or 0)

    async def list_all_benchmark_cases(self, eval_set_id: UUID) -> list[BenchmarkCase]:
        result = await self.session.execute(
            select(BenchmarkCase)
            .where(BenchmarkCase.eval_set_id == eval_set_id)
            .order_by(BenchmarkCase.position.asc(), BenchmarkCase.created_at.asc())
        )
        return list(result.scalars().all())

    async def delete_benchmark_case(self, case: BenchmarkCase) -> None:
        await self.session.delete(case)
        await self.session.flush()

    async def create_run(self, run: EvaluationRun) -> EvaluationRun:
        self.session.add(run)
        await self.session.flush()
        return run

    async def get_run(self, run_id: UUID, workspace_id: UUID | None = None) -> EvaluationRun | None:
        query: Select[tuple[EvaluationRun]] = (
            select(EvaluationRun)
            .where(EvaluationRun.id == run_id)
            .options(selectinload(EvaluationRun.verdicts))
        )
        if workspace_id is not None:
            query = query.where(EvaluationRun.workspace_id == workspace_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_runs(
        self,
        workspace_id: UUID,
        *,
        eval_set_id: UUID | None,
        agent_fqn: str | None,
        status: Any | None,
        page: int,
        page_size: int,
        allowed_ids: set[UUID] | None = None,
    ) -> tuple[list[EvaluationRun], int]:
        filters = [EvaluationRun.workspace_id == workspace_id]
        if eval_set_id is not None:
            filters.append(EvaluationRun.eval_set_id == eval_set_id)
        if agent_fqn is not None:
            filters.append(EvaluationRun.agent_fqn == agent_fqn)
        if status is not None:
            filters.append(EvaluationRun.status == status)
        if allowed_ids is not None:
            if not allowed_ids:
                return [], 0
            filters.append(EvaluationRun.id.in_(sorted(allowed_ids, key=str)))
        total = await self.session.scalar(
            select(func.count()).select_from(EvaluationRun).where(*filters)
        )
        result = await self.session.execute(
            select(EvaluationRun)
            .where(*filters)
            .order_by(EvaluationRun.created_at.desc(), EvaluationRun.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), int(total or 0)

    async def update_run(self, run: EvaluationRun, **fields: Any) -> EvaluationRun:
        for key, value in fields.items():
            setattr(run, key, value)
        await self.session.flush()
        return run

    async def create_verdict(self, verdict: JudgeVerdict) -> JudgeVerdict:
        self.session.add(verdict)
        await self.session.flush()
        return verdict

    async def get_verdict(self, verdict_id: UUID) -> JudgeVerdict | None:
        result = await self.session.execute(
            select(JudgeVerdict)
            .where(JudgeVerdict.id == verdict_id)
            .options(
                selectinload(JudgeVerdict.human_grade),
                selectinload(JudgeVerdict.run),
            )
        )
        return result.scalar_one_or_none()

    async def list_run_verdicts(
        self,
        run_id: UUID,
        *,
        passed: bool | None,
        status: Any | None,
        page: int,
        page_size: int,
    ) -> tuple[list[JudgeVerdict], int]:
        filters = [JudgeVerdict.run_id == run_id]
        if passed is not None:
            filters.append(JudgeVerdict.passed.is_(passed))
        if status is not None:
            filters.append(JudgeVerdict.status == status)
        total = await self.session.scalar(
            select(func.count()).select_from(JudgeVerdict).where(*filters)
        )
        result = await self.session.execute(
            select(JudgeVerdict)
            .where(*filters)
            .options(selectinload(JudgeVerdict.human_grade))
            .order_by(JudgeVerdict.created_at.asc(), JudgeVerdict.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), int(total or 0)

    async def list_verdicts_by_run(self, run_id: UUID) -> list[JudgeVerdict]:
        result = await self.session.execute(
            select(JudgeVerdict)
            .where(JudgeVerdict.run_id == run_id)
            .order_by(JudgeVerdict.created_at.asc(), JudgeVerdict.id.asc())
        )
        return list(result.scalars().all())

    async def get_run_score_array(self, run_id: UUID) -> list[float]:
        result = await self.session.execute(
            select(JudgeVerdict.overall_score).where(
                JudgeVerdict.run_id == run_id,
                JudgeVerdict.overall_score.is_not(None),
            )
        )
        return [float(value) for value in result.scalars().all() if value is not None]

    async def create_rubric(self, rubric: Rubric) -> Rubric:
        self.session.add(rubric)
        await self.session.flush()
        return rubric

    async def get_rubric(
        self,
        rubric_id: UUID,
        workspace_id: UUID | None = None,
    ) -> Rubric | None:
        query = select(Rubric).where(Rubric.id == rubric_id)
        if workspace_id is not None:
            query = query.where(
                or_(Rubric.workspace_id == workspace_id, Rubric.is_builtin.is_(True))
            )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_builtin_rubric_by_name(self, name: str) -> Rubric | None:
        result = await self.session.execute(
            select(Rubric).where(
                Rubric.name == name,
                Rubric.is_builtin.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_workspace_rubric_by_name(self, workspace_id: UUID, name: str) -> Rubric | None:
        result = await self.session.execute(
            select(Rubric).where(
                Rubric.workspace_id == workspace_id,
                Rubric.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def list_rubrics(
        self,
        workspace_id: UUID | None,
        *,
        status: Any | None,
        include_builtins: bool,
        page: int,
        page_size: int,
    ) -> tuple[list[Rubric], int]:
        filters: list[Any] = []
        if workspace_id is None:
            filters.append(Rubric.is_builtin.is_(True))
        elif include_builtins:
            filters.append(or_(Rubric.workspace_id == workspace_id, Rubric.is_builtin.is_(True)))
        else:
            filters.append(Rubric.workspace_id == workspace_id)
        if status is not None:
            filters.append(Rubric.status == status)
        total = await self.session.scalar(select(func.count()).select_from(Rubric).where(*filters))
        result = await self.session.execute(
            select(Rubric)
            .where(*filters)
            .order_by(Rubric.is_builtin.desc(), Rubric.name.asc(), Rubric.created_at.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), int(total or 0)

    async def update_rubric(self, rubric: Rubric, **fields: Any) -> Rubric:
        for key, value in fields.items():
            setattr(rubric, key, value)
        await self.session.flush()
        return rubric

    async def soft_delete_rubric(self, rubric: Rubric) -> Rubric:
        rubric.deleted_at = datetime.now(UTC)
        await self.session.flush()
        return rubric

    async def count_in_flight_rubric_references(self, rubric_id: UUID) -> int:
        total = await self.session.scalar(
            select(func.count())
            .select_from(EvaluationRun)
            .join(EvalSet, EvalSet.id == EvaluationRun.eval_set_id)
            .where(
                EvaluationRun.status == RunStatus.running,
                EvalSet.scorer_config.contains({"llm_judge": {"rubric_id": str(rubric_id)}}),
            )
        )
        return int(total or 0)

    async def create_calibration_run(self, run: CalibrationRun) -> CalibrationRun:
        self.session.add(run)
        await self.session.flush()
        return run

    async def get_calibration_run(self, run_id: UUID) -> CalibrationRun | None:
        result = await self.session.execute(
            select(CalibrationRun).where(CalibrationRun.id == run_id)
        )
        return result.scalar_one_or_none()

    async def update_calibration_run(self, run: CalibrationRun, **fields: Any) -> CalibrationRun:
        for key, value in fields.items():
            setattr(run, key, value)
        await self.session.flush()
        return run

    async def create_ab_experiment(self, experiment: AbExperiment) -> AbExperiment:
        self.session.add(experiment)
        await self.session.flush()
        return experiment

    async def get_ab_experiment(
        self,
        experiment_id: UUID,
        workspace_id: UUID | None = None,
    ) -> AbExperiment | None:
        query = select(AbExperiment).where(AbExperiment.id == experiment_id)
        if workspace_id is not None:
            query = query.where(AbExperiment.workspace_id == workspace_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def update_ab_experiment(self, experiment: AbExperiment, **fields: Any) -> AbExperiment:
        for key, value in fields.items():
            setattr(experiment, key, value)
        await self.session.flush()
        return experiment

    async def create_ate_config(self, config: ATEConfig) -> ATEConfig:
        self.session.add(config)
        await self.session.flush()
        return config

    async def get_ate_config(
        self, config_id: UUID, workspace_id: UUID | None = None
    ) -> ATEConfig | None:
        query = select(ATEConfig).where(ATEConfig.id == config_id, ATEConfig.deleted_at.is_(None))
        if workspace_id is not None:
            query = query.where(ATEConfig.workspace_id == workspace_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_ate_configs(
        self,
        workspace_id: UUID,
        *,
        page: int,
        page_size: int,
    ) -> tuple[list[ATEConfig], int]:
        filters = [ATEConfig.workspace_id == workspace_id, ATEConfig.deleted_at.is_(None)]
        total = await self.session.scalar(
            select(func.count()).select_from(ATEConfig).where(*filters)
        )
        result = await self.session.execute(
            select(ATEConfig)
            .where(*filters)
            .order_by(ATEConfig.created_at.desc(), ATEConfig.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), int(total or 0)

    async def update_ate_config(self, config: ATEConfig, **fields: Any) -> ATEConfig:
        for key, value in fields.items():
            setattr(config, key, value)
        await self.session.flush()
        return config

    async def soft_delete_ate_config(self, config: ATEConfig) -> ATEConfig:
        config.deleted_at = datetime.now(UTC)
        await self.session.flush()
        return config

    async def create_ate_run(self, run: ATERun) -> ATERun:
        self.session.add(run)
        await self.session.flush()
        return run

    async def get_ate_run(self, run_id: UUID, workspace_id: UUID | None = None) -> ATERun | None:
        query = select(ATERun).where(ATERun.id == run_id)
        if workspace_id is not None:
            query = query.where(ATERun.workspace_id == workspace_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_ate_runs(
        self,
        ate_config_id: UUID,
        *,
        page: int,
        page_size: int,
    ) -> tuple[list[ATERun], int]:
        filters = [ATERun.ate_config_id == ate_config_id]
        total = await self.session.scalar(select(func.count()).select_from(ATERun).where(*filters))
        result = await self.session.execute(
            select(ATERun)
            .where(*filters)
            .order_by(ATERun.created_at.desc(), ATERun.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), int(total or 0)

    async def update_ate_run(self, run: ATERun, **fields: Any) -> ATERun:
        for key, value in fields.items():
            setattr(run, key, value)
        await self.session.flush()
        return run

    async def create_robustness_run(self, run: RobustnessTestRun) -> RobustnessTestRun:
        self.session.add(run)
        await self.session.flush()
        return run

    async def get_robustness_run(
        self,
        run_id: UUID,
        workspace_id: UUID | None = None,
    ) -> RobustnessTestRun | None:
        query = select(RobustnessTestRun).where(RobustnessTestRun.id == run_id)
        if workspace_id is not None:
            query = query.where(RobustnessTestRun.workspace_id == workspace_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_active_robustness_runs_by_agent(self, agent_fqn: str) -> list[RobustnessTestRun]:
        result = await self.session.execute(
            select(RobustnessTestRun).where(
                RobustnessTestRun.agent_fqn == agent_fqn,
                RobustnessTestRun.status.in_([RunStatus.pending, RunStatus.running]),
            )
        )
        return list(result.scalars().all())

    async def list_pending_robustness_runs(
        self,
        *,
        limit: int = 20,
    ) -> list[RobustnessTestRun]:
        result = await self.session.execute(
            select(RobustnessTestRun)
            .where(RobustnessTestRun.status == RunStatus.pending)
            .order_by(RobustnessTestRun.created_at.asc(), RobustnessTestRun.id.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def update_robustness_run(
        self,
        run: RobustnessTestRun,
        **fields: Any,
    ) -> RobustnessTestRun:
        for key, value in fields.items():
            setattr(run, key, value)
        await self.session.flush()
        return run

    async def create_human_grade(self, grade: HumanAiGrade) -> HumanAiGrade:
        self.session.add(grade)
        await self.session.flush()
        return grade

    async def get_human_grade(self, grade_id: UUID) -> HumanAiGrade | None:
        result = await self.session.execute(select(HumanAiGrade).where(HumanAiGrade.id == grade_id))
        return result.scalar_one_or_none()

    async def get_human_grade_by_verdict(self, verdict_id: UUID) -> HumanAiGrade | None:
        result = await self.session.execute(
            select(HumanAiGrade).where(HumanAiGrade.verdict_id == verdict_id)
        )
        return result.scalar_one_or_none()

    async def update_human_grade(self, grade: HumanAiGrade, **fields: Any) -> HumanAiGrade:
        for key, value in fields.items():
            setattr(grade, key, value)
        await self.session.flush()
        return grade

    async def get_review_progress(self, run_id: UUID) -> dict[str, int]:
        total = await self.session.scalar(
            select(func.count()).select_from(JudgeVerdict).where(JudgeVerdict.run_id == run_id)
        )
        reviewed = await self.session.scalar(
            select(func.count())
            .select_from(JudgeVerdict)
            .join(HumanAiGrade, HumanAiGrade.verdict_id == JudgeVerdict.id)
            .where(JudgeVerdict.run_id == run_id)
        )
        overridden = await self.session.scalar(
            select(func.count())
            .select_from(JudgeVerdict)
            .join(HumanAiGrade, HumanAiGrade.verdict_id == JudgeVerdict.id)
            .where(
                JudgeVerdict.run_id == run_id,
                HumanAiGrade.override_score.is_not(None),
            )
        )
        total_count = int(total or 0)
        reviewed_count = int(reviewed or 0)
        overridden_count = int(overridden or 0)
        return {
            "total_verdicts": total_count,
            "pending_review": max(0, total_count - reviewed_count),
            "reviewed": reviewed_count,
            "overridden": overridden_count,
        }

    async def get_latest_completed_run_score(
        self,
        *,
        workspace_id: UUID,
        agent_fqn: str,
        eval_set_id: UUID,
    ) -> float | None:
        result = await self.session.execute(
            select(EvaluationRun.aggregate_score)
            .where(
                EvaluationRun.workspace_id == workspace_id,
                EvaluationRun.agent_fqn == agent_fqn,
                EvaluationRun.eval_set_id == eval_set_id,
                EvaluationRun.status == RunStatus.completed,
            )
            .order_by(EvaluationRun.completed_at.desc(), EvaluationRun.created_at.desc())
            .limit(1)
        )
        score = result.scalar_one_or_none()
        return float(score) if score is not None else None
