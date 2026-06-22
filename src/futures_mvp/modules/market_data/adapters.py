from __future__ import annotations

from datetime import date, datetime

from futures_mvp.modules.market_data.contracts import (
    BarTimeframe,
    HistoricalBarsResult,
    HistoricalDataStatus,
    HistoricalQuoteResult,
    MarketDataSource,
)
from futures_mvp.modules.market_data.models import InstrumentContract

READ_ONLY_ADAPTER_NOT_CONFIGURED = "read-only market data adapter not configured"
READ_ONLY_ADAPTER_BOUNDARY = (
    "Phase L read-only adapter placeholder: no network, broker, CTP, SimNow, "
    "live trading, live account, order, or execution capability"
)


class ReadOnlyMarketDataAdapter:
    """Disabled-by-default boundary for future read-only market data providers."""

    source = MarketDataSource.READ_ONLY_ADAPTER.value

    def list_symbols(self) -> tuple[str, ...]:
        return ()

    def list_contracts(
        self,
        symbol: str,
        trading_day: str | date,
    ) -> tuple[InstrumentContract, ...]:
        return ()

    def get_main_contract(
        self,
        symbol: str,
        trading_day: str | date,
    ) -> InstrumentContract | None:
        return None

    def get_trade_contract(
        self,
        symbol: str,
        trading_day: str | date,
    ) -> InstrumentContract | None:
        return None

    def get_bars(
        self,
        identity: object,
        timeframe: str | BarTimeframe,
        start: datetime | date | None = None,
        end: datetime | date | None = None,
        as_of: datetime | None = None,
    ) -> HistoricalBarsResult:
        return HistoricalBarsResult(
            status=HistoricalDataStatus.BLOCKED,
            diagnostics=_blocked_diagnostics(),
        )

    def get_latest_quote(
        self,
        identity: object,
        as_of: datetime | None = None,
    ) -> HistoricalQuoteResult:
        return HistoricalQuoteResult(
            status=HistoricalDataStatus.BLOCKED,
            diagnostics=_blocked_diagnostics(),
        )


def _blocked_diagnostics() -> tuple[str, ...]:
    return (
        f"source={MarketDataSource.READ_ONLY_ADAPTER.value}",
        READ_ONLY_ADAPTER_NOT_CONFIGURED,
        READ_ONLY_ADAPTER_BOUNDARY,
    )
