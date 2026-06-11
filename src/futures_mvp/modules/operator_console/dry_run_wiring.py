from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from futures_mvp.domain.models import ExecutionCommand
from futures_mvp.modules.operator_console.actions import (
    DryRunActionResult,
    DryRunProvider,
)
from futures_mvp.modules.paper_trading.session import (
    PaperCommandProvider,
    PaperLocalSession,
    PaperRuntimeJobFactory,
    PaperSessionConfig,
    PaperSessionResult,
)
from futures_mvp.modules.sim_trading.session import (
    SimCommandProvider,
    SimLocalSession,
    SimRuntimeJobFactory,
    SimSessionConfig,
    SimSessionResult,
)

MOCK_TARGET = "MOCK only"


class PaperSessionRunner(Protocol):
    def run(self) -> PaperSessionResult: ...


class SimSessionRunner(Protocol):
    def run(self) -> SimSessionResult: ...


PaperSessionFactory = Callable[..., PaperSessionRunner]
SimSessionFactory = Callable[..., SimSessionRunner]


@dataclass(frozen=True)
class PaperDryRunWiring:
    config: PaperSessionConfig | None = None
    job_factory: PaperRuntimeJobFactory | None = None
    commands: Sequence[ExecutionCommand] | None = None
    command_provider: PaperCommandProvider | None = None
    session_factory: PaperSessionFactory = PaperLocalSession
    target: str = MOCK_TARGET
    apply_requested: bool = False


@dataclass(frozen=True)
class SimDryRunWiring:
    config: SimSessionConfig | None = None
    job_factory: SimRuntimeJobFactory | None = None
    commands: Sequence[ExecutionCommand] | None = None
    command_provider: SimCommandProvider | None = None
    session_factory: SimSessionFactory = SimLocalSession
    target: str = MOCK_TARGET
    apply_requested: bool = False


def create_paper_dry_run_provider(
    wiring: PaperDryRunWiring | None = None,
) -> DryRunProvider:
    safe_wiring = wiring or PaperDryRunWiring()

    def provider() -> DryRunActionResult:
        blocked = _paper_blocked_reason(safe_wiring)
        if blocked is not None:
            return _blocked_result(blocked)
        assert safe_wiring.config is not None
        assert safe_wiring.job_factory is not None
        session = safe_wiring.session_factory(
            config=safe_wiring.config,
            job_factory=safe_wiring.job_factory,
            commands=safe_wiring.commands,
            command_provider=safe_wiring.command_provider,
        )
        return _map_paper_result(session.run())

    return provider


def create_sim_dry_run_provider(
    wiring: SimDryRunWiring | None = None,
) -> DryRunProvider:
    safe_wiring = wiring or SimDryRunWiring()

    def provider() -> DryRunActionResult:
        blocked = _sim_blocked_reason(safe_wiring)
        if blocked is not None:
            return _blocked_result(blocked)
        assert safe_wiring.config is not None
        assert safe_wiring.job_factory is not None
        session = safe_wiring.session_factory(
            config=safe_wiring.config,
            job_factory=safe_wiring.job_factory,
            commands=safe_wiring.commands,
            command_provider=safe_wiring.command_provider,
        )
        return _map_sim_result(session.run())

    return provider


def _paper_blocked_reason(wiring: PaperDryRunWiring) -> str | None:
    if wiring.apply_requested:
        return "paper apply is not available from the console"
    if not _is_mock_target(wiring.target):
        return "paper console dry-run supports MOCK target only"
    if wiring.config is None:
        return "paper dry-run requires complete session config"
    if not wiring.config.dry_run or wiring.config.apply_confirmed:
        return "paper console dry-run requires dry_run=True and apply_confirmed=False"
    if wiring.job_factory is None:
        return "paper dry-run requires a session job factory"
    return _command_source_blocked_reason(wiring.commands, wiring.command_provider, "paper")


def _sim_blocked_reason(wiring: SimDryRunWiring) -> str | None:
    if wiring.apply_requested:
        return "sim apply is not available from the console"
    if not _is_mock_target(wiring.target):
        return "sim console dry-run supports MOCK target only"
    if wiring.config is None:
        return "sim dry-run requires complete session config"
    if not wiring.config.dry_run or wiring.config.apply_confirmed:
        return "sim console dry-run requires dry_run=True and apply_confirmed=False"
    if wiring.job_factory is None:
        return "sim dry-run requires a session job factory"
    return _command_source_blocked_reason(wiring.commands, wiring.command_provider, "sim")


def _command_source_blocked_reason(
    commands: Sequence[ExecutionCommand] | None,
    command_provider: Callable[[], Sequence[ExecutionCommand]] | None,
    name: str,
) -> str | None:
    if commands is None and command_provider is None:
        return f"{name} dry-run requires typed commands or command_provider"
    if commands is not None and command_provider is not None:
        return f"{name} dry-run accepts either commands or command_provider, not both"
    if commands is not None:
        return _commands_blocked_reason(commands, name)
    return None


def _commands_blocked_reason(
    commands: Sequence[ExecutionCommand],
    name: str,
) -> str | None:
    if not commands:
        return f"{name} dry-run requires at least one typed ExecutionCommand"
    for command in commands:
        target = getattr(command, "execution_target", None)
        if target is not None and _target_value(target) != "MOCK":
            return f"{name} console dry-run supports MOCK target only"
    return None


def _map_paper_result(result: PaperSessionResult) -> DryRunActionResult:
    job = result.job_results[0] if result.job_results else None
    job_status = _value(job.status) if job is not None else _value(result.status)
    run_status = job_status
    return DryRunActionResult(
        session_status=_value(result.status),
        job_status=job_status,
        run_status=run_status,
        db_delta=0,
        target=MOCK_TARGET,
        reason=result.reason,
    )


def _map_sim_result(result: SimSessionResult) -> DryRunActionResult:
    job = result.job_results[0] if result.job_results else None
    job_status = _value(job.status) if job is not None else _value(result.status)
    run_status = job_status
    return DryRunActionResult(
        session_status=_value(result.status),
        job_status=job_status,
        run_status=run_status,
        db_delta=0,
        target=MOCK_TARGET,
        reason=result.reason,
    )


def _blocked_result(reason: str) -> DryRunActionResult:
    return DryRunActionResult(
        session_status="BLOCKED",
        job_status="BLOCKED",
        run_status="BLOCKED",
        db_delta=0,
        target=MOCK_TARGET,
        reason=reason,
    )


def _is_mock_target(target: str) -> bool:
    return target in {MOCK_TARGET, "MOCK"}


def _target_value(target: object) -> str:
    value = getattr(target, "value", None)
    return str(value if value is not None else target)


def _value(status: object) -> str:
    value = getattr(status, "value", None)
    return str(value if value is not None else status)
