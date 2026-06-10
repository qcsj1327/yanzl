from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from futures_mvp.domain.enums import ExecutionTarget
from futures_mvp.modules.ops_safety import RolloutMode, evaluate_capital_controls
from futures_mvp.modules.ops_safety.kill_switch import (
    evaluate_replay_gate,
    evaluate_scheduler_gate,
)
from futures_mvp.modules.sim_trading.coordinator import (
    SimRunContext,
    SimRunResult,
    SimRunStatus,
    SimTradingCoordinator,
)


class SimJobStatus(StrEnum):
    DISABLED = "DISABLED"
    DRY_RUN = "DRY_RUN"
    COMPLETED = "COMPLETED"
    DUPLICATE = "DUPLICATE"
    BLOCKED = "BLOCKED"
    CONFLICT = "CONFLICT"
    ERROR = "ERROR"


@dataclass(frozen=True)
class SimJobConfig:
    enabled: bool = False
    job_name: str = "sim_runtime_job"
    rollout_mode: RolloutMode = RolloutMode.SIM
    dry_run: bool = True
    scheduler_enabled: bool = False
    max_commands_per_run: int = 1
    stop_on_conflict: bool = True
    stop_on_first_error: bool = True
    require_migration_ready: bool = True
    require_capital_controls: bool = True
    require_scheduler_not_paused: bool = True
    require_replay_not_paused: bool = True
    apply_confirmed: bool = False

    def __post_init__(self) -> None:
        if not self.job_name:
            raise ValueError("sim job_name is required")
        if self.max_commands_per_run < 1:
            raise ValueError("max_commands_per_run must be >= 1")


@dataclass(frozen=True)
class SimJobResult:
    job_name: str
    status: SimJobStatus
    reason: str | None = None
    sim_run_result: SimRunResult | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    processed_command_count: int = 0
    conflict_count: int = 0
    error_count: int = 0


SimRunContextProvider = Callable[[], Sequence[SimRunContext]]


class SimRuntimeJob:
    def __init__(
        self,
        *,
        config: SimJobConfig,
        coordinator: SimTradingCoordinator | None,
        context_provider: SimRunContextProvider,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self._coordinator = coordinator
        self._context_provider = context_provider
        self._clock = clock or (lambda: datetime.now(UTC))

    def __call__(self) -> SimJobResult:
        started_at = self._clock()
        config = self._config
        if not config.enabled:
            return self._result(
                SimJobStatus.DISABLED,
                started_at,
                reason="sim job is disabled",
            )
        if config.rollout_mode is not RolloutMode.SIM:
            return self._result(
                SimJobStatus.BLOCKED,
                started_at,
                reason="sim job requires RolloutMode.SIM",
            )
        if not config.scheduler_enabled:
            return self._result(
                SimJobStatus.BLOCKED,
                started_at,
                reason="scheduler is disabled",
            )
        if not config.dry_run and not config.apply_confirmed:
            return self._result(
                SimJobStatus.BLOCKED,
                started_at,
                reason="sim apply requires explicit apply_confirmed",
            )
        if self._coordinator is None:
            return self._result(
                SimJobStatus.BLOCKED,
                started_at,
                reason="sim coordinator is not wired",
            )

        try:
            contexts = tuple(self._context_provider())[: config.max_commands_per_run]
        except Exception as exc:  # noqa: BLE001
            return self._result(SimJobStatus.ERROR, started_at, reason=str(exc))

        blocked_reason = self._blocked_reason(contexts)
        if blocked_reason is not None:
            return self._result(SimJobStatus.BLOCKED, started_at, reason=blocked_reason)
        if config.dry_run:
            return self._result(
                SimJobStatus.DRY_RUN,
                started_at,
                reason="sim job dry-run",
                processed_command_count=len(contexts),
            )

        processed = 0
        conflicts = 0
        errors = 0
        last_result: SimRunResult | None = None
        final_status = SimJobStatus.COMPLETED

        for context in contexts:
            run_result = self._coordinator.run(context)
            processed += 1
            last_result = run_result
            mapped_status = _map_run_status(run_result.status)
            if mapped_status is SimJobStatus.CONFLICT:
                conflicts += 1
                final_status = SimJobStatus.CONFLICT
                if config.stop_on_conflict:
                    break
            elif mapped_status is SimJobStatus.ERROR:
                errors += 1
                final_status = SimJobStatus.ERROR
                if config.stop_on_first_error:
                    break
            elif (
                mapped_status is SimJobStatus.DUPLICATE
                and final_status is SimJobStatus.COMPLETED
            ):
                final_status = SimJobStatus.DUPLICATE

        return self._result(
            final_status,
            started_at,
            sim_run_result=last_result,
            processed_command_count=processed,
            conflict_count=conflicts,
            error_count=errors,
        )

    def _blocked_reason(self, contexts: tuple[SimRunContext, ...]) -> str | None:
        if not contexts:
            return None
        for context in contexts:
            reason = _context_blocked_reason(context, self._config)
            if reason is not None:
                return reason
        return None

    def _result(
        self,
        status: SimJobStatus,
        started_at: datetime,
        *,
        reason: str | None = None,
        sim_run_result: SimRunResult | None = None,
        processed_command_count: int = 0,
        conflict_count: int = 0,
        error_count: int = 0,
    ) -> SimJobResult:
        return SimJobResult(
            job_name=self._config.job_name,
            status=status,
            reason=reason,
            sim_run_result=sim_run_result,
            started_at=started_at,
            finished_at=self._clock(),
            processed_command_count=processed_command_count,
            conflict_count=conflict_count,
            error_count=error_count,
        )


def _context_blocked_reason(context: SimRunContext, config: SimJobConfig) -> str | None:
    if context.rollout_mode is not RolloutMode.SIM:
        return "sim run context requires RolloutMode.SIM"
    if context.safety_config.rollout.mode is not RolloutMode.SIM:
        return "SafetyConfig rollout mode must be SIM"
    if context.command.execution_target is not ExecutionTarget.MOCK:
        return "sim job supports ExecutionTarget.MOCK only"
    if context.operator_approval is None:
        return "operator approval is required"
    if context.operator_approval.environment != "sim":
        return "operator approval environment mismatch"
    if context.operator_approval.account_id != context.account_id:
        return "operator approval account mismatch"
    if context.operator_approval.adapter_target != "mock":
        return "operator approval adapter target mismatch"
    if context.operator_approval.allowed_stage != "sim_trading":
        return "operator approval stage mismatch"
    if context.operator_approval.command_surface != context.command.command_type.value:
        return "operator approval command surface mismatch"
    if not context.runtime_ready:
        return "runtime is not READY"
    if config.require_migration_ready and not context.migration.compatible:
        return context.migration.reason or "migration readiness is incompatible"
    if _has_live_gate_enabled(context):
        return "SIM runtime forbids live credentials and live apply"
    if context.unresolved_critical_incidents:
        return "unresolved critical incidents are present"
    if config.require_scheduler_not_paused:
        scheduler_gate = evaluate_scheduler_gate(context.safety_config)
        if not scheduler_gate.allowed:
            return scheduler_gate.reason
    if config.require_replay_not_paused:
        replay_gate = evaluate_replay_gate(context.safety_config)
        if not replay_gate.allowed:
            return replay_gate.reason
    if config.require_capital_controls:
        capital_decision = evaluate_capital_controls(
            context.safety_config,
            context.capital_control_context,
        )
        if not capital_decision.passed:
            return capital_decision.reason
    return None


def _has_live_gate_enabled(context: SimRunContext) -> bool:
    live_gate = context.safety_config.live_gate
    return (
        live_gate.broker_enabled
        or live_gate.live_submit_enabled
        or live_gate.explicit_live_flag
        or live_gate.broker_credentials_handle is not None
    )


def _map_run_status(status: SimRunStatus) -> SimJobStatus:
    if status is SimRunStatus.DUPLICATE:
        return SimJobStatus.DUPLICATE
    if status is SimRunStatus.CONFLICT:
        return SimJobStatus.CONFLICT
    if status in {
        SimRunStatus.ERROR,
        SimRunStatus.REJECTED_NO_REPORT,
        SimRunStatus.REJECTED_NON_SIM_MODE,
        SimRunStatus.REJECTED_SAFETY_GATE,
        SimRunStatus.REJECTED_CAPITAL_CONTROL,
        SimRunStatus.REJECTED_UNSUPPORTED_TARGET,
    }:
        return SimJobStatus.ERROR
    return SimJobStatus.COMPLETED
