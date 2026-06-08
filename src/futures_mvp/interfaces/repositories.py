from datetime import date, datetime
from decimal import Decimal
from types import TracebackType
from typing import Protocol, runtime_checkable

from futures_mvp.domain.enums import BarTimeframe, EventSource, ExecutionReportStatus, OrderStatus
from futures_mvp.domain.errors import FuturesMvpError
from futures_mvp.domain.models import (
    AccountSnapshot,
    Bar,
    ExecutionCommand,
    FeatureSnapshot,
    MarginSnapshot,
    NormalizedExecutionReport,
    OrderEvent,
    OrderIntent,
    OrderRequest,
    OrderState,
    PnLSnapshot,
    Position,
    PositionEvent,
    SettlementSnapshot,
    SignalCandidate,
    SignalLifecycleEvent,
    Tick,
    Trade,
    TradingRiskResult,
)


class RepositoryError(FuturesMvpError):
    """Base error for repository port failures."""


class OrderNotFoundError(RepositoryError):
    """Raised when an order cannot be found by the requested identity."""


class DuplicateClientOrderError(RepositoryError):
    """Raised when a client_order_id already exists."""


class IdempotencyConflictError(DuplicateClientOrderError):
    """Raised when a client_order_id is reused with a different canonical payload."""


class EventAlreadyExistsError(RepositoryError):
    """Raised when an order event idempotency key already exists."""


class OptimisticLockError(RepositoryError):
    """Raised when an order version check fails during persistence."""


class TradeIdempotencyConflictError(RepositoryError):
    """Raised when an exchange trade id is reused with different trade facts."""


class PositionEventConflictError(RepositoryError):
    """Raised when an exchange trade id is reused with different position facts."""


class MarginSnapshotConflictError(RepositoryError):
    """Raised when a margin snapshot identity is reused with different facts."""


class PnLSnapshotConflictError(RepositoryError):
    """Raised when a PnL calculation key is reused with different facts."""


class SettlementSnapshotConflictError(RepositoryError):
    """Raised when a settlement account/day is reused with different facts."""


class MarketDataConflictError(RepositoryError):
    """Raised when a market data identity is reused with different facts."""


class FeatureSnapshotConflictError(RepositoryError):
    """Raised when a feature snapshot identity is reused with different facts."""


class SignalCandidateConflictError(RepositoryError):
    """Raised when a signal candidate identity is reused with different facts."""


class SignalLifecycleConflictError(RepositoryError):
    """Raised when a signal lifecycle event cannot be appended consistently."""


class TradingRiskResultConflictError(RepositoryError):
    """Raised when a trading risk result identity is reused with different facts."""


class OrderIntentConflictError(RepositoryError):
    """Raised when an order intent identity is reused with different facts."""


class ExecutionCommandConflictError(RepositoryError):
    """Raised when an execution command identity is reused with different facts."""


class ExecutionReportConflictError(RepositoryError):
    """Raised when an execution report identity is reused with different facts."""


@runtime_checkable
class OrderRepository(Protocol):
    def create_order(self, order_request: OrderRequest, *, client_order_id: str) -> OrderState: ...

    def get_by_id(self, order_id: str) -> OrderState | None: ...

    def get_by_client_order_id(self, client_order_id: str) -> OrderState | None: ...

    def update_status(
        self,
        order_id: str,
        new_status: OrderStatus,
        *,
        expected_version: int | None = None,
    ) -> OrderState: ...

    def list_open_orders(self) -> list[OrderState]: ...


@runtime_checkable
class OrderEventRepository(Protocol):
    def append_event(self, event: OrderEvent) -> OrderEvent: ...

    def get_by_event_key(
        self,
        event_source: EventSource,
        external_event_id: str,
    ) -> OrderEvent | None: ...

    def list_by_order_id(self, order_id: str) -> list[OrderEvent]: ...


@runtime_checkable
class TradeRepository(Protocol):
    def append_trade(self, trade: Trade) -> Trade: ...

    def create_or_get_trade(self, trade: Trade) -> Trade: ...

    def get_by_exchange_trade_id(
        self,
        account_id: str,
        exchange: str,
        exchange_trade_id: str,
    ) -> Trade | None: ...

    def get_by_trade_identity(
        self,
        account_id: str,
        exchange: str,
        exchange_trade_id: str,
    ) -> Trade | None: ...

    def list_by_order_id(self, order_id: str) -> list[Trade]: ...


@runtime_checkable
class PositionRepository(Protocol):
    def get_by_account_instrument(
        self,
        account_id: str,
        instrument_id: str,
    ) -> Position | None: ...

    def create_or_get_position(self, account_id: str, instrument_id: str) -> Position: ...

    def update_position(
        self,
        position: Position,
        *,
        expected_version: int | None = None,
    ) -> Position: ...

    def update_margin_used(
        self,
        account_id: str,
        instrument_id: str,
        margin_used: Decimal,
        *,
        expected_version: int | None = None,
    ) -> Position: ...

    def update_pnl(
        self,
        account_id: str,
        instrument_id: str,
        realized_pnl: Decimal,
        unrealized_pnl: Decimal,
        *,
        expected_version: int | None = None,
    ) -> Position: ...

    def roll_today_to_yesterday_for_settlement(
        self,
        account_id: str,
        instrument_id: str,
        *,
        expected_version: int,
    ) -> Position: ...

    def list_by_account(self, account_id: str) -> list[Position]: ...


@runtime_checkable
class PositionEventRepository(Protocol):
    def append_position_event(self, event: PositionEvent) -> PositionEvent: ...

    def get_by_trade_key(
        self,
        account_id: str,
        exchange: str,
        exchange_trade_id: str,
    ) -> PositionEvent | None: ...

    def list_by_position(self, account_id: str, instrument_id: str) -> list[PositionEvent]: ...

    def list_by_account(self, account_id: str) -> list[PositionEvent]: ...


@runtime_checkable
class MarginSnapshotRepository(Protocol):
    def append_margin_snapshot(self, snapshot: MarginSnapshot) -> MarginSnapshot: ...

    def get_latest(self, account_id: str, instrument_id: str) -> MarginSnapshot | None: ...

    def list_by_account(self, account_id: str) -> list[MarginSnapshot]: ...

    def get_by_position_version(
        self,
        account_id: str,
        instrument_id: str,
        position_version: int,
    ) -> MarginSnapshot | None: ...

    def get_by_accounting_identity(
        self,
        account_id: str,
        instrument_id: str,
        position_version: int,
        trading_day: date,
        config_hash: str,
    ) -> MarginSnapshot | None: ...


@runtime_checkable
class PnLSnapshotRepository(Protocol):
    def append_pnl_snapshot(self, snapshot: PnLSnapshot) -> PnLSnapshot: ...

    def get_latest(self, account_id: str, instrument_id: str) -> PnLSnapshot | None: ...

    def list_by_account(self, account_id: str) -> list[PnLSnapshot]: ...

    def get_by_calculation_key(
        self,
        account_id: str,
        instrument_id: str,
        calculation_key: str,
    ) -> PnLSnapshot | None: ...

    def get_by_position_version(
        self,
        account_id: str,
        instrument_id: str,
        position_version: int,
    ) -> PnLSnapshot | None: ...

    def get_by_accounting_identity(
        self,
        account_id: str,
        instrument_id: str,
        position_version: int,
        trading_day: date,
        config_hash: str,
    ) -> PnLSnapshot | None: ...


@runtime_checkable
class AccountSnapshotRepository(Protocol):
    def append_account_snapshot(self, snapshot: AccountSnapshot) -> AccountSnapshot: ...

    def get_by_id(self, snapshot_id: str) -> AccountSnapshot | None: ...

    def get_latest(self, account_id: str) -> AccountSnapshot | None: ...

    def list_by_account(self, account_id: str) -> list[AccountSnapshot]: ...


@runtime_checkable
class SettlementSnapshotRepository(Protocol):
    def append_settlement_snapshot(self, snapshot: SettlementSnapshot) -> SettlementSnapshot: ...

    def get_by_account_trading_day(
        self,
        account_id: str,
        trading_day: date,
    ) -> SettlementSnapshot | None: ...

    def get_by_calculation_key(
        self,
        account_id: str,
        trading_day: date,
        calculation_key: str,
    ) -> SettlementSnapshot | None: ...

    def list_by_account(self, account_id: str) -> list[SettlementSnapshot]: ...

    def list_by_trading_day(self, trading_day: date) -> list[SettlementSnapshot]: ...


@runtime_checkable
class MarketTickRepository(Protocol):
    def append_tick(self, tick: Tick) -> Tick: ...

    def get_by_identity(
        self,
        exchange: str,
        instrument_id: str,
        ts: datetime,
        source: str,
    ) -> Tick | None: ...

    def list_by_instrument(
        self,
        exchange: str,
        instrument_id: str,
        start_ts: datetime,
        end_ts: datetime,
    ) -> list[Tick]: ...

    def list_by_trading_day(
        self,
        exchange: str,
        instrument_id: str,
        trading_day: date,
    ) -> list[Tick]: ...


@runtime_checkable
class MarketBarRepository(Protocol):
    def append_bar(self, bar: Bar) -> Bar: ...

    def get_by_identity(
        self,
        exchange: str,
        instrument_id: str,
        timeframe: BarTimeframe,
        bar_ts: datetime,
        source: str,
    ) -> Bar | None: ...

    def list_by_instrument(
        self,
        exchange: str,
        instrument_id: str,
        timeframe: BarTimeframe,
        start_bar_ts: datetime,
        end_bar_ts: datetime,
    ) -> list[Bar]: ...

    def list_by_trading_day(
        self,
        exchange: str,
        instrument_id: str,
        timeframe: BarTimeframe,
        trading_day: date,
    ) -> list[Bar]: ...


@runtime_checkable
class FeatureSnapshotRepository(Protocol):
    def append_feature_snapshot(self, snapshot: FeatureSnapshot) -> FeatureSnapshot: ...

    def get_by_identity(
        self,
        exchange: str,
        instrument_id: str,
        timeframe: BarTimeframe,
        bar_ts: datetime,
        feature_version: str,
        feature_config_hash: str,
    ) -> FeatureSnapshot | None: ...

    def list_by_instrument(
        self,
        exchange: str,
        instrument_id: str,
        timeframe: BarTimeframe,
        start_bar_ts: datetime,
        end_bar_ts: datetime,
    ) -> list[FeatureSnapshot]: ...

    def list_by_trading_day(
        self,
        exchange: str,
        instrument_id: str,
        timeframe: BarTimeframe,
        trading_day: date,
    ) -> list[FeatureSnapshot]: ...


@runtime_checkable
class SignalCandidateRepository(Protocol):
    def append_signal_candidate(self, candidate: SignalCandidate) -> SignalCandidate: ...

    def get_by_signal_id(self, signal_id: str) -> SignalCandidate | None: ...

    def list_by_strategy(
        self,
        strategy_name: str,
        strategy_version: str,
        start_bar_ts: datetime,
        end_bar_ts: datetime,
    ) -> list[SignalCandidate]: ...

    def list_by_instrument(
        self,
        exchange: str,
        instrument_id: str,
        timeframe: BarTimeframe,
        start_bar_ts: datetime,
        end_bar_ts: datetime,
    ) -> list[SignalCandidate]: ...


@runtime_checkable
class SignalEventRepository(Protocol):
    def append_signal_event(self, event: SignalLifecycleEvent) -> SignalLifecycleEvent: ...

    def get_by_event_key(self, event_key: str) -> SignalLifecycleEvent | None: ...

    def list_by_signal_id(self, signal_id: str) -> list[SignalLifecycleEvent]: ...

    def get_latest_status(self, signal_id: str) -> SignalLifecycleEvent | None: ...


@runtime_checkable
class TradingRiskResultRepository(Protocol):
    def append_risk_result(self, result: TradingRiskResult) -> TradingRiskResult: ...

    def get_by_risk_result_id(self, risk_result_id: str) -> TradingRiskResult | None: ...

    def list_by_signal_id(self, signal_id: str) -> list[TradingRiskResult]: ...


@runtime_checkable
class OrderIntentRepository(Protocol):
    def append_order_intent(self, intent: OrderIntent) -> OrderIntent: ...

    def get_by_intent_id(self, intent_id: str) -> OrderIntent | None: ...

    def list_by_signal_id(self, signal_id: str) -> list[OrderIntent]: ...


@runtime_checkable
class ExecutionCommandRepository(Protocol):
    def append_execution_command(self, command: ExecutionCommand) -> ExecutionCommand: ...

    def get_by_command_id(self, command_id: str) -> ExecutionCommand | None: ...

    def list_by_order_id(self, order_id: str) -> list[ExecutionCommand]: ...

    def list_by_target(
        self,
        execution_target: str,
        start_ts: datetime | None = None,
        end_ts: datetime | None = None,
    ) -> list[ExecutionCommand]: ...


@runtime_checkable
class ExecutionReportRepository(Protocol):
    def append_normalized_report(
        self,
        report: NormalizedExecutionReport,
    ) -> NormalizedExecutionReport: ...

    def get_by_report_id(self, report_id: str) -> NormalizedExecutionReport | None: ...

    def list_by_order_id(self, order_id: str) -> list[NormalizedExecutionReport]: ...

    def list_by_command_id(self, command_id: str) -> list[NormalizedExecutionReport]: ...

    def list_by_status(
        self,
        execution_status: ExecutionReportStatus | str,
        start_ts: datetime | None = None,
        end_ts: datetime | None = None,
    ) -> list[NormalizedExecutionReport]: ...


@runtime_checkable
class UnitOfWork(Protocol):
    orders: OrderRepository
    order_events: OrderEventRepository
    trades: TradeRepository
    positions: PositionRepository
    position_events: PositionEventRepository
    margin_snapshots: MarginSnapshotRepository
    pnl_snapshots: PnLSnapshotRepository
    account_snapshots: AccountSnapshotRepository
    settlement_snapshots: SettlementSnapshotRepository
    market_ticks: MarketTickRepository
    market_bars: MarketBarRepository
    feature_snapshots: FeatureSnapshotRepository
    signal_candidates: SignalCandidateRepository
    signal_events: SignalEventRepository
    trading_risk_results: TradingRiskResultRepository
    order_intents: OrderIntentRepository
    execution_commands: ExecutionCommandRepository
    execution_reports: ExecutionReportRepository

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def __enter__(self) -> "UnitOfWork": ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None: ...


@runtime_checkable
class MarketDataUnitOfWork(Protocol):
    market_ticks: MarketTickRepository
    market_bars: MarketBarRepository

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def __enter__(self) -> "MarketDataUnitOfWork": ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None: ...


@runtime_checkable
class FeatureUnitOfWork(Protocol):
    feature_snapshots: FeatureSnapshotRepository

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def __enter__(self) -> "FeatureUnitOfWork": ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None: ...


@runtime_checkable
class StrategySignalUnitOfWork(Protocol):
    signal_candidates: SignalCandidateRepository
    signal_events: SignalEventRepository

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def __enter__(self) -> "StrategySignalUnitOfWork": ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None: ...


@runtime_checkable
class TradingWorkflowUnitOfWork(Protocol):
    trading_risk_results: TradingRiskResultRepository
    order_intents: OrderIntentRepository

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def __enter__(self) -> "TradingWorkflowUnitOfWork": ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None: ...


@runtime_checkable
class ExecutionGatewayUnitOfWork(Protocol):
    execution_commands: ExecutionCommandRepository

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def __enter__(self) -> "ExecutionGatewayUnitOfWork": ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None: ...


@runtime_checkable
class ExecutionReportUnitOfWork(Protocol):
    execution_reports: ExecutionReportRepository

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def __enter__(self) -> "ExecutionReportUnitOfWork": ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None: ...
