from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum

from futures_mvp.domain.enums import ExecutionTarget
from futures_mvp.domain.models import ExecutionCommand
from futures_mvp.modules.paper_trading.job import (
    PaperJobConfig,
    PaperJobResult,
    PaperJobStatus,
)


class PaperSessionStatus(StrEnum):
    DISABLED = "DISABLED"
    DRY_RUN_COMPLETED = "DRY_RUN_COMPLETED"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    CONFLICT = "CONFLICT"
    ERROR = "ERROR"


@dataclass(frozen=True)
class PaperSessionConfig:
    session_name: str
    runtime_id: str
    trading_day: date
    account_id: str
    dry_run: bool = True
    max_commands: int = 1
    require_clean_start: bool = True
    stop_on_first_error: bool = True
    stop_on_conflict: bool = True
    apply_confirmed: bool = False

    def __post_init__(self) -> None:
        if not self.session_name:
            raise ValueError("paper session_name is required")
        if not self.runtime_id:
            raise ValueError("paper runtime_id is required")
        if not self.account_id:
            raise ValueError("paper account_id is required")
        if self.max_commands < 1:
            raise ValueError("paper max_commands must be >= 1")


@dataclass(frozen=True)
class PaperSessionResult:
    session_name: str
    status: PaperSessionStatus
    reason: str | None = None
    job_results: tuple[PaperJobResult, ...] = ()
    processed_commands: int = 0
    duplicate_count: int = 0
    conflict_count: int = 0
    error_count: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None


PaperCommandProvider = Callable[[], Sequence[ExecutionCommand]]
PaperRuntimeJobFactory = Callable[
    [PaperJobConfig, Sequence[ExecutionCommand]],
    Callable[[], PaperJobResult],
]


class PaperLocalSession:
    def __init__(
        self,
        *,
        config: PaperSessionConfig,
        job_factory: PaperRuntimeJobFactory,
        commands: Sequence[ExecutionCommand] | None = None,
        command_provider: PaperCommandProvider | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self._job_factory = job_factory
        self._commands = tuple(commands) if commands is not None else None
        self._command_provider = command_provider
        self._clock = clock or (lambda: datetime.now(UTC))

    def run(self) -> PaperSessionResult:
        started_at = self._clock()
        blocked = self._blocked_reason()
        if blocked is not None:
            return self._result(PaperSessionStatus.BLOCKED, started_at, reason=blocked)

        try:
            commands = self._load_commands()
        except Exception as exc:  # noqa: BLE001
            return self._result(PaperSessionStatus.ERROR, started_at, reason=str(exc))

        command_blocked = _command_blocked_reason(commands)
        if command_blocked is not None:
            return self._result(
                PaperSessionStatus.BLOCKED,
                started_at,
                reason=command_blocked,
            )

        selected = commands[: self._config.max_commands]
        job_config = PaperJobConfig(
            enabled=True,
            job_name=self._config.session_name,
            dry_run=self._config.dry_run,
            scheduler_enabled=True,
            max_commands_per_run=self._config.max_commands,
            stop_on_first_error=self._config.stop_on_first_error,
            stop_on_conflict=self._config.stop_on_conflict,
        )
        job = self._job_factory(job_config, selected)
        job_result = job()
        return self._from_job_results(started_at, (job_result,))

    def _blocked_reason(self) -> str | None:
        if self._commands is not None and self._command_provider is not None:
            return "paper session accepts either commands or command_provider, not both"
        if self._commands is None and self._command_provider is None:
            return "paper session requires typed commands or command_provider"
        if not self._config.dry_run and not self._config.apply_confirmed:
            return "paper apply session requires explicit apply_confirmed"
        return None

    def _load_commands(self) -> tuple[ExecutionCommand, ...]:
        if self._commands is not None:
            return self._commands
        assert self._command_provider is not None
        return tuple(self._command_provider())

    def _from_job_results(
        self,
        started_at: datetime,
        job_results: tuple[PaperJobResult, ...],
    ) -> PaperSessionResult:
        status = _session_status(job_results, self._config.dry_run)
        return self._result(
            status,
            started_at,
            job_results=job_results,
            processed_commands=sum(result.processed_command_count for result in job_results),
            duplicate_count=sum(
                1 for result in job_results if result.status is PaperJobStatus.DUPLICATE
            ),
            conflict_count=sum(result.conflict_count for result in job_results),
            error_count=sum(result.error_count for result in job_results),
            reason=next((result.reason for result in job_results if result.reason), None),
        )

    def _result(
        self,
        status: PaperSessionStatus,
        started_at: datetime,
        *,
        reason: str | None = None,
        job_results: tuple[PaperJobResult, ...] = (),
        processed_commands: int = 0,
        duplicate_count: int = 0,
        conflict_count: int = 0,
        error_count: int = 0,
    ) -> PaperSessionResult:
        return PaperSessionResult(
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


def run_paper_local_session(
    *,
    config: PaperSessionConfig,
    job_factory: PaperRuntimeJobFactory,
    commands: Sequence[ExecutionCommand] | None = None,
    command_provider: PaperCommandProvider | None = None,
    clock: Callable[[], datetime] | None = None,
) -> PaperSessionResult:
    return PaperLocalSession(
        config=config,
        job_factory=job_factory,
        commands=commands,
        command_provider=command_provider,
        clock=clock,
    ).run()


def _command_blocked_reason(commands: tuple[ExecutionCommand, ...]) -> str | None:
    if not commands:
        return "paper session requires at least one typed ExecutionCommand"
    for command in commands:
        if not isinstance(command, ExecutionCommand):
            return "paper session command source must return typed ExecutionCommand"
        if command.execution_target is not ExecutionTarget.MOCK:
            return "paper session supports ExecutionTarget.MOCK only"
    return None


def _session_status(
    job_results: tuple[PaperJobResult, ...],
    dry_run: bool,
) -> PaperSessionStatus:
    if not job_results:
        return PaperSessionStatus.BLOCKED
    if any(result.status is PaperJobStatus.ERROR for result in job_results):
        return PaperSessionStatus.ERROR
    if any(result.status is PaperJobStatus.CONFLICT for result in job_results):
        return PaperSessionStatus.CONFLICT
    if any(result.status is PaperJobStatus.BLOCKED for result in job_results):
        return PaperSessionStatus.BLOCKED
    if all(result.status is PaperJobStatus.DISABLED for result in job_results):
        return PaperSessionStatus.DISABLED
    if dry_run and all(result.status is PaperJobStatus.DRY_RUN for result in job_results):
        return PaperSessionStatus.DRY_RUN_COMPLETED
    return PaperSessionStatus.COMPLETED
