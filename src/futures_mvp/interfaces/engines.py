from decimal import Decimal
from typing import Protocol

from futures_mvp.domain.models import (
    OrderEvent,
    OrderRequest,
    OrderState,
    RiskResult,
    Signal,
    Trade,
)


class MarketDataMock(Protocol):
    def latest_price(self, instrument_id: str) -> Decimal: ...


class StrategyEngine(Protocol):
    def on_market_data(self, market_data: object) -> list[Signal]: ...


class FuturesRiskEngine(Protocol):
    def check_order(self, signal: Signal) -> RiskResult: ...


class OMS(Protocol):
    def create_order(self, request: OrderRequest, risk_result: RiskResult) -> OrderState: ...

    def apply_event(self, event: OrderEvent) -> OrderState: ...

    def get_by_client_order_id(self, client_order_id: str) -> OrderState | None: ...


class EMS(Protocol):
    def submit(self, order: OrderState) -> None: ...

    def cancel(self, order: OrderState) -> None: ...


class MockFuturesExchange(Protocol):
    def submit_limit_order(self, order: OrderState) -> None: ...

    def cancel_order(self, order: OrderState) -> None: ...

    def run_daily_settlement(self, trading_day: str) -> None: ...


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
