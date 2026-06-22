from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

from futures_mvp.domain.enums import (
    Direction,
    ExecutionCommandType,
    ExecutionTarget,
    Offset,
    OrderStatus,
    OrderType,
)
from futures_mvp.domain.models import ExecutionCommand, OrderRequest, OrderState
from futures_mvp.modules.execution_gateway import build_execution_command_payload_hash
from futures_mvp.modules.market_data.consumer import (
    ResolvedInstrumentIdentity,
    ResolverConsumerContext,
    ResolverLineage,
)
from futures_mvp.modules.ops_safety import (
    CapitalControlConfig,
    CapitalControlContext,
    MigrationReadinessReport,
    RolloutConfig,
    RolloutMode,
    SafetyConfig,
)
from futures_mvp.modules.paper_trading.coordinator import (
    PaperRunContext,
    PaperRunResult,
    PaperRunStatus,
)
from futures_mvp.modules.paper_trading.job import (
    PaperJobConfig,
    PaperRuntimeJob,
)
from futures_mvp.modules.paper_trading.session import (
    PaperLocalSession,
    PaperSessionConfig,
    PaperSessionStatus,
)

NOW = datetime(2026, 6, 10, 9, tzinfo=UTC)
TRADING_DAY = date(2026, 6, 10)


class FakeCoordinator:
    def __init__(self, results: list[PaperRunResult] | None = None) -> None:
        self.calls: list[PaperRunContext] = []
        self._results = results or [PaperRunResult(status=PaperRunStatus.COMPLETED)]

    def run(self, context: PaperRunContext) -> PaperRunResult:
        self.calls.append(context)
        index = min(len(self.calls) - 1, len(self._results) - 1)
        return self._results[index]


class RecordingJobFactory:
    def __init__(self, coordinator: FakeCoordinator) -> None:
        self.calls: list[tuple[PaperJobConfig, tuple[ExecutionCommand, ...]]] = []
        self._coordinator = coordinator

    def __call__(
        self,
        config: PaperJobConfig,
        commands: Sequence[ExecutionCommand],
    ) -> PaperRuntimeJob:
        selected = tuple(commands)
        self.calls.append((config, selected))
        return PaperRuntimeJob(
            config=config,
            coordinator=self._coordinator,  # type: ignore[arg-type]
            context_provider=lambda: tuple(_run_context(command) for command in selected),
            clock=lambda: NOW,
        )


def _command(
    *,
    command_id: str = "command-1",
    execution_target: ExecutionTarget = ExecutionTarget.MOCK,
) -> ExecutionCommand:
    command = ExecutionCommand(
        command_id=command_id,
        order_id=f"order-{command_id}",
        client_order_id=f"client-{command_id}",
        account_id="account-1",
        symbol="rb",
        instrument_id="rb2601",
        trade_instrument_id="rb2601",
        exchange="SHFE",
        side=Direction.BUY,
        offset=Offset.OPEN,
        quantity=Decimal("2"),
        price=Decimal("3500"),
        order_type=OrderType.LIMIT,
        tif="GFD",
        command_type=ExecutionCommandType.SUBMIT_ORDER,
        execution_target=execution_target,
        command_payload_hash="pending",
        created_at=NOW,
    )
    return command.model_copy(
        update={"command_payload_hash": build_execution_command_payload_hash(command)}
    )


def _order_state(command: ExecutionCommand) -> OrderState:
    return OrderState(
        order_id=command.order_id,
        request=OrderRequest(
            client_order_id=command.client_order_id,
            account_id=command.account_id,
            instrument_id=command.instrument_id,
            exchange=command.exchange,
            direction=command.side,
            offset=command.offset,
            order_type=command.order_type,
            limit_price=command.price,
            quantity=command.quantity,
        ),
        status=OrderStatus.SUBMITTED,
        filled_quantity=Decimal("0"),
    )


def _run_context(command: ExecutionCommand) -> PaperRunContext:
    return PaperRunContext(
        rollout_mode=RolloutMode.PAPER,
        safety_config=SafetyConfig(
            rollout=RolloutConfig(
                mode=RolloutMode.PAPER,
                capital_controls=CapitalControlConfig(
                    max_order_size=Decimal("10"),
                    max_position_size=Decimal("10"),
                    max_daily_loss=Decimal("10000"),
                    account_whitelist=("account-1",),
                    allowed_instruments=("rb2601",),
                ),
            )
        ),
        migration=MigrationReadinessReport(
            compatible=True,
            current_revision="0016",
            expected_revision="0016",
        ),
        capital_control_context=CapitalControlContext(
            order_size=command.quantity,
            projected_position_size=command.quantity,
            daily_loss=Decimal("0"),
            account_id=command.account_id,
            instrument_id=command.instrument_id,
        ),
        account_id=command.account_id,
        trading_day=TRADING_DAY,
        config_hash="paper-config-v1",
        command=command,
        current_order_state=_order_state(command),
        symbol=command.symbol,
        trade_instrument_id=command.trade_instrument_id,
    )


def _config(
    *,
    dry_run: bool = True,
    apply_confirmed: bool = False,
    resolver_required: bool = False,
) -> PaperSessionConfig:
    return PaperSessionConfig(
        session_name="paper-local-smoke",
        runtime_id="runtime-1",
        trading_day=TRADING_DAY,
        account_id="account-1",
        dry_run=dry_run,
        max_commands=2,
        apply_confirmed=apply_confirmed,
        resolver_required=resolver_required,
    )


def test_dry_run_session_uses_job_dry_run_and_does_not_call_coordinator() -> None:
    coordinator = FakeCoordinator()
    factory = RecordingJobFactory(coordinator)

    result = PaperLocalSession(
        config=_config(dry_run=True),
        commands=(_command(),),
        job_factory=factory,
        clock=lambda: NOW,
    ).run()

    assert result.status is PaperSessionStatus.DRY_RUN_COMPLETED
    assert result.processed_commands == 1
    assert len(factory.calls) == 1
    assert factory.calls[0][0].dry_run is True
    assert coordinator.calls == []


def test_apply_session_requires_confirmation_and_can_complete() -> None:
    coordinator = FakeCoordinator()
    factory = RecordingJobFactory(coordinator)

    blocked = PaperLocalSession(
        config=_config(dry_run=False, apply_confirmed=False),
        commands=(_command(),),
        job_factory=factory,
        clock=lambda: NOW,
    ).run()

    assert blocked.status is PaperSessionStatus.BLOCKED
    assert factory.calls == []
    assert coordinator.calls == []

    applied = PaperLocalSession(
        config=_config(dry_run=False, apply_confirmed=True),
        commands=(_command(),),
        job_factory=factory,
        clock=lambda: NOW,
    ).run()

    assert applied.status is PaperSessionStatus.COMPLETED
    assert applied.processed_commands == 1
    assert factory.calls[-1][0].dry_run is False
    assert len(coordinator.calls) == 1


def test_blocked_session_missing_commands_does_not_call_job() -> None:
    coordinator = FakeCoordinator()
    factory = RecordingJobFactory(coordinator)

    result = PaperLocalSession(
        config=_config(),
        commands=(),
        job_factory=factory,
        clock=lambda: NOW,
    ).run()

    assert result.status is PaperSessionStatus.BLOCKED
    assert result.reason == "paper session requires at least one typed ExecutionCommand"
    assert factory.calls == []


def test_conflict_session_stops_later_commands() -> None:
    coordinator = FakeCoordinator(
        [
            PaperRunResult(status=PaperRunStatus.CONFLICT, reason="conflict"),
            PaperRunResult(status=PaperRunStatus.COMPLETED),
        ]
    )
    factory = RecordingJobFactory(coordinator)

    result = PaperLocalSession(
        config=_config(dry_run=False, apply_confirmed=True),
        commands=(_command(command_id="1"), _command(command_id="2")),
        job_factory=factory,
        clock=lambda: NOW,
    ).run()

    assert result.status is PaperSessionStatus.CONFLICT
    assert result.processed_commands == 1
    assert result.conflict_count == 1
    assert len(coordinator.calls) == 1


def test_session_rejects_non_mock_target_before_job() -> None:
    coordinator = FakeCoordinator()
    factory = RecordingJobFactory(coordinator)

    result = PaperLocalSession(
        config=_config(),
        commands=(_command(execution_target=ExecutionTarget.PAPER),),
        job_factory=factory,
        clock=lambda: NOW,
    ).run()

    assert result.status is PaperSessionStatus.BLOCKED
    assert result.reason == "paper session supports ExecutionTarget.MOCK only"
    assert factory.calls == []


def test_resolver_required_session_blocks_missing_context() -> None:
    coordinator = FakeCoordinator()
    factory = RecordingJobFactory(coordinator)

    result = PaperLocalSession(
        config=_config(resolver_required=True),
        commands=(_command(),),
        job_factory=factory,
        clock=lambda: NOW,
    ).run()

    assert result.status is PaperSessionStatus.BLOCKED
    assert result.reason == "paper session requires resolver consumer context"
    assert factory.calls == []


def test_resolver_required_session_blocks_identity_mismatch() -> None:
    coordinator = FakeCoordinator()
    factory = RecordingJobFactory(coordinator)

    result = PaperLocalSession(
        config=_config(resolver_required=True),
        commands=(_command(),),
        resolver_consumer_context=_resolver_context(trade_instrument_id="rb2610"),
        job_factory=factory,
        clock=lambda: NOW,
    ).run()

    assert result.status is PaperSessionStatus.BLOCKED
    assert result.reason == "paper session resolver identity mismatch: trade_instrument_id"
    assert factory.calls == []


def _resolver_context(*, trade_instrument_id: str = "rb2601") -> ResolverConsumerContext:
    return ResolverConsumerContext(
        identity=ResolvedInstrumentIdentity(
            symbol="rb",
            instrument_id="rb2601",
            trade_instrument_id=trade_instrument_id,
            exchange="SHFE",
            trading_day=TRADING_DAY,
        ),
        lineage=ResolverLineage(
            resolver_source="static_fixture",
            resolver_confidence="static_fixture",
            resolver_effective_from=TRADING_DAY,
            resolver_effective_to=TRADING_DAY,
            resolver_diagnostics_summary="static fixture only, not live market source",
        ),
    )
