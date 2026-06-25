from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from importlib import import_module
from typing import Protocol, cast

from futures_mvp.modules.market_data.contracts import (
    BarTimeframe,
    BidAskLevel,
    HistoricalBar,
    HistoricalBarsResult,
    HistoricalDataStatus,
    HistoricalQuote,
    HistoricalQuoteResult,
    MarketDataSource,
)
from futures_mvp.modules.market_data.models import (
    ContractRole,
    InstrumentContract,
    InstrumentMetadata,
)
from futures_mvp.modules.market_data.registry import METADATA_BY_SYMBOL

READ_ONLY_ADAPTER_NOT_CONFIGURED = "只读行情适配器未配置"
READ_ONLY_ADAPTER_BOUNDARY = (
    "只读行情边界：不会下单，不连接 Broker、CTP、SimNow，不启用实盘或执行目标"
)

_AKSHARE_PROVIDER = "AkShare"
_TIMEFRAME_TO_AKSHARE_PERIOD = {
    BarTimeframe.M1: "1",
    BarTimeframe.M5: "5",
    BarTimeframe.M15: "15",
    BarTimeframe.H1: "60",
}


class AkShareClient(Protocol):
    def futures_display_main_sina(self) -> object: ...

    def match_main_contract(self, symbol: str) -> str: ...

    def futures_zh_spot(
        self,
        symbol: str,
        market: str = "CF",
        adjust: str = "0",
    ) -> object: ...

    def futures_zh_minute_sina(self, symbol: str, period: str) -> object: ...

    def futures_zh_daily_sina(self, symbol: str) -> object: ...


@dataclass(frozen=True)
class ReadOnlyMarketDataAdapterConfig:
    enabled: bool = False
    provider: str = _AKSHARE_PROVIDER
    exchanges: tuple[str, ...] = ("shfe", "dce", "czce", "gfex")
    market: str = "CF"
    timeout_seconds: int = 10


class ReadOnlyMarketDataAdapter:
    """显式配置后才会读取真实行情的只读适配器。"""

    source = MarketDataSource.READ_ONLY_ADAPTER.value

    def __init__(
        self,
        config: ReadOnlyMarketDataAdapterConfig | None = None,
        *,
        client: AkShareClient | None = None,
        now: datetime | None = None,
    ) -> None:
        self._config = config or ReadOnlyMarketDataAdapterConfig()
        self._client = client
        self._now = now

    @property
    def configured(self) -> bool:
        return self._config.enabled

    def list_symbols(self) -> tuple[str, ...]:
        client_result = self._configured_client()
        if client_result.blocked:
            return ()
        assert client_result.client is not None
        client = client_result.client
        try:
            rows = _records(client.futures_display_main_sina())
            symbols = tuple(
                sorted(
                    {
                        symbol
                        for row in rows
                        if (symbol := _base_symbol_from_row(row)) is not None
                    }
                )
            )
            return symbols
        except Exception:
            return ()

    def list_contracts(
        self,
        symbol: str,
        trading_day: str | date,
    ) -> tuple[InstrumentContract, ...]:
        parsed_day = _normalize_day(trading_day)
        normalized_symbol = _normalize_symbol(symbol)
        if parsed_day is None or normalized_symbol is None:
            return ()
        main = self.get_main_contract(normalized_symbol, parsed_day)
        trade = self.get_trade_contract(normalized_symbol, parsed_day)
        return tuple(contract for contract in (main, trade) if contract is not None)

    def get_main_contract(
        self,
        symbol: str,
        trading_day: str | date,
    ) -> InstrumentContract | None:
        parsed_day = _normalize_day(trading_day)
        normalized_symbol = _normalize_symbol(symbol)
        if parsed_day is None or normalized_symbol is None:
            return None
        client_result = self._configured_client()
        if client_result.blocked:
            return None
        assert client_result.client is not None
        client = client_result.client
        try:
            rows = _records(client.futures_display_main_sina())
        except Exception:
            return None
        for row in rows:
            if _base_symbol_from_row(row) != normalized_symbol:
                continue
            exchange = _row_text(row, "exchange", default="").upper()
            if not exchange:
                return None
            return _contract(
                symbol=normalized_symbol,
                instrument_id=f"{normalized_symbol}9999",
                exchange=exchange,
                role=ContractRole.CONTINUOUS_MAIN,
                trading_day=parsed_day,
            )
        return None

    def get_trade_contract(
        self,
        symbol: str,
        trading_day: str | date,
    ) -> InstrumentContract | None:
        parsed_day = _normalize_day(trading_day)
        normalized_symbol = _normalize_symbol(symbol)
        if parsed_day is None or normalized_symbol is None:
            return None
        main_contract = self.get_main_contract(normalized_symbol, parsed_day)
        if main_contract is None:
            return None
        quote_result = self.get_latest_quote(_SimpleIdentity(normalized_symbol, parsed_day))
        if quote_result.status is not HistoricalDataStatus.OK or quote_result.quote is None:
            return None
        return _contract(
            symbol=normalized_symbol,
            instrument_id=quote_result.quote.trade_instrument_id,
            exchange=main_contract.exchange,
            role=ContractRole.TRADE_CONTRACT,
            trading_day=parsed_day,
        )

    def get_bars(
        self,
        identity: object,
        timeframe: str | BarTimeframe,
        start: datetime | date | None = None,
        end: datetime | date | None = None,
        as_of: datetime | None = None,
    ) -> HistoricalBarsResult:
        client_result = self._configured_client()
        if client_result.blocked:
            return _blocked_bars(client_result.reason)
        assert client_result.client is not None
        client = client_result.client
        identity_fields = _identity_fields(identity)
        normalized_timeframe = _normalize_timeframe(timeframe)
        if identity_fields is None or normalized_timeframe is None:
            return _blocked_bars("输入无效，必须提供解析器身份和支持的周期")
        symbol, instrument_id, trade_instrument_id, exchange, trading_day = identity_fields
        ak_symbol = _akshare_symbol(instrument_id)
        try:
            if normalized_timeframe is BarTimeframe.D1:
                rows = _records(client.futures_zh_daily_sina(symbol=ak_symbol))
            else:
                rows = _records(
                    client.futures_zh_minute_sina(
                        symbol=ak_symbol,
                        period=_TIMEFRAME_TO_AKSHARE_PERIOD[normalized_timeframe],
                    )
                )
        except Exception as exc:
            return _blocked_bars(f"行情接口异常：{type(exc).__name__}")
        bars = _bars_from_rows(
            rows=rows,
            symbol=symbol,
            instrument_id=instrument_id,
            trade_instrument_id=trade_instrument_id,
            exchange=exchange,
            trading_day=trading_day,
            timeframe=normalized_timeframe,
            start=start,
            end=end,
            as_of=as_of,
        )
        if not bars:
            return _blocked_bars("行情接口返回空 K 线")
        return HistoricalBarsResult(
            status=HistoricalDataStatus.OK,
            bars=bars,
            diagnostics=(
                f"数据源={MarketDataSource.READ_ONLY_ADAPTER.value}",
                f"提供方={_AKSHARE_PROVIDER}",
                "已读取标准化 K 线",
                "未写数据库，未下单",
            ),
        )

    def get_latest_quote(
        self,
        identity: object,
        as_of: datetime | None = None,
    ) -> HistoricalQuoteResult:
        client_result = self._configured_client()
        if client_result.blocked:
            return _blocked_quote(client_result.reason)
        assert client_result.client is not None
        client = client_result.client
        identity_fields = _identity_fields(identity)
        if identity_fields is None:
            return _blocked_quote("输入无效，必须提供解析器身份")
        symbol, instrument_id, trade_instrument_id, exchange, trading_day = identity_fields
        ak_symbol = _akshare_symbol(instrument_id)
        try:
            rows = _records(
                client.futures_zh_spot(
                    symbol=ak_symbol,
                    market=self._config.market,
                    adjust="0",
                )
            )
        except Exception as exc:
            return _blocked_quote(f"行情接口异常：{type(exc).__name__}")
        if not rows:
            return _blocked_quote("行情接口返回空报价")
        quote = _quote_from_row(
            rows[0],
            symbol=symbol,
            instrument_id=instrument_id,
            fallback_trade_instrument_id=trade_instrument_id,
            exchange=exchange,
            trading_day=trading_day,
            as_of=as_of or self._now,
        )
        if quote is None:
            return _blocked_quote("行情报价字段缺失或格式无效")
        return HistoricalQuoteResult(
            status=HistoricalDataStatus.OK,
            quote=quote,
            diagnostics=(
                f"数据源={MarketDataSource.READ_ONLY_ADAPTER.value}",
                f"提供方={_AKSHARE_PROVIDER}",
                "已读取标准化最近行情",
                "未写数据库，未下单",
            ),
        )

    def _configured_client(self) -> _ClientResult:
        if not self._config.enabled:
            return _ClientResult(blocked=True, reason=READ_ONLY_ADAPTER_NOT_CONFIGURED)
        if self._config.provider != _AKSHARE_PROVIDER:
            return _ClientResult(blocked=True, reason="只允许配置 AkShare 数据源")
        if self._config.timeout_seconds <= 0:
            return _ClientResult(blocked=True, reason="超时配置无效")
        if self._client is not None:
            return _ClientResult(blocked=False, client=self._client)
        try:
            client = cast(AkShareClient, import_module("akshare"))
        except Exception as exc:
            return _ClientResult(
                blocked=True,
                reason=f"AkShare 未安装或不可用：{type(exc).__name__}",
            )
        return _ClientResult(blocked=False, client=client)


@dataclass(frozen=True)
class _ClientResult:
    blocked: bool
    reason: str = ""
    client: AkShareClient | None = None


@dataclass(frozen=True)
class _SimpleIdentity:
    symbol: str
    trading_day: date


def _blocked_diagnostics(reason: str) -> tuple[str, ...]:
    return (
        f"数据源={MarketDataSource.READ_ONLY_ADAPTER.value}",
        reason,
        READ_ONLY_ADAPTER_BOUNDARY,
        "不会访问网络，除非显式配置并调用只读适配器",
    )


def _blocked_bars(reason: str) -> HistoricalBarsResult:
    return HistoricalBarsResult(
        status=HistoricalDataStatus.BLOCKED,
        diagnostics=_blocked_diagnostics(reason),
    )


def _blocked_quote(reason: str) -> HistoricalQuoteResult:
    return HistoricalQuoteResult(
        status=HistoricalDataStatus.BLOCKED,
        diagnostics=_blocked_diagnostics(reason),
    )


def _records(data: object) -> tuple[Mapping[str, object], ...]:
    if data is None:
        return ()
    if hasattr(data, "empty") and bool(data.empty):
        return ()
    if hasattr(data, "to_dict"):
        converted = data.to_dict("records")
        return tuple(cast(tuple[Mapping[str, object], ...], tuple(converted)))
    if isinstance(data, Mapping):
        return (data,)
    if isinstance(data, list | tuple):
        return tuple(item for item in data if isinstance(item, Mapping))
    return ()


def _base_symbol_from_row(row: Mapping[str, object]) -> str | None:
    raw = _row_text(row, "symbol", "品种", default="")
    if not raw:
        return None
    letters = "".join(char for char in raw.lower() if "a" <= char <= "z")
    return letters or None


def _row_text(
    row: Mapping[str, object],
    *keys: str,
    default: str,
) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None:
            text = str(value).strip()
            if text and text.lower() != "nan":
                return text
    return default


def _normalize_symbol(symbol: str) -> str | None:
    normalized = symbol.strip().lower()
    if not normalized or not normalized.isalnum():
        return None
    return normalized


def _normalize_day(value: str | date) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _normalize_timeframe(value: str | BarTimeframe) -> BarTimeframe | None:
    if isinstance(value, BarTimeframe):
        return value
    try:
        return BarTimeframe(value.strip().lower())
    except ValueError:
        return None


def _contract(
    *,
    symbol: str,
    instrument_id: str,
    exchange: str,
    role: ContractRole,
    trading_day: date,
) -> InstrumentContract:
    return InstrumentContract(
        symbol=symbol,
        instrument_id=instrument_id,
        exchange=exchange,
        role=role,
        effective_from=trading_day,
        effective_to=trading_day,
        source=MarketDataSource.READ_ONLY_ADAPTER.value,
        metadata=_metadata(symbol),
    )


def _metadata(symbol: str) -> InstrumentMetadata:
    return METADATA_BY_SYMBOL.get(
        symbol,
        InstrumentMetadata(
            product_name=symbol,
            tick_size=Decimal("1"),
            contract_multiplier=Decimal("1"),
            min_order_qty=Decimal("1"),
            price_limit_ref="只读行情适配器未提供涨跌停规则",
            trading_session_ref="只读行情适配器未提供交易时段",
        ),
    )


def _identity_fields(identity: object) -> tuple[str, str, str, str, date] | None:
    value = getattr(identity, "identity", identity)
    symbol = getattr(value, "symbol", None)
    instrument_id = getattr(value, "instrument_id", None)
    trade_instrument_id = getattr(value, "trade_instrument_id", None)
    exchange = getattr(value, "exchange", None)
    trading_day = getattr(value, "trading_day", None)
    if (
        isinstance(symbol, str)
        and isinstance(instrument_id, str)
        and isinstance(trade_instrument_id, str)
        and isinstance(exchange, str)
        and isinstance(trading_day, date)
    ):
        return symbol, instrument_id, trade_instrument_id, exchange, trading_day
    if isinstance(symbol, str) and isinstance(trading_day, date):
        main = f"{symbol}9999"
        return symbol, main, main, "", trading_day
    return None


def _akshare_symbol(instrument_id: str) -> str:
    if instrument_id.endswith("9999"):
        return f"{instrument_id[:-4].upper()}0"
    return instrument_id.upper()


def _decimal(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _bar_ts(row: Mapping[str, object], trading_day: date) -> datetime | None:
    raw = row.get("datetime", row.get("date", row.get("时间")))
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, date):
        return datetime.combine(raw, time())
    text = str(raw).strip()
    try:
        if len(text) == 10:
            return datetime.combine(date.fromisoformat(text), time())
        return datetime.fromisoformat(text)
    except ValueError:
        return datetime.combine(trading_day, time())


def _bars_from_rows(
    *,
    rows: tuple[Mapping[str, object], ...],
    symbol: str,
    instrument_id: str,
    trade_instrument_id: str,
    exchange: str,
    trading_day: date,
    timeframe: BarTimeframe,
    start: datetime | date | None,
    end: datetime | date | None,
    as_of: datetime | None,
) -> tuple[HistoricalBar, ...]:
    bars: list[HistoricalBar] = []
    start_dt = _date_bound(start, is_end=False)
    end_dt = _date_bound(end, is_end=True)
    for row in rows:
        bar_ts = _bar_ts(row, trading_day)
        open_price = _decimal(row.get("open", row.get("开盘")))
        high = _decimal(row.get("high", row.get("最高")))
        low = _decimal(row.get("low", row.get("最低")))
        close = _decimal(row.get("close", row.get("收盘")))
        volume = _decimal(row.get("volume", row.get("成交量")))
        open_interest = _decimal(row.get("hold", row.get("持仓量", 0))) or Decimal("0")
        if None in (bar_ts, open_price, high, low, close, volume):
            return ()
        assert bar_ts is not None
        assert open_price is not None
        assert high is not None
        assert low is not None
        assert close is not None
        assert volume is not None
        if start_dt is not None and bar_ts < start_dt:
            continue
        if end_dt is not None and bar_ts > end_dt:
            continue
        if as_of is not None and bar_ts > as_of:
            continue
        bars.append(
            HistoricalBar(
                symbol=symbol,
                instrument_id=instrument_id,
                trade_instrument_id=trade_instrument_id,
                exchange=exchange,
                trading_day=bar_ts.date(),
                session_id="read_only_akshare",
                timeframe=timeframe,
                bar_ts=bar_ts,
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=volume,
                turnover=_decimal(row.get("turnover", row.get("成交额", 0))) or Decimal("0"),
                open_interest=open_interest,
            )
        )
    return tuple(bars)


def _date_bound(value: datetime | date | None, *, is_end: bool) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.combine(value, time.max if is_end else time())


def _quote_from_row(
    row: Mapping[str, object],
    *,
    symbol: str,
    instrument_id: str,
    fallback_trade_instrument_id: str,
    exchange: str,
    trading_day: date,
    as_of: datetime | None,
) -> HistoricalQuote | None:
    last_price = _decimal(row.get("current_price", row.get("trade", row.get("price"))))
    volume = _decimal(row.get("volume", 0))
    open_interest = _decimal(row.get("hold", row.get("open_interest", 0))) or Decimal("0")
    if last_price is None or volume is None:
        return None
    trade_instrument_id = _row_text(row, "symbol", default=fallback_trade_instrument_id)
    bid_price = _decimal(row.get("bid_price", row.get("bid", last_price))) or last_price
    ask_price = _decimal(row.get("ask_price", row.get("ask", last_price))) or last_price
    bid_volume = _decimal(row.get("buy_vol", 0)) or Decimal("0")
    ask_volume = _decimal(row.get("sell_vol", 0)) or Decimal("0")
    return HistoricalQuote(
        symbol=symbol,
        instrument_id=instrument_id,
        trade_instrument_id=trade_instrument_id.lower(),
        exchange=exchange,
        trading_day=trading_day,
        session_id="read_only_akshare",
        ts=as_of or datetime.combine(trading_day, time()),
        last_price=last_price,
        volume=volume,
        turnover=_decimal(row.get("turnover", 0)) or Decimal("0"),
        open_interest=open_interest,
        bid_ask_ladder=(
            BidAskLevel(
                level=1,
                bid_price=bid_price,
                bid_volume=bid_volume,
                ask_price=ask_price,
                ask_volume=ask_volume,
            ),
        ),
        source=MarketDataSource.READ_ONLY_ADAPTER.value,
    )
