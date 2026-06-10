from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

from futures_mvp.domain.enums import (
    Direction,
    EventApplicationStatus,
    EventSource,
    ExecutionCommandResultStatus,
    ExecutionCommandType,
    ExecutionReportNormalizeResultStatus,
    ExecutionReportStatus,
    ExecutionTarget,
    MarginResultStatus,
    Offset,
    OMSEventApplyResultStatus,
    OrderStatus,
    OrderType,
    PnLPriceBasis,
    PnLResultStatus,
    PositionManagerResultStatus,
    SettlementResultStatus,
    TradeBridgeResultStatus,
)
from futures_mvp.domain.models import (
    AccountContext,
    ExecutionCommand,
    ExecutionReportNormalizeResult,
    MarginRequirement,
    MarginResult,
    MarginRule,
    MarginSnapshot,
    NormalizedExecutionReport,
    OMSEventApplyContext,
    OMSEventApplyResult,
    OrderEvent,
    OrderEventApplicationResult,
    OrderRequest,
    OrderState,
    PnLResult,
    PnLSnapshot,
    Position,
    PositionManagerResult,
    SettlementContext,
    SettlementPrice,
    SettlementResult,
    SettlementSnapshot,
    Trade,
    TradeBridgeContext,
    TradeBridgeResult,
    UnrealizedPnL,
)
from futures_mvp.interfaces.repositories import ExecutionReportConflictError
from futures_mvp.modules.execution_gateway import build_execution_command_payload_hash
from futures_mvp.modules.execution_reports import (
    ExecutionReportNormalizer,
    canonical_normalized_execution_report_payload,
)
from futures_mvp.modules.oms.state_machine import can_transition
from futures_mvp.modules.oms_event_application import OMSEventApplicationService
from futures_mvp.modules.oms_to_trade import OMSToTradeBridgeService
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
    PaperAccountingContext,
    PaperExecutionHarness,
    PaperExecutionResult,
    PaperFillPolicy,
    PaperRunContext,
    PaperRunStatus,
    PaperTradingCoordinator,
)

NOW = datetime(2026, 6, 10, 9, tzinfo=UTC)
TRADING_DAY = date(2026, 6, 10)


class InMemoryExecutionReportRepository:
    def __init__(self) -> None:
        self.reports: dict[str, NormalizedExecutionReport] = {}

    def append_normalized_report(
        self,
        report: NormalizedExecutionReport,
    ) -> NormalizedExecutionReport:
        existing = self.reports.get(report.report_id)
        if existing is not None:
            if canonical_normalized_execution_report_payload(
                existing
            ) != canonical_normalized_execution_report_payload(report):
                raise ExecutionReportConflictError("conflict")
            return existing
        self.reports[report.report_id] = report
        return report

    def get_by_report_id(self, report_id: str) -> NormalizedExecutionReport | None:
        return self.reports.get(report_id)

    def get_by_raw_report_id(self, raw_report_id: str) -> NormalizedExecutionReport | None:
        return next(
            (
                report
                for report in self.reports.values()
                if report.raw_report_id == raw_report_id
            ),
            None,
        )

    def list_by_order_id(self, order_id: str) -> list[NormalizedExecutionReport]:
        return [report for report in self.reports.values() if report.order_id == order_id]

    def list_by_command_id(self, command_id: str) -> list[NormalizedExecutionReport]:
        return [report for report in self.reports.values() if report.command_id == command_id]

    def list_by_status(
        self,
        execution_status: str,
        start_ts: datetime | None = None,
        end_ts: datetime | None = None,
    ) -> list[NormalizedExecutionReport]:
        del start_ts, end_ts
        return [
            report
            for report in self.reports.values()
            if report.execution_status.value == execution_status
        ]


class FakeExecutionReportUnitOfWork:
    def __init__(self, repository: InMemoryExecutionReportRepository) -> None:
        self.execution_reports = repository

    def __enter__(self) -> FakeExecutionReportUnitOfWork:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> bool | None:
        del exc_type, exc, tb
        return None

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


class FakeOMSOrderEventApplier:
    def __init__(self) -> None:
        self.applied_events: list[OrderEvent] = []
        self.existing_events: dict[tuple[EventSource, str], OrderEvent] = {}

    def apply_order_event(self, event: OrderEvent) -> OrderEventApplicationResult:
        if event.previous_status is not None and not can_transition(
            event.previous_status,
            event.new_status,
        ):
            return OrderEventApplicationResult(
                status=EventApplicationStatus.MISMATCH_REJECTED,
                order=_order_state(status=event.previous_status),
                reason="invalid_transition_rejected",
            )
        self.applied_events.append(event)
        self.existing_events[(event.event_source, event.external_event_id)] = event
        return OrderEventApplicationResult(
            status=EventApplicationStatus.APPLIED,
            order=_order_state(status=event.new_status, filled_quantity=event.filled_qty),
        )

    def get_by_event_key(
        self,
        event_source: EventSource,
        external_event_id: str,
    ) -> OrderEvent | None:
        return self.existing_events.get((event_source, external_event_id))


class FakeTradeRepository:
    def __init__(self) -> None:
        self.trades: dict[tuple[str, str, str], Trade] = {}

    def append_trade(self, trade: Trade) -> Trade:
        key = (trade.account_id, trade.exchange, trade.exchange_trade_id)
        existing = self.trades.get(key)
        if existing is not None:
            return existing
        stored = trade.model_copy(update={"id": str(len(self.trades) + 1)})
        self.trades[key] = stored
        return stored

    def create_or_get_trade(self, trade: Trade) -> Trade:
        return self.append_trade(trade)

    def get_by_exchange_trade_id(
        self,
        account_id: str,
        exchange: str,
        exchange_trade_id: str,
    ) -> Trade | None:
        return self.trades.get((account_id, exchange, exchange_trade_id))

    def get_by_trade_identity(
        self,
        account_id: str,
        exchange: str,
        exchange_trade_id: str,
    ) -> Trade | None:
        return self.get_by_exchange_trade_id(account_id, exchange, exchange_trade_id)

    def list_by_order_id(self, order_id: str) -> list[Trade]:
        return [trade for trade in self.trades.values() if trade.order_id == order_id]


class FakePositionManager:
    def __init__(self) -> None:
        self.trades: list[Trade] = []

    def apply_trade(self, trade: Trade) -> PositionManagerResult:
        self.trades.append(trade)
        return PositionManagerResult(
            status=PositionManagerResultStatus.APPLIED,
            position=Position(
                id="position-1",
                account_id=trade.account_id,
                instrument_id=trade.instrument_id,
                long_today_qty=trade.quantity,
                long_avg_price=trade.price,
                last_price=trade.price,
                version=1,
            ),
            trade_id=trade.id,
            account_id=trade.account_id,
            instrument_id=trade.instrument_id,
        )


class FakeMarginEngine:
    def calculate_margin(
        self,
        position: Position,
        rule: MarginRule | None,
        account: AccountContext,
        *,
        calculation_key: str,
        calculated_at: datetime,
        trading_day: date | None = None,
        config_hash: str | None = None,
        latest_price: Decimal | None = None,
        settlement_price: Decimal | None = None,
    ) -> MarginResult:
        del latest_price, settlement_price
        assert rule is not None
        assert trading_day is not None
        assert config_hash is not None
        snapshot = MarginSnapshot(
            id="margin-1",
            account_id=position.account_id,
            instrument_id=position.instrument_id,
            position_version=position.version,
            trading_day=trading_day,
            config_hash=config_hash,
            rule_id=rule.rule_id,
            rule_version=rule.rule_version,
            calculation_key=calculation_key,
            long_qty=position.long_today_qty,
            short_qty=position.short_today_qty,
            price=position.last_price,
            contract_multiplier=rule.contract_multiplier,
            initial_margin=Decimal("1000"),
            maintenance_margin=Decimal("800"),
            margin_used=Decimal("1000"),
            available_cash=account.available_cash,
            equity=account.equity,
            calculated_at=calculated_at,
        )
        return MarginResult(
            status=MarginResultStatus.CALCULATED,
            requirement=MarginRequirement(
                account_id=position.account_id,
                instrument_id=position.instrument_id,
                long_initial_margin=Decimal("1000"),
                short_initial_margin=Decimal("0"),
                total_initial_margin=Decimal("1000"),
                long_maintenance_margin=Decimal("800"),
                short_maintenance_margin=Decimal("0"),
                total_maintenance_margin=Decimal("800"),
                margin_used=Decimal("1000"),
                required_cash=Decimal("1000"),
                is_sufficient=True,
            ),
            snapshot=snapshot,
            account_id=position.account_id,
            instrument_id=position.instrument_id,
        )


class FakePnLEngine:
    def calculate_pnl(
        self,
        position: Position,
        *,
        price_basis: PnLPriceBasis,
        mark_price: Decimal | None,
        contract_multiplier: Decimal | None,
        calculation_key: str,
        calculated_at: datetime,
        trading_day: date | None = None,
        config_hash: str | None = None,
        trade: Trade | None = None,
        close_context: object | None = None,
        margin_snapshot_id: str | None = None,
    ) -> PnLResult:
        del close_context
        assert trading_day is not None
        assert config_hash is not None
        assert mark_price is not None
        assert contract_multiplier is not None
        snapshot = PnLSnapshot(
            id="pnl-1",
            account_id=position.account_id,
            instrument_id=position.instrument_id,
            position_version=position.version,
            trading_day=trading_day,
            config_hash=config_hash,
            trade_id=trade.id if trade else None,
            margin_snapshot_id=margin_snapshot_id,
            calculation_key=calculation_key,
            price_basis=price_basis,
            mark_price=mark_price,
            contract_multiplier=contract_multiplier,
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            total_pnl=Decimal("0"),
            calculated_at=calculated_at,
        )
        return PnLResult(
            status=PnLResultStatus.CALCULATED,
            unrealized=UnrealizedPnL(
                account_id=position.account_id,
                instrument_id=position.instrument_id,
                long_qty=position.long_today_qty,
                short_qty=position.short_today_qty,
                long_avg_price=position.long_avg_price,
                short_avg_price=position.short_avg_price,
                price_basis=price_basis,
                mark_price=mark_price,
                contract_multiplier=contract_multiplier,
                gross_unrealized_pnl=Decimal("0"),
                net_unrealized_pnl=Decimal("0"),
            ),
            snapshot=snapshot,
            account_id=position.account_id,
            instrument_id=position.instrument_id,
        )


class FakeSettlementEngine:
    def settle(self, context: object, *, calendar: object | None = None) -> SettlementResult:
        del calendar
        assert context is not None
        snapshot = SettlementSnapshot(
            account_id="account-1",
            trading_day=TRADING_DAY,
            calculation_key="settlement-1",
            positions_before=(),
            positions_after=(),
            settlement_prices=(),
            pnl_snapshot_ids=(),
            margin_snapshot_ids=(),
            cash_before=Decimal("100000"),
            cash_after=Decimal("100000"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            margin_used=Decimal("1000"),
            status=SettlementResultStatus.SETTLED,
            created_at=NOW,
        )
        return SettlementResult(
            status=SettlementResultStatus.SETTLED,
            snapshot=snapshot,
            account_id="account-1",
            trading_day=TRADING_DAY,
        )


class IdentityCheckingSettlementEngine:
    def __init__(self) -> None:
        self.contexts: list[SettlementContext] = []

    def settle(
        self,
        context: SettlementContext,
        *,
        calendar: object | None = None,
    ) -> SettlementResult:
        del calendar
        self.contexts.append(context)
        position = context.positions[0]
        margin_snapshot = context.margin_snapshots[0]
        pnl_snapshot = context.pnl_snapshots[0]
        if (
            margin_snapshot.account_id,
            margin_snapshot.instrument_id,
            margin_snapshot.position_version,
            margin_snapshot.trading_day,
        ) != (
            position.account_id,
            position.instrument_id,
            position.version,
            context.trading_day,
        ):
            return SettlementResult(
                status=SettlementResultStatus.CONFLICT,
                reason="margin_snapshot_identity_mismatch",
                account_id=context.account_id,
                trading_day=context.trading_day,
            )
        if (
            pnl_snapshot.account_id,
            pnl_snapshot.instrument_id,
            pnl_snapshot.position_version,
            pnl_snapshot.trading_day,
        ) != (
            position.account_id,
            position.instrument_id,
            position.version,
            context.trading_day,
        ):
            return SettlementResult(
                status=SettlementResultStatus.CONFLICT,
                reason="pnl_snapshot_identity_mismatch",
                account_id=context.account_id,
                trading_day=context.trading_day,
            )
        return SettlementResult(
            status=SettlementResultStatus.SETTLED,
            account_id=context.account_id,
            trading_day=context.trading_day,
        )


class CountingTradeBridge:
    def __init__(self, result: TradeBridgeResult | None = None) -> None:
        self.calls = 0
        self.result = result

    def create_trade(self, context: TradeBridgeContext) -> TradeBridgeResult:
        self.calls += 1
        if self.result is not None:
            return self.result
        return TradeBridgeResult(
            status=TradeBridgeResultStatus.ERROR,
            source_report_id=context.normalized_report.report_id,
            reason="unexpected trade bridge call",
        )


class DuplicateOMSEventApplication:
    def __init__(self) -> None:
        self.calls = 0

    def apply_candidate(self, context: OMSEventApplyContext) -> OMSEventApplyResult:
        self.calls += 1
        return OMSEventApplyResult(
            status=OMSEventApplyResultStatus.DUPLICATE,
            candidate=context.order_event_candidate,
            reason="order_event_duplicate",
            dry_run=False,
        )


class CountingMarginEngine:
    def __init__(self, status: MarginResultStatus = MarginResultStatus.CALCULATED) -> None:
        self.calls = 0
        self.status = status

    def calculate_margin(
        self,
        position: Position,
        rule: MarginRule | None,
        account: AccountContext,
        *,
        calculation_key: str,
        calculated_at: datetime,
        trading_day: date | None = None,
        config_hash: str | None = None,
        latest_price: Decimal | None = None,
        settlement_price: Decimal | None = None,
    ) -> MarginResult:
        del position, rule, account, calculation_key, calculated_at
        del trading_day, config_hash, latest_price, settlement_price
        self.calls += 1
        return MarginResult(status=self.status, reason=self.status.value)


class CountingPnLEngine:
    def __init__(self, status: PnLResultStatus = PnLResultStatus.CALCULATED) -> None:
        self.calls = 0
        self.status = status

    def calculate_pnl(
        self,
        position: Position,
        *,
        price_basis: PnLPriceBasis,
        mark_price: Decimal | None,
        contract_multiplier: Decimal | None,
        calculation_key: str,
        calculated_at: datetime,
        trading_day: date | None = None,
        config_hash: str | None = None,
        trade: Trade | None = None,
        close_context: object | None = None,
        margin_snapshot_id: str | None = None,
    ) -> PnLResult:
        del position, price_basis, mark_price, contract_multiplier, calculation_key
        del calculated_at, trading_day, config_hash, trade, close_context, margin_snapshot_id
        self.calls += 1
        return PnLResult(status=self.status, reason=self.status.value)


class CountingSettlementEngine:
    def __init__(
        self,
        status: SettlementResultStatus = SettlementResultStatus.SETTLED,
    ) -> None:
        self.calls = 0
        self.status = status

    def settle(self, context: object, *, calendar: object | None = None) -> SettlementResult:
        del context, calendar
        self.calls += 1
        return SettlementResult(
            status=self.status,
            reason=None if self.status is SettlementResultStatus.SETTLED else self.status.value,
        )


class CountingHarness:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, command: ExecutionCommand) -> object:
        self.calls += 1
        return PaperExecutionHarness().execute(command)


class OnlyFilledHarness:
    def execute(self, command: ExecutionCommand) -> PaperExecutionResult:
        result = PaperExecutionHarness().execute(command)
        return PaperExecutionResult(
            status=result.status,
            command_result=result.command_result,
            raw_reports=(result.raw_reports[-1],),
            translation_result=result.translation_result,
            reason=result.reason,
        )


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


def _order_state(
    *,
    status: OrderStatus = OrderStatus.SUBMITTED,
    filled_quantity: Decimal | None = None,
) -> OrderState:
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
        status=status,
        filled_quantity=filled_quantity or Decimal("0"),
    )


def _migration(compatible: bool = True) -> MigrationReadinessReport:
    return MigrationReadinessReport(
        compatible=compatible,
        current_revision="0016",
        expected_revision="0016",
        reason=None if compatible else "db migration revision is incompatible",
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


def _capital_context(order_size: Decimal = Decimal("2")) -> CapitalControlContext:
    return CapitalControlContext(
        order_size=order_size,
        projected_position_size=Decimal("2"),
        daily_loss=Decimal("0"),
        account_id="account-1",
        instrument_id="rb2601",
    )


def _accounting_context() -> PaperAccountingContext:
    return PaperAccountingContext(
        account=AccountContext(
            account_id="account-1",
            equity=Decimal("100000"),
            available_cash=Decimal("90000"),
            frozen_cash=Decimal("0"),
            snapshot_time=NOW,
        ),
        margin_rule=MarginRule(
            rule_id="rule-1",
            instrument_id="rb2601",
            exchange="SHFE",
            contract_multiplier=Decimal("10"),
            long_initial_margin_rate=Decimal("0.1"),
            short_initial_margin_rate=Decimal("0.1"),
            long_maintenance_margin_rate=Decimal("0.08"),
            short_maintenance_margin_rate=Decimal("0.08"),
            price_basis="LAST_PRICE",
            rule_version="v1",
        ),
        latest_price=Decimal("3500"),
        mark_price=Decimal("3500"),
        contract_multiplier=Decimal("10"),
        calculated_at=NOW,
        settlement_context=object(),
    )


def _settlement_context_with_stale_snapshots() -> SettlementContext:
    position = Position(
        id="stale-position",
        account_id="account-1",
        instrument_id="rb2601",
        version=99,
    )
    stale_margin = MarginSnapshot(
        id="stale-margin",
        account_id="account-1",
        instrument_id="rb2601",
        position_version=98,
        trading_day=TRADING_DAY,
        config_hash="paper-config-v1",
        calculation_key="stale-margin",
        long_qty=Decimal("0"),
        short_qty=Decimal("0"),
        price=Decimal("3500"),
        contract_multiplier=Decimal("10"),
        initial_margin=Decimal("0"),
        maintenance_margin=Decimal("0"),
        margin_used=Decimal("0"),
        available_cash=Decimal("90000"),
        equity=Decimal("100000"),
        calculated_at=NOW,
    )
    stale_pnl = PnLSnapshot(
        id="stale-pnl",
        account_id="account-1",
        instrument_id="rb2601",
        position_version=98,
        trading_day=TRADING_DAY,
        config_hash="paper-config-v1",
        calculation_key="stale-pnl",
        price_basis=PnLPriceBasis.LAST_PRICE,
        mark_price=Decimal("3500"),
        contract_multiplier=Decimal("10"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        total_pnl=Decimal("0"),
        calculated_at=NOW,
    )
    return SettlementContext(
        account_id="account-1",
        trading_day=TRADING_DAY,
        account_before=AccountContext(
            account_id="account-1",
            equity=Decimal("100000"),
            available_cash=Decimal("90000"),
            frozen_cash=Decimal("0"),
            snapshot_time=NOW,
        ),
        positions=(position,),
        pnl_snapshots=(stale_pnl,),
        margin_snapshots=(stale_margin,),
        settlement_prices=(
            SettlementPrice(
                instrument_id="rb2601",
                exchange="SHFE",
                trading_day=TRADING_DAY,
                price=Decimal("3500"),
                received_at=NOW,
            ),
        ),
        calculation_key="paper-settlement",
        settled_at=NOW,
    )


def _context(
    *,
    mode: RolloutMode = RolloutMode.PAPER,
    safety_config: SafetyConfig | None = None,
    migration: MigrationReadinessReport | None = None,
    capital_context: CapitalControlContext | None = None,
    accounting: PaperAccountingContext | None = None,
) -> PaperRunContext:
    config = safety_config or _safety_config(mode=mode)
    return PaperRunContext(
        rollout_mode=mode,
        safety_config=config,
        migration=migration or _migration(),
        capital_control_context=capital_context or _capital_context(),
        account_id="account-1",
        trading_day=TRADING_DAY,
        config_hash="paper-config-v1",
        command=_command(),
        current_order_state=_order_state(),
        symbol="rb",
        trade_instrument_id="rb2601",
        accounting=accounting,
    )


def _normalizer(repository: InMemoryExecutionReportRepository) -> ExecutionReportNormalizer:
    return ExecutionReportNormalizer(
        lambda: FakeExecutionReportUnitOfWork(repository),
        clock=lambda: NOW,
    )


def _oms_event_application() -> OMSEventApplicationService:
    oms_applier = FakeOMSOrderEventApplier()
    return OMSEventApplicationService(
        oms_applier=oms_applier,
        event_lookup=oms_applier,
    )


def _coordinator(
    *,
    repository: InMemoryExecutionReportRepository | None = None,
    harness: object | None = None,
    fill_policy: PaperFillPolicy = PaperFillPolicy.IMMEDIATE_FULL_FILL,
    position_manager: FakePositionManager | None = None,
    settlement_engine: object | None = None,
) -> tuple[PaperTradingCoordinator, FakePositionManager, FakeTradeRepository]:
    report_repository = repository or InMemoryExecutionReportRepository()
    oms_applier = FakeOMSOrderEventApplier()
    trades = FakeTradeRepository()
    positions = position_manager or FakePositionManager()
    return (
        PaperTradingCoordinator(
            harness=harness
            or PaperExecutionHarness(fill_policy=fill_policy),
            normalizer=_normalizer(report_repository),
            oms_event_application=OMSEventApplicationService(
                oms_applier=oms_applier,
                event_lookup=oms_applier,
            ),
            oms_to_trade=OMSToTradeBridgeService(trades),
            position_manager=positions,
            margin_engine=FakeMarginEngine(),
            pnl_engine=FakePnLEngine(),
            settlement_engine=settlement_engine or FakeSettlementEngine(),
        ),
        positions,
        trades,
    )


def _trade(*, exchange_trade_id: str = "exchange-trade-1") -> Trade:
    return Trade(
        id="trade-1",
        account_id="account-1",
        exchange="SHFE",
        exchange_trade_id=exchange_trade_id,
        order_id="order-1",
        client_order_id="client-1",
        instrument_id="rb2601",
        trade_instrument_id="rb2601",
        symbol="rb",
        direction=Direction.BUY,
        offset=Offset.OPEN,
        price=Decimal("3500"),
        quantity=Decimal("2"),
        trade_time=NOW,
        trading_day=TRADING_DAY,
        source_report_id="report-1",
        source_order_event_id="event-1",
    )


def test_safety_preflight_rejects_non_paper_without_downstream() -> None:
    harness = CountingHarness()
    coordinator, _positions, _trades = _coordinator(harness=harness)

    result = coordinator.run(
        _context(
            mode=RolloutMode.SIM,
            safety_config=_safety_config(mode=RolloutMode.SIM),
        )
    )

    assert result.status is PaperRunStatus.REJECTED_NON_PAPER_MODE
    assert harness.calls == 0
    assert result.raw_reports == ()


def test_safety_preflight_rejects_kill_switch_migration_and_capital() -> None:
    for context in [
        _context(safety_config=_safety_config(kill_switch=KillSwitchConfig(global_kill_switch=True))),
        _context(migration=_migration(False)),
        _context(capital_context=_capital_context(order_size=Decimal("20"))),
    ]:
        harness = CountingHarness()
        coordinator, _positions, _trades = _coordinator(harness=harness)

        result = coordinator.run(context)

        assert result.status in {
            PaperRunStatus.REJECTED_SAFETY_GATE,
            PaperRunStatus.REJECTED_CAPITAL_CONTROL,
        }
        assert harness.calls == 0
        assert result.trades == ()


def test_full_fill_e2e_reaches_trade_position_and_accounting() -> None:
    coordinator, positions, trades = _coordinator()

    result = coordinator.run(_context(accounting=_accounting_context()))

    assert result.status is PaperRunStatus.COMPLETED
    assert result.command_result is not None
    assert result.command_result.status is ExecutionCommandResultStatus.ACCEPTED_BY_ADAPTER
    assert [report.report_type for report in result.raw_reports] == ["acked", "filled"]
    assert [
        report.execution_status for report in result.normalized_reports
    ] == [ExecutionReportStatus.ACKED, ExecutionReportStatus.FILLED]
    assert [
        candidate.execution_status for candidate in result.order_event_candidates
    ] == [ExecutionReportStatus.ACKED, ExecutionReportStatus.FILLED]
    assert [event.new_status for event in result.applied_order_events] == [
        OrderStatus.ACKED,
        OrderStatus.FILLED,
    ]
    assert result.trade_results[0].status is TradeBridgeResultStatus.CREATED
    assert (
        result.trades[0].source_order_event_id
        == result.applied_order_events[1].external_event_id
    )
    assert result.position_results[0].status is PositionManagerResultStatus.APPLIED
    assert result.margin_results[0].status is MarginResultStatus.CALCULATED
    assert result.pnl_results[0].status is PnLResultStatus.CALCULATED
    assert result.settlement_results[0].status is SettlementResultStatus.SETTLED
    assert positions.trades == [result.trades[0]]
    assert len(trades.trades) == 1


def test_paper_settlement_uses_current_run_margin_and_pnl_snapshot_identity() -> None:
    settlement = IdentityCheckingSettlementEngine()
    coordinator, _positions, _trades = _coordinator(settlement_engine=settlement)
    accounting = replace(
        _accounting_context(),
        settlement_context=_settlement_context_with_stale_snapshots(),
    )

    result = coordinator.run(_context(accounting=accounting))

    assert result.status is PaperRunStatus.COMPLETED
    assert result.settlement_results[0].status is SettlementResultStatus.SETTLED
    used_context = settlement.contexts[0]
    assert used_context.positions[0].version == 1
    assert used_context.margin_snapshots[0].id == "margin-1"
    assert used_context.margin_snapshots[0].position_version == 1
    assert used_context.pnl_snapshots[0].id == "pnl-1"
    assert used_context.pnl_snapshots[0].position_version == 1


def test_direct_submitted_to_filled_remains_rejected_by_oms_transition() -> None:
    coordinator, positions, trades = _coordinator(harness=OnlyFilledHarness())

    result = coordinator.run(_context(accounting=_accounting_context()))

    assert result.status is PaperRunStatus.CONFLICT
    assert result.reason == "invalid_transition_rejected"
    assert result.normalized_reports[0].execution_status is ExecutionReportStatus.FILLED
    assert result.oms_results[0].status is OMSEventApplyResultStatus.CONFLICT
    assert result.trades == ()
    assert positions.trades == []
    assert trades.trades == {}


def test_reject_report_applies_oms_but_creates_no_trade_or_position_or_accounting() -> None:
    coordinator, positions, trades = _coordinator(fill_policy=PaperFillPolicy.IMMEDIATE_REJECT)

    result = coordinator.run(_context(accounting=_accounting_context()))

    assert result.status is PaperRunStatus.APPLIED
    assert result.raw_reports[0].report_type == "rejected"
    assert result.normalized_reports[0].execution_status is ExecutionReportStatus.REJECTED
    assert result.applied_order_events[0].new_status is OrderStatus.REJECTED_BY_EXCHANGE
    assert result.trade_results == ()
    assert result.trades == ()
    assert result.position_results == ()
    assert result.margin_results == ()
    assert result.pnl_results == ()
    assert result.settlement_results == ()
    assert positions.trades == []
    assert trades.trades == {}


def test_timeout_and_uncertain_have_no_report_or_downstream_mutation() -> None:
    for policy in [
        PaperFillPolicy.PRE_SEND_TIMEOUT,
        PaperFillPolicy.POST_SEND_UNCERTAIN,
    ]:
        coordinator, positions, trades = _coordinator(fill_policy=policy)

        result = coordinator.run(_context(accounting=_accounting_context()))

        assert result.status is PaperRunStatus.REJECTED_NO_REPORT
        assert result.raw_reports == ()
        assert result.normalized_reports == ()
        assert result.applied_order_events == ()
        assert result.trades == ()
        assert positions.trades == []
        assert trades.trades == {}


def test_duplicate_report_is_noop_and_does_not_reapply_downstream() -> None:
    repository = InMemoryExecutionReportRepository()
    first, _positions, _trades = _coordinator(repository=repository)
    second, positions, trades = _coordinator(repository=repository)

    first_result = first.run(_context())
    duplicate = second.run(_context())

    assert first_result.status is PaperRunStatus.COMPLETED
    assert duplicate.status is PaperRunStatus.DUPLICATE
    assert duplicate.duplicate is True
    assert (
        duplicate.normalized_reports[0].raw_report_id
        == first_result.raw_reports[0].raw_report_id
    )
    assert duplicate.applied_order_events == ()
    assert duplicate.trades == ()
    assert positions.trades == []
    assert trades.trades == {}


def test_duplicate_oms_event_noops_without_trade_or_downstream() -> None:
    trade_bridge = CountingTradeBridge()
    position_manager = FakePositionManager()
    coordinator = PaperTradingCoordinator(
        normalizer=_normalizer(InMemoryExecutionReportRepository()),
        oms_event_application=DuplicateOMSEventApplication(),
        oms_to_trade=trade_bridge,
        position_manager=position_manager,
        margin_engine=FakeMarginEngine(),
        pnl_engine=FakePnLEngine(),
        settlement_engine=FakeSettlementEngine(),
    )

    result = coordinator.run(_context(accounting=_accounting_context()))

    assert result.status is PaperRunStatus.DUPLICATE
    assert result.duplicate is True
    assert trade_bridge.calls == 0
    assert position_manager.trades == []
    assert result.trade_results == ()
    assert result.position_results == ()
    assert result.margin_results == ()
    assert result.pnl_results == ()
    assert result.settlement_results == ()


def test_duplicate_trade_noops_without_position_or_accounting() -> None:
    trade_bridge = CountingTradeBridge(
        TradeBridgeResult(
            status=TradeBridgeResultStatus.DUPLICATE,
            trade=_trade(),
            source_report_id="report-1",
            source_order_event_id="event-1",
        )
    )
    position_manager = FakePositionManager()
    coordinator = PaperTradingCoordinator(
        normalizer=_normalizer(InMemoryExecutionReportRepository()),
        oms_event_application=_oms_event_application(),
        oms_to_trade=trade_bridge,
        position_manager=position_manager,
        margin_engine=FakeMarginEngine(),
        pnl_engine=FakePnLEngine(),
        settlement_engine=FakeSettlementEngine(),
    )

    result = coordinator.run(_context(accounting=_accounting_context()))

    assert result.status is PaperRunStatus.DUPLICATE
    assert result.duplicate is True
    assert trade_bridge.calls == 1
    assert position_manager.trades == []
    assert result.trades == ()
    assert result.position_results == ()
    assert result.margin_results == ()
    assert result.pnl_results == ()
    assert result.settlement_results == ()


def test_trade_conflict_stops_downstream() -> None:
    trade_bridge = CountingTradeBridge(
        TradeBridgeResult(
            status=TradeBridgeResultStatus.CONFLICT,
            source_report_id="report-1",
            reason="trade canonical conflict",
        )
    )
    position_manager = FakePositionManager()
    coordinator = PaperTradingCoordinator(
        normalizer=_normalizer(InMemoryExecutionReportRepository()),
        oms_event_application=_oms_event_application(),
        oms_to_trade=trade_bridge,
        position_manager=position_manager,
    )

    result = coordinator.run(_context(accounting=_accounting_context()))

    assert result.status is PaperRunStatus.CONFLICT
    assert result.conflict is True
    assert position_manager.trades == []
    assert result.position_results == ()


class ConflictPositionManager:
    def __init__(self, status: PositionManagerResultStatus) -> None:
        self.trades: list[Trade] = []
        self.status = status

    def apply_trade(self, trade: Trade) -> PositionManagerResult:
        self.trades.append(trade)
        return PositionManagerResult(status=self.status, reason=self.status.value)


def test_position_conflict_or_error_stops_accounting() -> None:
    for status in [PositionManagerResultStatus.CONFLICT, PositionManagerResultStatus.ERROR]:
        position_manager = ConflictPositionManager(status)
        margin = CountingMarginEngine()
        pnl = CountingPnLEngine()
        settlement = CountingSettlementEngine()
        coordinator = PaperTradingCoordinator(
            normalizer=_normalizer(InMemoryExecutionReportRepository()),
            oms_event_application=_oms_event_application(),
            oms_to_trade=OMSToTradeBridgeService(FakeTradeRepository()),
            position_manager=position_manager,
            margin_engine=margin,
            pnl_engine=pnl,
            settlement_engine=settlement,
        )

        result = coordinator.run(_context(accounting=_accounting_context()))

        assert result.status in {PaperRunStatus.CONFLICT, PaperRunStatus.ERROR}
        assert position_manager.trades
        assert margin.calls == 0
        assert pnl.calls == 0
        assert settlement.calls == 0


def test_accounting_conflict_or_error_stops_later_accounting() -> None:
    margin = CountingMarginEngine(MarginResultStatus.CONFLICT)
    pnl = CountingPnLEngine()
    settlement = CountingSettlementEngine()
    coordinator = PaperTradingCoordinator(
        normalizer=_normalizer(InMemoryExecutionReportRepository()),
        oms_event_application=_oms_event_application(),
        oms_to_trade=OMSToTradeBridgeService(FakeTradeRepository()),
        position_manager=FakePositionManager(),
        margin_engine=margin,
        pnl_engine=pnl,
        settlement_engine=settlement,
    )

    result = coordinator.run(_context(accounting=_accounting_context()))

    assert result.status is PaperRunStatus.CONFLICT
    assert margin.calls == 1
    assert pnl.calls == 0
    assert settlement.calls == 0

    pnl_conflict = CountingPnLEngine(PnLResultStatus.CONFLICT)
    settlement_after_pnl = CountingSettlementEngine()
    coordinator = PaperTradingCoordinator(
        normalizer=_normalizer(InMemoryExecutionReportRepository()),
        oms_event_application=_oms_event_application(),
        oms_to_trade=OMSToTradeBridgeService(FakeTradeRepository()),
        position_manager=FakePositionManager(),
        pnl_engine=pnl_conflict,
        settlement_engine=settlement_after_pnl,
    )

    result = coordinator.run(_context(accounting=_accounting_context()))

    assert result.status is PaperRunStatus.CONFLICT
    assert pnl_conflict.calls == 1
    assert settlement_after_pnl.calls == 0


class ConflictNormalizer:
    def normalize(self, raw_report: object) -> ExecutionReportNormalizeResult:
        del raw_report
        return ExecutionReportNormalizeResult(
            status=ExecutionReportNormalizeResultStatus.CONFLICT,
            reason="normalized_execution_report_raw_identity_conflict",
        )


def test_report_conflict_stops_downstream() -> None:
    oms_applier = FakeOMSOrderEventApplier()
    trades = FakeTradeRepository()
    positions = FakePositionManager()
    coordinator = PaperTradingCoordinator(
        normalizer=ConflictNormalizer(),
        oms_event_application=OMSEventApplicationService(oms_applier),
        oms_to_trade=OMSToTradeBridgeService(trades),
        position_manager=positions,
    )

    result = coordinator.run(_context())

    assert result.status is PaperRunStatus.CONFLICT
    assert result.conflict is True
    assert result.applied_order_events == ()
    assert result.trades == ()
    assert positions.trades == []
