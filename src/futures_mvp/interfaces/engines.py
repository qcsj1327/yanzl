from datetime import datetime
from decimal import Decimal
from typing import Protocol

from futures_mvp.domain.models import (
    OrderEvent,
    OrderEventApplicationResult,
    OrderRequest,
    OrderState,
    RiskResult,
    Signal,
    Trade,
)
from futures_mvp.modules.execution.models import ExchangeReport


class MarketDataMock(Protocol):
    def latest_price(self, instrument_id: str) -> Decimal: ...


class StrategyEngine(Protocol):
    def on_market_data(self, market_data: object) -> list[Signal]: ...


class FuturesRiskEngine(Protocol):
    def check_order(self, signal: Signal) -> RiskResult: ...


class OMS(Protocol):
    def create_order(self, request: OrderRequest, *, client_order_id: str) -> OrderState: ...

    def apply_risk_result(
        self,
        order_id: str,
        risk_result: RiskResult,
        *,
        external_event_id: str,
        occurred_at: datetime | None = None,
    ) -> OrderEventApplicationResult: ...

    def apply_order_event(self, event: OrderEvent) -> OrderEventApplicationResult: ...

    def recover_order(self, order_id: str) -> OrderEventApplicationResult: ...

    def get_by_client_order_id(self, client_order_id: str) -> OrderState | None: ...


class EMS(Protocol):
    """Execution command port only; report surface is a later interface gate."""

    def submit(self, order: OrderState) -> None: ...

    def cancel(self, order: OrderState) -> None: ...


class ExchangeCommandPort(Protocol):
    """Execution venue command port; reports are delivered through a separate sink."""

    def submit_limit_order(self, order: OrderState) -> None: ...

    def cancel_order(self, order: OrderState) -> None: ...


class ExecutionReportSink(Protocol):
    """Local in-memory report surface for the current execution runtime layer."""

    def append(self, report: ExchangeReport) -> None: ...

    def list_reports(self) -> list[ExchangeReport]: ...

    def drain_reports(self) -> list[ExchangeReport]: ...


class MockFuturesExchange(ExchangeCommandPort, Protocol):
    """Mock exchange command port only; methods do not return exchange reports."""

    def submit_limit_order(self, order: OrderState) -> None: ...

    def cancel_order(self, order: OrderState) -> None: ...


class TradeProcessor(Protocol):
    def apply_trade(self, trade: Trade) -> bool: ...


class FuturesPositionManager(Protocol):
    def apply_trade(self, trade: Trade) -> None: ...

    def roll_today_to_yesterday(self, account_id: str, trading_day: str) -> None: ...


class MarginEngine(Protocol):
    def margin_required(self, order: OrderRequest) -> Decimal: ...


class PnLEngine(Protocol):
    def mark_to_market(self, account_id: str) -> Decimal: ...


class SettlementEngine(Protocol):
    def settle(self, account_id: str, trading_day: str) -> None: ...
