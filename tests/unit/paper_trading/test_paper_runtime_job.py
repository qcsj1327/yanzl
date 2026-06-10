from __future__ import annotations

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
    MigrationReadinessReport,
    RolloutConfig,
    RolloutMode,
    SafetyConfig,
)
from futures_mvp.modules.paper_trading import (
    PaperJobConfig,
    PaperJobStatus,
    PaperRunContext,
    PaperRunResult,
    PaperRunStatus,
    PaperRuntimeJob,
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


class CountingProvider:
    def __init__(self, contexts: tuple[PaperRunContext, ...]) -> None:
        self.calls = 0
        self._contexts = contexts

    def __call__(self) -> tuple[PaperRunContext, ...]:
        self.calls += 1
        return self._contexts


def _command() -> ExecutionCommand:
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
        execution_target=ExecutionTarget.MOCK,
        command_payload_hash="pending",
        created_at=NOW,
    )
    return command.model_copy(
        update={"command_payload_hash": build_execution_command_payload_hash(command)}
    )


def _order_state() -> OrderState:
    return OrderState(
        order_id="order-1",
        request=OrderRequest(
            client_order_id="client-1",
            account_id="account-1",
            instrument_id="rb2601",
            exchange="SHFE",
            direction=Direction.BUY,
            offset=Offset.OPEN,
            order_type=OrderType.LIMIT,
            limit_price=Decimal("3500"),
            quantity=Decimal("2"),
        ),
        status=OrderStatus.SUBMITTED,
        filled_quantity=Decimal("0"),
    )


def _safety_config(
    *,
    mode: RolloutMode = RolloutMode.PAPER,
    kill_switch: KillSwitchConfig | None = None,
    max_order_size: Decimal = Decimal("10"),
) -> SafetyConfig:
    return SafetyConfig(
        kill_switch=kill_switch or KillSwitchConfig(),
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
    mode: RolloutMode = RolloutMode.PAPER,
    safety_config: SafetyConfig | None = None,
    migration: MigrationReadinessReport | None = None,
    capital_context: CapitalControlContext | None = None,
) -> PaperRunContext:
    return PaperRunContext(
        rollout_mode=mode,
        safety_config=safety_config or _safety_config(mode=mode),
        migration=migration or _migration(),
        capital_control_context=capital_context or _capital_context(),
        account_id="account-1",
        trading_day=TRADING_DAY,
        config_hash="paper-config-v1",
        command=_command(),
        current_order_state=_order_state(),
        symbol="rb",
        trade_instrument_id="rb2601",
    )


def _enabled_config(*, dry_run: bool = False) -> PaperJobConfig:
    return PaperJobConfig(enabled=True, scheduler_enabled=True, dry_run=dry_run)


def _job(
    *,
    config: PaperJobConfig | None = None,
    coordinator: FakeCoordinator | None = None,
    provider: CountingProvider | None = None,
) -> PaperRuntimeJob:
    return PaperRuntimeJob(
        config=config or _enabled_config(),
        coordinator=coordinator,  # type: ignore[arg-type]
        context_provider=provider or CountingProvider((_run_context(),)),
        clock=lambda: NOW,
    )


def test_paper_job_disabled_default_noop_without_provider_or_coordinator_call() -> None:
    coordinator = FakeCoordinator()
    provider = CountingProvider((_run_context(),))
    job = _job(config=PaperJobConfig(), coordinator=coordinator, provider=provider)

    result = job()

    assert result.status is PaperJobStatus.DISABLED
    assert provider.calls == 0
    assert coordinator.calls == []


def test_paper_job_scheduler_disabled_blocks_before_provider() -> None:
    coordinator = FakeCoordinator()
    provider = CountingProvider((_run_context(),))
    config = PaperJobConfig(enabled=True, scheduler_enabled=False)
    job = _job(config=config, coordinator=coordinator, provider=provider)

    result = job()

    assert result.status is PaperJobStatus.BLOCKED
    assert result.reason == "scheduler is disabled"
    assert provider.calls == 0
    assert coordinator.calls == []


def test_paper_job_blocks_kill_switch_scheduler_pause_and_replay_pause() -> None:
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

        assert result.status is PaperJobStatus.BLOCKED
        assert coordinator.calls == []


def test_paper_job_blocks_migration_mismatch_and_capital_reject() -> None:
    cases = [
        _run_context(migration=_migration(False)),
        _run_context(capital_context=_capital_context(order_size=Decimal("20"))),
    ]
    for context in cases:
        coordinator = FakeCoordinator()
        provider = CountingProvider((context,))

        result = _job(coordinator=coordinator, provider=provider)()

        assert result.status is PaperJobStatus.BLOCKED
        assert coordinator.calls == []


def test_paper_job_missing_coordinator_fails_closed_before_provider() -> None:
    provider = CountingProvider((_run_context(),))
    job = _job(config=_enabled_config(), coordinator=None, provider=provider)

    result = job()

    assert result.status is PaperJobStatus.BLOCKED
    assert result.reason == "paper coordinator is not wired"
    assert provider.calls == 0


def test_paper_job_valid_apply_calls_coordinator_once() -> None:
    coordinator = FakeCoordinator()
    provider = CountingProvider((_run_context(),))

    result = _job(coordinator=coordinator, provider=provider)()

    assert result.status is PaperJobStatus.COMPLETED
    assert result.processed_command_count == 1
    assert result.paper_run_result is not None
    assert provider.calls == 1
    assert len(coordinator.calls) == 1


def test_paper_job_dry_run_does_not_call_coordinator() -> None:
    coordinator = FakeCoordinator()
    provider = CountingProvider((_run_context(),))

    result = _job(
        config=_enabled_config(dry_run=True),
        coordinator=coordinator,
        provider=provider,
    )()

    assert result.status is PaperJobStatus.DRY_RUN
    assert result.processed_command_count == 1
    assert coordinator.calls == []


def test_paper_job_rejects_non_paper_before_coordinator() -> None:
    coordinator = FakeCoordinator()
    provider = CountingProvider(
        (
            _run_context(
                mode=RolloutMode.SIM,
                safety_config=_safety_config(mode=RolloutMode.SIM),
            ),
        )
    )

    result = _job(coordinator=coordinator, provider=provider)()

    assert result.status is PaperJobStatus.BLOCKED
    assert coordinator.calls == []


def test_paper_job_conflict_stops_on_first_conflict_by_default() -> None:
    coordinator = FakeCoordinator(
        [
            PaperRunResult(status=PaperRunStatus.CONFLICT, reason="conflict"),
            PaperRunResult(status=PaperRunStatus.COMPLETED),
        ]
    )
    provider = CountingProvider((_run_context(), _run_context()))
    config = PaperJobConfig(
        enabled=True,
        scheduler_enabled=True,
        dry_run=False,
        max_commands_per_run=2,
    )

    result = _job(config=config, coordinator=coordinator, provider=provider)()

    assert result.status is PaperJobStatus.CONFLICT
    assert result.processed_command_count == 1
    assert result.conflict_count == 1
    assert len(coordinator.calls) == 1
