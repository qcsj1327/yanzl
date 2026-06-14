from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

from futures_mvp.domain.models import ExecutionCommand
from futures_mvp.modules.market_data.consumer import (
    ResolverConsumerContext,
    resolver_context_command_mismatch,
)
from futures_mvp.modules.operator_console.actions import (
    DryRunActionResult,
    DryRunProvider,
)
from futures_mvp.modules.operator_console.config_assembly import (
    ConsoleDryRunConfig,
    assemble_config,
    blocked_config_result,
)
from futures_mvp.modules.paper_trading import session as paper_session
from futures_mvp.modules.paper_trading.session import (
    PaperCommandProvider,
    PaperLocalSession,
    PaperRuntimeJobFactory,
    PaperSessionConfig,
    PaperSessionResult,
)
from futures_mvp.modules.sim_trading import session as sim_session
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
    resolver_consumer_context: ResolverConsumerContext | None = None
    session_factory: PaperSessionFactory = PaperLocalSession
    target: str = MOCK_TARGET
    apply_requested: bool = False
    resolver_required: bool = False


@dataclass(frozen=True)
class SimDryRunWiring:
    config: SimSessionConfig | None = None
    job_factory: SimRuntimeJobFactory | None = None
    commands: Sequence[ExecutionCommand] | None = None
    command_provider: SimCommandProvider | None = None
    resolver_consumer_context: ResolverConsumerContext | None = None
    session_factory: SimSessionFactory = SimLocalSession
    target: str = MOCK_TARGET
    apply_requested: bool = False
    resolver_required: bool = False


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
            resolver_consumer_context=safe_wiring.resolver_consumer_context,
        )
        return _map_paper_result(session.run())

    return provider


def _paper_console_fixture_job_factory(
    job_config: Any,
    commands: Sequence[ExecutionCommand],
) -> Callable[[], Any]:
    def job() -> Any:
        result_type = vars(paper_session)["PaperJobResult"]
        status_type = vars(paper_session)["PaperJobStatus"]
        if not job_config.dry_run:
            return result_type(
                job_name=job_config.job_name,
                status=status_type.BLOCKED,
                reason="console paper fixture requires dry_run=True",
            )
        return result_type(
            job_name=job_config.job_name,
            status=status_type.DRY_RUN,
            reason="本地 Paper 预演完成，未写库",
            processed_command_count=len(commands),
        )

    return job


def create_paper_config_dry_run_provider(
    config: ConsoleDryRunConfig,
    *,
    job_factory: PaperRuntimeJobFactory | None = _paper_console_fixture_job_factory,
    session_factory: PaperSessionFactory = PaperLocalSession,
) -> DryRunProvider:
    assembly = assemble_config(config)
    if assembly.validation.blocked:
        reason = assembly.validation.reason or "配置无效"

        def blocked_provider() -> DryRunActionResult:
            return blocked_config_result(reason, assembly.validation.missing_fields)

        return blocked_provider
    assert assembly.command is not None
    assert assembly.resolver_consumer_context is not None
    return create_paper_dry_run_provider(
        PaperDryRunWiring(
            config=_paper_session_config(config),
            job_factory=job_factory,
            commands=(assembly.command,),
            resolver_consumer_context=assembly.resolver_consumer_context,
            session_factory=session_factory,
            target=MOCK_TARGET,
            apply_requested=False,
            resolver_required=True,
        )
    )


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
            resolver_consumer_context=safe_wiring.resolver_consumer_context,
        )
        return _map_sim_result(session.run())

    return provider


def _sim_console_fixture_job_factory(
    job_config: Any,
    commands: Sequence[ExecutionCommand],
) -> Callable[[], Any]:
    def job() -> Any:
        result_type = vars(sim_session)["SimJobResult"]
        status_type = vars(sim_session)["SimJobStatus"]
        if not job_config.dry_run or job_config.apply_confirmed:
            return result_type(
                job_name=job_config.job_name,
                status=status_type.BLOCKED,
                reason="console sim fixture requires dry_run=True and apply_confirmed=False",
            )
        return result_type(
            job_name=job_config.job_name,
            status=status_type.DRY_RUN,
            reason="本地 SIM 预演完成，未写库",
            processed_command_count=len(commands),
        )

    return job


def create_sim_config_dry_run_provider(
    config: ConsoleDryRunConfig,
    *,
    job_factory: SimRuntimeJobFactory | None = _sim_console_fixture_job_factory,
    session_factory: SimSessionFactory = SimLocalSession,
) -> DryRunProvider:
    assembly = assemble_config(config)
    if assembly.validation.blocked:
        reason = assembly.validation.reason or "配置无效"

        def blocked_provider() -> DryRunActionResult:
            return blocked_config_result(reason, assembly.validation.missing_fields)

        return blocked_provider
    assert assembly.command is not None
    assert assembly.resolver_consumer_context is not None
    return create_sim_dry_run_provider(
        SimDryRunWiring(
            config=_sim_session_config(config),
            job_factory=job_factory,
            commands=(assembly.command,),
            resolver_consumer_context=assembly.resolver_consumer_context,
            session_factory=session_factory,
            target=MOCK_TARGET,
            apply_requested=False,
            resolver_required=True,
        )
    )


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
    return _command_source_blocked_reason(
        wiring.commands,
        wiring.command_provider,
        "paper",
        resolver_required=wiring.resolver_required,
        resolver_consumer_context=wiring.resolver_consumer_context,
    )


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
    return _command_source_blocked_reason(
        wiring.commands,
        wiring.command_provider,
        "sim",
        resolver_required=wiring.resolver_required,
        resolver_consumer_context=wiring.resolver_consumer_context,
    )


def _command_source_blocked_reason(
    commands: Sequence[ExecutionCommand] | None,
    command_provider: Callable[[], Sequence[ExecutionCommand]] | None,
    name: str,
    *,
    resolver_required: bool,
    resolver_consumer_context: ResolverConsumerContext | None,
) -> str | None:
    if resolver_required and resolver_consumer_context is None:
        return f"{name} dry-run requires resolver consumer context"
    if commands is None and command_provider is None:
        return f"{name} dry-run requires typed commands or command_provider"
    if commands is not None and command_provider is not None:
        return f"{name} dry-run accepts either commands or command_provider, not both"
    if commands is not None:
        return _commands_blocked_reason(
            commands,
            name,
            resolver_consumer_context=resolver_consumer_context,
        )
    return None


def _commands_blocked_reason(
    commands: Sequence[ExecutionCommand],
    name: str,
    *,
    resolver_consumer_context: ResolverConsumerContext | None = None,
) -> str | None:
    if not commands:
        return f"{name} dry-run requires at least one typed ExecutionCommand"
    for command in commands:
        target = getattr(command, "execution_target", None)
        if target is not None and _target_value(target) != "MOCK":
            return f"{name} console dry-run supports MOCK target only"
        if resolver_consumer_context is not None:
            mismatch = resolver_context_command_mismatch(
                resolver_consumer_context,
                command,
            )
            if mismatch is not None:
                return f"{name} dry-run {mismatch}"
    return None


def _map_paper_result(result: PaperSessionResult) -> DryRunActionResult:
    job = result.job_results[0] if result.job_results else None
    job_status = _value(job.status) if job is not None else _value(result.status)
    run_status = _value(result.status)
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
    run_status = _value(result.status)
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


def _paper_session_config(config: ConsoleDryRunConfig) -> PaperSessionConfig:
    return PaperSessionConfig(
        session_name="console-paper-dry-run",
        runtime_id="operator-console",
        trading_day=date.fromisoformat(config.trading_day.strip()),
        account_id=config.account_id.strip(),
        dry_run=True,
        apply_confirmed=False,
        resolver_required=True,
    )


def _sim_session_config(config: ConsoleDryRunConfig) -> SimSessionConfig:
    return SimSessionConfig(
        session_name="console-sim-dry-run",
        runtime_id="operator-console",
        trading_day=date.fromisoformat(config.trading_day.strip()),
        account_id=config.account_id.strip(),
        dry_run=True,
        apply_confirmed=False,
        resolver_required=True,
    )


def _is_mock_target(target: str) -> bool:
    return target in {MOCK_TARGET, "MOCK"}


def _target_value(target: object) -> str:
    value = getattr(target, "value", None)
    return str(value if value is not None else target)


def _value(status: object) -> str:
    value = getattr(status, "value", None)
    return str(value if value is not None else status)
