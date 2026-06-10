from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum

from futures_mvp.domain.enums import ExecutionTarget
from futures_mvp.domain.models import ExecutionCommand
from futures_mvp.modules.sim_trading.job import (
    SimJobConfig,
    SimJobResult,
    SimJobStatus,
)


class SimSessionStatus(StrEnum):
    DISABLED = "DISABLED"
    DRY_RUN_COMPLETED = "DRY_RUN_COMPLETED"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    CONFLICT = "CONFLICT"
    ERROR = "ERROR"


@dataclass(frozen=True)
class SimSessionConfig:
    session_name: str
    runtime_id: str
    trading_day: date
    account_id: str
    dry_run: bool = True
    max_commands: int = 1
    require_clean_start: bool = True
    stop_on_conflict: bool = True
    stop_on_first_error: bool = True
    apply_confirmed: bool = False

    def __post_init__(self) -> None:
        if not self.session_name:
            raise ValueError("sim session_name is required")
        if not self.runtime_id:
            raise ValueError("sim runtime_id is required")
        if not self.account_id:
            raise ValueError("sim account_id is required")
        if self.max_commands < 1:
            raise ValueError("sim max_commands must be >= 1")


@dataclass(frozen=True)
class SimSessionResult:
    session_name: str
    status: SimSessionStatus
    reason: str | None = None
    job_results: tuple[SimJobResult, ...] = ()
    processed_commands: int = 0
    duplicate_count: int = 0
    conflict_count: int = 0
    error_count: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None


SimCommandProvider = Callable[[], Sequence[ExecutionCommand]]
SimRuntimeJobFactory = Callable[
    [SimJobConfig, Sequence[ExecutionCommand]],
    Callable[[], SimJobResult],
]


class SimLocalSession:
    def __init__(
        self,
        *,
        config: SimSessionConfig,
        job_factory: SimRuntimeJobFactory,
        commands: Sequence[ExecutionCommand] | None = None,
        command_provider: SimCommandProvider | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self._job_factory = job_factory
        self._commands = tuple(commands) if commands is not None else None
        self._command_provider = command_provider
        self._clock = clock or (lambda: datetime.now(UTC))

    def run(self) -> SimSessionResult:
        started_at = self._clock()
        blocked = self._blocked_reason()
        if blocked is not None:
            return self._result(SimSessionStatus.BLOCKED, started_at, reason=blocked)

        try:
            commands = self._load_commands()
        except Exception as exc:  # noqa: BLE001
            return self._result(SimSessionStatus.ERROR, started_at, reason=str(exc))

        command_blocked = _command_blocked_reason(commands)
        if command_blocked is not None:
            return self._result(
                SimSessionStatus.BLOCKED,
                started_at,
                reason=command_blocked,
            )

        selected = commands[: self._config.max_commands]
        job_config = SimJobConfig(
            enabled=True,
            job_name=self._config.session_name,
            dry_run=self._config.dry_run,
            scheduler_enabled=True,
            max_commands_per_run=self._config.max_commands,
            stop_on_conflict=self._config.stop_on_conflict,
            stop_on_first_error=self._config.stop_on_first_error,
            apply_confirmed=self._config.apply_confirmed,
        )
        job = self._job_factory(job_config, selected)
        job_result = job()
        return self._from_job_results(started_at, (job_result,))

    def _blocked_reason(self) -> str | None:
        if self._commands is not None and self._command_provider is not None:
            return "sim session accepts either commands or command_provider, not both"
        if self._commands is None and self._command_provider is None:
            return "sim session requires typed commands or command_provider"
        if not self._config.dry_run and not self._config.apply_confirmed:
            return "sim apply session requires explicit apply_confirmed"
        return None

    def _load_commands(self) -> tuple[ExecutionCommand, ...]:
        if self._commands is not None:
            return self._commands
        assert self._command_provider is not None
        return tuple(self._command_provider())

    def _from_job_results(
        self,
        started_at: datetime,
        job_results: tuple[SimJobResult, ...],
    ) -> SimSessionResult:
        status = _session_status(job_results, self._config.dry_run)
        return self._result(
            status,
            started_at,
            job_results=job_results,
            processed_commands=sum(result.processed_command_count for result in job_results),
            duplicate_count=sum(
                1 for result in job_results if result.status is SimJobStatus.DUPLICATE
            ),
            conflict_count=sum(result.conflict_count for result in job_results),
            error_count=sum(result.error_count for result in job_results),
            reason=next((result.reason for result in job_results if result.reason), None),
        )

    def _result(
        self,
        status: SimSessionStatus,
        started_at: datetime,
        *,
        reason: str | None = None,
        job_results: tuple[SimJobResult, ...] = (),
        processed_commands: int = 0,
        duplicate_count: int = 0,
        conflict_count: int = 0,
        error_count: int = 0,
    ) -> SimSessionResult:
        return SimSessionResult(
            session_name=self._config.session_name,
            status=status,
            reason=reason,
            job_results=job_results,
            processed_commands=processed_commands,
            duplicate_count=duplicate_count,
            conflict_count=conflict_count,
            error_count=error_count,
            started_at=started_at,
            finished_at=self._clock(),
        )


def run_sim_local_session(
    *,
    config: SimSessionConfig,
    job_factory: SimRuntimeJobFactory,
    commands: Sequence[ExecutionCommand] | None = None,
    command_provider: SimCommandProvider | None = None,
    clock: Callable[[], datetime] | None = None,
) -> SimSessionResult:
    return SimLocalSession(
        config=config,
        job_factory=job_factory,
        commands=commands,
        command_provider=command_provider,
        clock=clock,
    ).run()


def _command_blocked_reason(commands: tuple[ExecutionCommand, ...]) -> str | None:
    if not commands:
        return "sim session requires at least one typed ExecutionCommand"
    for command in commands:
        if not isinstance(command, ExecutionCommand):
            return "sim session command source must return typed ExecutionCommand"
        if command.execution_target is not ExecutionTarget.MOCK:
            return "sim session supports ExecutionTarget.MOCK only"
    return None


def _session_status(
    job_results: tuple[SimJobResult, ...],
    dry_run: bool,
) -> SimSessionStatus:
    if not job_results:
        return SimSessionStatus.BLOCKED
    if any(result.status is SimJobStatus.ERROR for result in job_results):
        return SimSessionStatus.ERROR
    if any(result.status is SimJobStatus.CONFLICT for result in job_results):
        return SimSessionStatus.CONFLICT
    if any(result.status is SimJobStatus.BLOCKED for result in job_results):
        return SimSessionStatus.BLOCKED
    if all(result.status is SimJobStatus.DISABLED for result in job_results):
        return SimSessionStatus.DISABLED
    if dry_run and all(result.status is SimJobStatus.DRY_RUN for result in job_results):
        return SimSessionStatus.DRY_RUN_COMPLETED
    return SimSessionStatus.COMPLETED
