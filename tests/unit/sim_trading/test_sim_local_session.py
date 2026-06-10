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
from futures_mvp.modules.ops_safety import (
    CapitalControlConfig,
    CapitalControlContext,
    MigrationReadinessReport,
    OperatorApproval,
    RolloutConfig,
    RolloutMode,
    SafetyConfig,
)
from futures_mvp.modules.sim_trading import (
    SimJobConfig,
    SimLocalSession,
    SimRunContext,
    SimRunResult,
    SimRunStatus,
    SimRuntimeJob,
    SimSessionConfig,
    SimSessionStatus,
)

NOW = datetime(2026, 6, 10, 9, tzinfo=UTC)
TRADING_DAY = date(2026, 6, 10)


class FakeCoordinator:
    def __init__(self, results: list[SimRunResult] | None = None) -> None:
        self.calls: list[SimRunContext] = []
        self._results = results or [SimRunResult(status=SimRunStatus.COMPLETED)]

    def run(self, context: SimRunContext) -> SimRunResult:
        self.calls.append(context)
        index = min(len(self.calls) - 1, len(self._results) - 1)
        return self._results[index]


class RecordingJobFactory:
    def __init__(self, coordinator: FakeCoordinator) -> None:
        self.calls: list[tuple[SimJobConfig, tuple[ExecutionCommand, ...]]] = []
        self._coordinator = coordinator

    def __call__(
        self,
        config: SimJobConfig,
        commands: Sequence[ExecutionCommand],
    ) -> SimRuntimeJob:
        selected = tuple(commands)
        self.calls.append((config, selected))
        return SimRuntimeJob(
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


def _run_context(command: ExecutionCommand) -> SimRunContext:
    return SimRunContext(
        rollout_mode=RolloutMode.SIM,
        safety_config=SafetyConfig(
            rollout=RolloutConfig(
                mode=RolloutMode.SIM,
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
        config_hash="sim-config-v1",
        command=command,
        current_order_state=_order_state(command),
        symbol=command.symbol,
        trade_instrument_id=command.trade_instrument_id,
        runtime_ready=True,
        operator_approval=OperatorApproval(
            environment="sim",
            account_id=command.account_id,
            adapter_target="mock",
            allowed_stage="sim_trading",
            command_surface=command.command_type.value,
            approved_at=NOW,
            decision_id="approval-1",
        ),
    )


def _config(*, dry_run: bool = True, apply_confirmed: bool = False) -> SimSessionConfig:
    return SimSessionConfig(
        session_name="sim-local-smoke",
        runtime_id="runtime-1",
        trading_day=TRADING_DAY,
        account_id="account-1",
        dry_run=dry_run,
        max_commands=2,
        apply_confirmed=apply_confirmed,
    )


def test_sim_local_session_dry_run_completed_without_coordinator_call() -> None:
    coordinator = FakeCoordinator()
    factory = RecordingJobFactory(coordinator)

    result = SimLocalSession(
        config=_config(dry_run=True),
        commands=(_command(),),
        job_factory=factory,
        clock=lambda: NOW,
    ).run()

    assert result.status is SimSessionStatus.DRY_RUN_COMPLETED
    assert result.processed_commands == 1
    assert len(factory.calls) == 1
    assert factory.calls[0][0].dry_run is True
    assert coordinator.calls == []


def test_sim_local_session_apply_requires_confirmation_and_can_complete() -> None:
    coordinator = FakeCoordinator()
    factory = RecordingJobFactory(coordinator)

    blocked = SimLocalSession(
        config=_config(dry_run=False, apply_confirmed=False),
        commands=(_command(),),
        job_factory=factory,
        clock=lambda: NOW,
    ).run()

    assert blocked.status is SimSessionStatus.BLOCKED
    assert factory.calls == []
    assert coordinator.calls == []

    applied = SimLocalSession(
        config=_config(dry_run=False, apply_confirmed=True),
        commands=(_command(),),
        job_factory=factory,
        clock=lambda: NOW,
    ).run()

    assert applied.status is SimSessionStatus.COMPLETED
    assert applied.processed_commands == 1
    assert factory.calls[-1][0].dry_run is False
    assert factory.calls[-1][0].apply_confirmed is True
    assert len(coordinator.calls) == 1


def test_sim_local_session_accepts_typed_provider_only() -> None:
    coordinator = FakeCoordinator()
    factory = RecordingJobFactory(coordinator)

    result = SimLocalSession(
        config=_config(dry_run=True),
        command_provider=lambda: (_command(),),
        job_factory=factory,
        clock=lambda: NOW,
    ).run()

    assert result.status is SimSessionStatus.DRY_RUN_COMPLETED
    assert len(factory.calls) == 1


def test_sim_local_session_blocks_missing_or_ambiguous_command_source() -> None:
    coordinator = FakeCoordinator()
    factory = RecordingJobFactory(coordinator)

    missing = SimLocalSession(
        config=_config(),
        job_factory=factory,
        clock=lambda: NOW,
    ).run()
    ambiguous = SimLocalSession(
        config=_config(),
        commands=(_command(),),
        command_provider=lambda: (_command(),),
        job_factory=factory,
        clock=lambda: NOW,
    ).run()

    assert missing.status is SimSessionStatus.BLOCKED
    assert ambiguous.status is SimSessionStatus.BLOCKED
    assert factory.calls == []


def test_sim_local_session_blocks_empty_untyped_and_non_mock_commands() -> None:
    coordinator = FakeCoordinator()
    factory = RecordingJobFactory(coordinator)

    empty = SimLocalSession(
        config=_config(),
        commands=(),
        job_factory=factory,
        clock=lambda: NOW,
    ).run()
    untyped = SimLocalSession(
        config=_config(),
        commands=("raw-payload",),  # type: ignore[list-item]
        job_factory=factory,
        clock=lambda: NOW,
    ).run()
    non_mock = SimLocalSession(
        config=_config(),
        commands=(_command(execution_target=ExecutionTarget.SIM),),
        job_factory=factory,
        clock=lambda: NOW,
    ).run()

    assert empty.status is SimSessionStatus.BLOCKED
    assert empty.reason == "sim session requires at least one typed ExecutionCommand"
    assert untyped.status is SimSessionStatus.BLOCKED
    assert untyped.reason == "sim session command source must return typed ExecutionCommand"
    assert non_mock.status is SimSessionStatus.BLOCKED
    assert non_mock.reason == "sim session supports ExecutionTarget.MOCK only"
    assert factory.calls == []


def test_sim_local_session_conflict_stops_later_commands() -> None:
    coordinator = FakeCoordinator(
        [
            SimRunResult(status=SimRunStatus.CONFLICT, reason="conflict"),
            SimRunResult(status=SimRunStatus.COMPLETED),
        ]
    )
    factory = RecordingJobFactory(coordinator)

    result = SimLocalSession(
        config=_config(dry_run=False, apply_confirmed=True),
        commands=(_command(command_id="1"), _command(command_id="2")),
        job_factory=factory,
        clock=lambda: NOW,
    ).run()

    assert result.status is SimSessionStatus.CONFLICT
    assert result.processed_commands == 1
    assert result.conflict_count == 1
    assert len(coordinator.calls) == 1
