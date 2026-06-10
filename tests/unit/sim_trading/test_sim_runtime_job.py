from __future__ import annotations

from dataclasses import replace
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
    KillSwitchConfig,
    LiveGateConfig,
    MigrationReadinessReport,
    OperatorApproval,
    RolloutConfig,
    RolloutMode,
    SafetyConfig,
)
from futures_mvp.modules.sim_trading import (
    SimJobConfig,
    SimJobStatus,
    SimRunContext,
    SimRunResult,
    SimRunStatus,
    SimRuntimeJob,
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


class CountingProvider:
    def __init__(self, contexts: tuple[SimRunContext, ...]) -> None:
        self.calls = 0
        self._contexts = contexts

    def __call__(self) -> tuple[SimRunContext, ...]:
        self.calls += 1
        return self._contexts


def _command(
    *,
    execution_target: ExecutionTarget = ExecutionTarget.MOCK,
) -> ExecutionCommand:
    command = ExecutionCommand(
        command_id="command-1",
        order_id="order-1",
        client_order_id="client-1",
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


def _order_state(command: ExecutionCommand | None = None) -> OrderState:
    command = command or _command()
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


def _approval(
    *,
    environment: str = "sim",
    account_id: str = "account-1",
    adapter_target: str = "mock",
    allowed_stage: str = "sim_trading",
    command_surface: str = "SUBMIT_ORDER",
) -> OperatorApproval:
    return OperatorApproval(
        environment=environment,
        account_id=account_id,
        adapter_target=adapter_target,
        allowed_stage=allowed_stage,
        command_surface=command_surface,
        approved_at=NOW,
        decision_id="approval-1",
    )


def _safety_config(
    *,
    mode: RolloutMode = RolloutMode.SIM,
    kill_switch: KillSwitchConfig | None = None,
    live_gate: LiveGateConfig | None = None,
    max_order_size: Decimal = Decimal("10"),
) -> SafetyConfig:
    return SafetyConfig(
        kill_switch=kill_switch or KillSwitchConfig(),
        live_gate=live_gate or LiveGateConfig(),
        rollout=RolloutConfig(
            mode=mode,
            capital_controls=CapitalControlConfig(
                max_order_size=max_order_size,
                max_position_size=Decimal("10"),
                max_daily_loss=Decimal("10000"),
                account_whitelist=("account-1",),
                allowed_instruments=("rb2601",),
            ),
        ),
    )


def _migration(compatible: bool = True) -> MigrationReadinessReport:
    return MigrationReadinessReport(
        compatible=compatible,
        current_revision="0016",
        expected_revision="0016",
        reason=None if compatible else "db migration revision is incompatible",
    )


def _capital_context(order_size: Decimal = Decimal("2")) -> CapitalControlContext:
    return CapitalControlContext(
        order_size=order_size,
        projected_position_size=Decimal("2"),
        daily_loss=Decimal("0"),
        account_id="account-1",
        instrument_id="rb2601",
    )


def _run_context(
    *,
    mode: RolloutMode = RolloutMode.SIM,
    safety_config: SafetyConfig | None = None,
    migration: MigrationReadinessReport | None = None,
    capital_context: CapitalControlContext | None = None,
    command: ExecutionCommand | None = None,
    runtime_ready: bool = True,
    approval: OperatorApproval | None = None,
    unresolved_critical_incidents: tuple[str, ...] = (),
) -> SimRunContext:
    command = command or _command()
    return SimRunContext(
        rollout_mode=mode,
        safety_config=safety_config or _safety_config(mode=mode),
        migration=migration or _migration(),
        capital_control_context=capital_context or _capital_context(),
        account_id="account-1",
        trading_day=TRADING_DAY,
        config_hash="sim-config-v1",
        command=command,
        current_order_state=_order_state(command),
        symbol=command.symbol,
        trade_instrument_id=command.trade_instrument_id,
        runtime_ready=runtime_ready,
        operator_approval=approval if approval is not None else _approval(),
        unresolved_critical_incidents=unresolved_critical_incidents,
    )


def _enabled_config(*, dry_run: bool = False, apply_confirmed: bool = True) -> SimJobConfig:
    return SimJobConfig(
        enabled=True,
        scheduler_enabled=True,
        dry_run=dry_run,
        apply_confirmed=apply_confirmed,
    )


def _job(
    *,
    config: SimJobConfig | None = None,
    coordinator: FakeCoordinator | None = None,
    provider: CountingProvider | None = None,
) -> SimRuntimeJob:
    return SimRuntimeJob(
        config=config or _enabled_config(),
        coordinator=coordinator,  # type: ignore[arg-type]
        context_provider=provider or CountingProvider((_run_context(),)),
        clock=lambda: NOW,
    )


def test_sim_job_disabled_default_noop_without_provider_or_coordinator_call() -> None:
    coordinator = FakeCoordinator()
    provider = CountingProvider((_run_context(),))
    job = _job(config=SimJobConfig(), coordinator=coordinator, provider=provider)

    result = job()

    assert result.status is SimJobStatus.DISABLED
    assert provider.calls == 0
    assert coordinator.calls == []


def test_sim_job_dry_run_does_not_call_coordinator() -> None:
    coordinator = FakeCoordinator()
    provider = CountingProvider((_run_context(),))

    result = _job(
        config=_enabled_config(dry_run=True, apply_confirmed=False),
        coordinator=coordinator,
        provider=provider,
    )()

    assert result.status is SimJobStatus.DRY_RUN
    assert result.processed_command_count == 1
    assert provider.calls == 1
    assert coordinator.calls == []


def test_sim_job_apply_calls_coordinator_once() -> None:
    coordinator = FakeCoordinator()
    provider = CountingProvider((_run_context(),))

    result = _job(coordinator=coordinator, provider=provider)()

    assert result.status is SimJobStatus.COMPLETED
    assert result.processed_command_count == 1
    assert result.sim_run_result is not None
    assert provider.calls == 1
    assert len(coordinator.calls) == 1


def test_sim_job_apply_requires_confirmation() -> None:
    coordinator = FakeCoordinator()
    provider = CountingProvider((_run_context(),))
    config = _enabled_config(dry_run=False, apply_confirmed=False)

    result = _job(config=config, coordinator=coordinator, provider=provider)()

    assert result.status is SimJobStatus.BLOCKED
    assert result.reason == "sim apply requires explicit apply_confirmed"
    assert provider.calls == 0
    assert coordinator.calls == []


def test_sim_job_blocks_non_sim_mode_before_coordinator() -> None:
    coordinator = FakeCoordinator()
    provider = CountingProvider(
        (
            _run_context(
                mode=RolloutMode.PAPER,
                safety_config=_safety_config(mode=RolloutMode.PAPER),
            ),
        )
    )

    result = _job(coordinator=coordinator, provider=provider)()

    assert result.status is SimJobStatus.BLOCKED
    assert coordinator.calls == []


def test_sim_job_blocks_missing_or_mismatched_approval() -> None:
    cases = [
        replace(_run_context(), operator_approval=None),
        _run_context(approval=_approval(environment="paper")),
        _run_context(approval=_approval(account_id="other")),
        _run_context(approval=_approval(adapter_target="paper")),
        _run_context(approval=_approval(allowed_stage="execution_gateway")),
        _run_context(approval=_approval(command_surface="CANCEL_ORDER")),
    ]
    for context in cases:
        coordinator = FakeCoordinator()
        provider = CountingProvider((context,))

        result = _job(coordinator=coordinator, provider=provider)()

        assert result.status is SimJobStatus.BLOCKED
        assert coordinator.calls == []


def test_sim_job_blocks_runtime_not_ready_migration_and_capital_reject() -> None:
    cases = [
        _run_context(runtime_ready=False),
        _run_context(migration=_migration(False)),
        _run_context(capital_context=_capital_context(order_size=Decimal("20"))),
    ]
    for context in cases:
        coordinator = FakeCoordinator()
        provider = CountingProvider((context,))

        result = _job(coordinator=coordinator, provider=provider)()

        assert result.status is SimJobStatus.BLOCKED
        assert coordinator.calls == []


def test_sim_job_blocks_kill_switch_scheduler_pause_and_replay_pause() -> None:
    cases = [
        KillSwitchConfig(global_kill_switch=True),
        KillSwitchConfig(scheduler_paused=True),
        KillSwitchConfig(replay_paused=True),
    ]
    for kill_switch in cases:
        coordinator = FakeCoordinator()
        provider = CountingProvider(
            (_run_context(safety_config=_safety_config(kill_switch=kill_switch)),)
        )

        result = _job(coordinator=coordinator, provider=provider)()

        assert result.status is SimJobStatus.BLOCKED
        assert coordinator.calls == []


def test_sim_job_blocks_live_gate_and_unresolved_incident() -> None:
    live_gate = LiveGateConfig(
        broker_enabled=True,
        live_submit_enabled=True,
        explicit_live_flag=True,
        broker_credentials_handle="secret-ref",
    )
    cases = [
        _run_context(safety_config=_safety_config(live_gate=live_gate)),
        _run_context(unresolved_critical_incidents=("incident-1",)),
    ]
    for context in cases:
        coordinator = FakeCoordinator()
        provider = CountingProvider((context,))

        result = _job(coordinator=coordinator, provider=provider)()

        assert result.status is SimJobStatus.BLOCKED
        assert coordinator.calls == []


def test_sim_job_rejects_non_mock_target_before_coordinator() -> None:
    for target in [ExecutionTarget.PAPER, ExecutionTarget.SIM, ExecutionTarget.LIVE]:
        coordinator = FakeCoordinator()
        provider = CountingProvider(
            (_run_context(command=_command(execution_target=target)),)
        )

        result = _job(coordinator=coordinator, provider=provider)()

        assert result.status is SimJobStatus.BLOCKED
        assert result.reason == "sim job supports ExecutionTarget.MOCK only"
        assert coordinator.calls == []


def test_sim_job_conflict_and_error_stop_later_commands() -> None:
    scenarios = [
        (
            SimRunResult(status=SimRunStatus.CONFLICT, reason="conflict"),
            SimJobStatus.CONFLICT,
            1,
            0,
        ),
        (
            SimRunResult(status=SimRunStatus.ERROR, reason="error"),
            SimJobStatus.ERROR,
            0,
            1,
        ),
    ]
    for run_result, expected_status, expected_conflicts, expected_errors in scenarios:
        coordinator = FakeCoordinator([run_result, SimRunResult(status=SimRunStatus.COMPLETED)])
        provider = CountingProvider((_run_context(), _run_context()))
        config = SimJobConfig(
            enabled=True,
            scheduler_enabled=True,
            dry_run=False,
            apply_confirmed=True,
            max_commands_per_run=2,
        )

        result = _job(config=config, coordinator=coordinator, provider=provider)()

        assert result.status is expected_status
        assert result.processed_command_count == 1
        assert result.conflict_count == expected_conflicts
        assert result.error_count == expected_errors
        assert len(coordinator.calls) == 1


def test_sim_job_maps_duplicate_result() -> None:
    coordinator = FakeCoordinator([SimRunResult(status=SimRunStatus.DUPLICATE)])
    provider = CountingProvider((_run_context(),))

    result = _job(coordinator=coordinator, provider=provider)()

    assert result.status is SimJobStatus.DUPLICATE
    assert result.processed_command_count == 1
