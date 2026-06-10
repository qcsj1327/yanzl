from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from futures_mvp.modules.ops_safety import RolloutMode, evaluate_capital_controls
from futures_mvp.modules.ops_safety.kill_switch import (
    evaluate_replay_gate,
    evaluate_scheduler_gate,
)
from futures_mvp.modules.paper_trading.coordinator import (
    PaperRunContext,
    PaperRunResult,
    PaperRunStatus,
    PaperTradingCoordinator,
)


class PaperJobStatus(StrEnum):
    DISABLED = "DISABLED"
    BLOCKED = "BLOCKED"
    DRY_RUN = "DRY_RUN"
    COMPLETED = "COMPLETED"
    DUPLICATE = "DUPLICATE"
    CONFLICT = "CONFLICT"
    ERROR = "ERROR"


@dataclass(frozen=True)
class PaperJobConfig:
    enabled: bool = False
    job_name: str = "paper_runtime_job"
    rollout_mode: RolloutMode = RolloutMode.PAPER
    dry_run: bool = True
    scheduler_enabled: bool = False
    max_commands_per_run: int = 1
    stop_on_first_error: bool = True
    stop_on_conflict: bool = True
    require_migration_ready: bool = True
    require_capital_controls: bool = True
    require_scheduler_not_paused: bool = True
    require_replay_not_paused: bool = True

    def __post_init__(self) -> None:
        if not self.job_name:
            raise ValueError("paper job_name is required")
        if self.max_commands_per_run < 1:
            raise ValueError("max_commands_per_run must be >= 1")


@dataclass(frozen=True)
class PaperJobResult:
    job_name: str
    status: PaperJobStatus
    reason: str | None = None
    paper_run_result: PaperRunResult | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    processed_command_count: int = 0
    conflict_count: int = 0
    error_count: int = 0


PaperRunContextProvider = Callable[[], Sequence[PaperRunContext]]


class PaperRuntimeJob:
    def __init__(
        self,
        *,
        config: PaperJobConfig,
        coordinator: PaperTradingCoordinator | None,
        context_provider: PaperRunContextProvider,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self._coordinator = coordinator
        self._context_provider = context_provider
        self._clock = clock or (lambda: datetime.now(UTC))

    def __call__(self) -> PaperJobResult:
        started_at = self._clock()
        config = self._config
        if not config.enabled:
            return self._result(
                PaperJobStatus.DISABLED,
                started_at,
                reason="paper job is disabled",
            )
        if config.rollout_mode is not RolloutMode.PAPER:
            return self._result(
                PaperJobStatus.BLOCKED,
                started_at,
                reason="paper job requires RolloutMode.PAPER",
            )
        if not config.scheduler_enabled:
            return self._result(
                PaperJobStatus.BLOCKED,
                started_at,
                reason="scheduler is disabled",
            )
        if self._coordinator is None:
            return self._result(
                PaperJobStatus.BLOCKED,
                started_at,
                reason="paper coordinator is not wired",
            )

        try:
            contexts = tuple(self._context_provider())[: config.max_commands_per_run]
        except Exception as exc:  # noqa: BLE001
            return self._result(PaperJobStatus.ERROR, started_at, reason=str(exc))

        blocked_reason = self._blocked_reason(contexts)
        if blocked_reason is not None:
            return self._result(PaperJobStatus.BLOCKED, started_at, reason=blocked_reason)
        if config.dry_run:
            return self._result(
                PaperJobStatus.DRY_RUN,
                started_at,
                reason="paper job dry-run",
                processed_command_count=len(contexts),
            )

        processed = 0
        conflicts = 0
        errors = 0
        last_result: PaperRunResult | None = None
        final_status = PaperJobStatus.COMPLETED

        for context in contexts:
            run_result = self._coordinator.run(context)
            processed += 1
            last_result = run_result
            mapped_status = _map_run_status(run_result.status)
            if mapped_status is PaperJobStatus.CONFLICT:
                conflicts += 1
                final_status = PaperJobStatus.CONFLICT
                if config.stop_on_conflict:
                    break
            elif mapped_status is PaperJobStatus.ERROR:
                errors += 1
                final_status = PaperJobStatus.ERROR
                if config.stop_on_first_error:
                    break
            elif (
                mapped_status is PaperJobStatus.DUPLICATE
                and final_status is PaperJobStatus.COMPLETED
            ):
                final_status = PaperJobStatus.DUPLICATE

        return self._result(
            final_status,
            started_at,
            paper_run_result=last_result,
            processed_command_count=processed,
            conflict_count=conflicts,
            error_count=errors,
        )

    def _blocked_reason(self, contexts: tuple[PaperRunContext, ...]) -> str | None:
        if not contexts:
            return None
        for context in contexts:
            if context.rollout_mode is not RolloutMode.PAPER:
                return "paper run context requires RolloutMode.PAPER"
            if context.safety_config.rollout.mode is not RolloutMode.PAPER:
                return "SafetyConfig rollout mode must be PAPER"
            if self._config.require_migration_ready and not context.migration.compatible:
                return context.migration.reason or "migration readiness is incompatible"
            if self._config.require_scheduler_not_paused:
                scheduler_gate = evaluate_scheduler_gate(context.safety_config)
                if not scheduler_gate.allowed:
                    return scheduler_gate.reason
            if self._config.require_replay_not_paused:
                replay_gate = evaluate_replay_gate(context.safety_config)
                if not replay_gate.allowed:
                    return replay_gate.reason
            if self._config.require_capital_controls:
                capital_decision = evaluate_capital_controls(
                    context.safety_config,
                    context.capital_control_context,
                )
                if not capital_decision.passed:
                    return capital_decision.reason
        return None

    def _result(
        self,
        status: PaperJobStatus,
        started_at: datetime,
        *,
        reason: str | None = None,
        paper_run_result: PaperRunResult | None = None,
        processed_command_count: int = 0,
        conflict_count: int = 0,
        error_count: int = 0,
    ) -> PaperJobResult:
        return PaperJobResult(
            job_name=self._config.job_name,
            status=status,
            reason=reason,
            paper_run_result=paper_run_result,
            started_at=started_at,
            finished_at=self._clock(),
            processed_command_count=processed_command_count,
            conflict_count=conflict_count,
            error_count=error_count,
        )


def _map_run_status(status: PaperRunStatus) -> PaperJobStatus:
    if status is PaperRunStatus.DUPLICATE:
        return PaperJobStatus.DUPLICATE
    if status is PaperRunStatus.CONFLICT:
        return PaperJobStatus.CONFLICT
    if status in {
        PaperRunStatus.ERROR,
        PaperRunStatus.REJECTED_NO_REPORT,
        PaperRunStatus.REJECTED_NON_PAPER_MODE,
        PaperRunStatus.REJECTED_SAFETY_GATE,
        PaperRunStatus.REJECTED_CAPITAL_CONTROL,
    }:
        return PaperJobStatus.ERROR
    return PaperJobStatus.COMPLETED
