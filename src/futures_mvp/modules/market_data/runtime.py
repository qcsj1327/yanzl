from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from importlib.util import find_spec

from futures_mvp.modules.market_data.adapters import (
    AkShareClient,
    ReadOnlyMarketDataAdapter,
    ReadOnlyMarketDataAdapterConfig,
)
from futures_mvp.modules.market_data.contracts import (
    BarTimeframe,
    HistoricalBar,
    HistoricalDataStatus,
    HistoricalQuote,
    MarketDataSource,
)
from futures_mvp.modules.market_data.models import (
    InstrumentResolution,
    InstrumentResolveStatus,
)
from futures_mvp.modules.market_data.resolver import InstrumentResolver

SUPPORTED_RUNTIME_SYMBOLS = ("ao", "rb", "ag", "cu")
_RUNTIME_SOURCE = MarketDataSource.READ_ONLY_ADAPTER.value


class MarketDataRuntimeStatus(StrEnum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"
    DEGRADED = "DEGRADED"


class SymbolPollStatus(StrEnum):
    OK = "OK"
    BLOCKED = "BLOCKED"
    DEGRADED = "DEGRADED"


@dataclass(frozen=True)
class MarketDataRuntimeConfig:
    enabled: bool = False
    trading_day: date | None = None
    source: str = _RUNTIME_SOURCE
    symbols: tuple[str, ...] = SUPPORTED_RUNTIME_SYMBOLS
    timeframe: BarTimeframe = BarTimeframe.M1


@dataclass(frozen=True)
class RuntimeQuoteSnapshot:
    symbol: str
    instrument_id: str
    trade_instrument_id: str
    exchange: str
    trading_day: date
    ts: datetime
    last_price: Decimal
    volume: Decimal
    open_interest: Decimal
    source: str


@dataclass(frozen=True)
class RuntimeBarsSummary:
    symbol: str
    instrument_id: str
    trade_instrument_id: str
    timeframe: BarTimeframe
    count: int
    first_ts: datetime | None
    last_ts: datetime | None
    last_close: Decimal | None
    source: str


@dataclass(frozen=True)
class SymbolRuntimeSnapshot:
    symbol: str
    status: SymbolPollStatus
    latest_quote: RuntimeQuoteSnapshot | None = None
    latest_bars_summary: RuntimeBarsSummary | None = None
    updated_at: datetime | None = None
    source: str = _RUNTIME_SOURCE
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True)
class MarketDataRuntimeSnapshot:
    status: MarketDataRuntimeStatus
    started: bool
    configured: bool
    source: str
    updated_at: datetime | None
    akshare_available: bool
    network_call_occurred: bool
    latest_error: str | None
    symbols: tuple[SymbolRuntimeSnapshot, ...]
    diagnostics: tuple[str, ...]


class MarketDataRuntime:
    """本地只读真实行情运行时；默认关闭，不自动联网。"""

    def __init__(
        self,
        config: MarketDataRuntimeConfig | None = None,
        *,
        adapter: ReadOnlyMarketDataAdapter | None = None,
        resolver: InstrumentResolver | None = None,
        client: AkShareClient | None = None,
        now: datetime | None = None,
    ) -> None:
        self._config = config or MarketDataRuntimeConfig()
        adapter_config = ReadOnlyMarketDataAdapterConfig(enabled=self._config.enabled)
        self._adapter = adapter or ReadOnlyMarketDataAdapter(
            adapter_config,
            client=client,
            now=now,
        )
        self._resolver = resolver or InstrumentResolver()
        self._started = False
        self._ever_started = False
        self._network_call_occurred = False
        self._latest_error: str | None = None
        self._last_status = MarketDataRuntimeStatus.NOT_CONFIGURED
        self._updated_at: datetime | None = None
        self._symbols: dict[str, SymbolRuntimeSnapshot] = {}

    @property
    def configured(self) -> bool:
        return self._config.enabled and self._config.trading_day is not None

    @property
    def started(self) -> bool:
        return self._started

    def start(self) -> MarketDataRuntimeSnapshot:
        reason = self._configuration_block_reason()
        if reason is not None:
            self._started = False
            self._latest_error = reason
            self._last_status = MarketDataRuntimeStatus.BLOCKED
            return self.latest_snapshot(MarketDataRuntimeStatus.BLOCKED)
        self._started = True
        self._ever_started = True
        self._latest_error = None
        self._last_status = MarketDataRuntimeStatus.RUNNING
        return self.latest_snapshot(MarketDataRuntimeStatus.RUNNING)

    def stop(self) -> MarketDataRuntimeSnapshot:
        self._started = False
        self._latest_error = "行情运行时已停止，需重新启动后刷新"
        self._last_status = MarketDataRuntimeStatus.STOPPED
        return self.latest_snapshot(MarketDataRuntimeStatus.STOPPED)

    def poll_once(self, symbols: tuple[str, ...] | list[str]) -> MarketDataRuntimeSnapshot:
        reason = self._configuration_block_reason()
        if reason is not None:
            self._started = False
            self._latest_error = "行情运行时未配置或未启用，不能刷新"
            self._last_status = MarketDataRuntimeStatus.BLOCKED
            return self.latest_snapshot(MarketDataRuntimeStatus.BLOCKED)
        if not self._started:
            if self._ever_started:
                self._latest_error = "行情运行时已停止，需重新启动后刷新"
                self._last_status = MarketDataRuntimeStatus.STOPPED
                return self.latest_snapshot(MarketDataRuntimeStatus.STOPPED)
            self._latest_error = "行情运行时未启动，需先启动后刷新"
            self._last_status = MarketDataRuntimeStatus.BLOCKED
            return self.latest_snapshot(MarketDataRuntimeStatus.BLOCKED)
        normalized = _normalize_symbols(symbols)
        if not normalized:
            self._latest_error = "未提供支持的品种"
            self._last_status = MarketDataRuntimeStatus.BLOCKED
            return self.latest_snapshot(MarketDataRuntimeStatus.BLOCKED)
        now = datetime.now()
        any_ok = False
        any_failed = False
        for symbol in normalized:
            result = self._poll_symbol(symbol, now)
            self._symbols[symbol] = result
            any_ok = any_ok or result.status is SymbolPollStatus.OK
            any_failed = any_failed or result.status is not SymbolPollStatus.OK
        self._updated_at = now
        if any_failed:
            self._latest_error = _first_symbol_error(tuple(self._symbols.values()))
        else:
            self._latest_error = None
        if any_ok and any_failed:
            self._last_status = MarketDataRuntimeStatus.DEGRADED
            return self.latest_snapshot(MarketDataRuntimeStatus.DEGRADED)
        if any_ok:
            self._last_status = MarketDataRuntimeStatus.RUNNING
            return self.latest_snapshot(MarketDataRuntimeStatus.RUNNING)
        self._last_status = MarketDataRuntimeStatus.BLOCKED
        return self.latest_snapshot(MarketDataRuntimeStatus.BLOCKED)

    def health(self) -> MarketDataRuntimeSnapshot:
        if not self.configured:
            self._last_status = MarketDataRuntimeStatus.NOT_CONFIGURED
            return self.latest_snapshot(MarketDataRuntimeStatus.NOT_CONFIGURED)
        if self._started:
            self._last_status = MarketDataRuntimeStatus.RUNNING
            return self.latest_snapshot(MarketDataRuntimeStatus.RUNNING)
        self._last_status = MarketDataRuntimeStatus.STOPPED
        return self.latest_snapshot(MarketDataRuntimeStatus.STOPPED)

    def latest_snapshot(
        self,
        status: MarketDataRuntimeStatus | None = None,
    ) -> MarketDataRuntimeSnapshot:
        effective_status = status or self._current_status()
        return MarketDataRuntimeSnapshot(
            status=effective_status,
            started=self._started,
            configured=self.configured,
            source=self._config.source,
            updated_at=self._updated_at,
            akshare_available=_akshare_available(),
            network_call_occurred=self._network_call_occurred,
            latest_error=self._latest_error,
            symbols=tuple(self._symbols[symbol] for symbol in sorted(self._symbols)),
            diagnostics=self._diagnostics(effective_status),
        )

    def diagnostics(self) -> tuple[str, ...]:
        return self.latest_snapshot().diagnostics

    def _poll_symbol(self, symbol: str, now: datetime) -> SymbolRuntimeSnapshot:
        assert self._config.trading_day is not None
        resolution = self._resolver.resolve(symbol, self._config.trading_day)
        if resolution.status is not InstrumentResolveStatus.RESOLVED:
            return _symbol_blocked(
                symbol,
                f"resolver 未解析：{resolution.status.value}",
                resolution,
            )
        if not _resolution_has_identity(resolution):
            return _symbol_blocked(symbol, "resolver 身份字段不完整", resolution)
        identity = _RuntimeIdentity(resolution)
        quote_result = self._adapter.get_latest_quote(identity, as_of=now)
        self._network_call_occurred = True
        bars_result = self._adapter.get_bars(
            identity,
            self._config.timeframe,
            as_of=now,
        )
        self._network_call_occurred = True
        diagnostics = (
            *resolution.diagnostics,
            *quote_result.diagnostics,
            *bars_result.diagnostics,
            "运行时只读缓存：未写数据库，未写文件，未生成命令",
        )
        if quote_result.status is not HistoricalDataStatus.OK or quote_result.quote is None:
            return SymbolRuntimeSnapshot(
                symbol=symbol,
                status=SymbolPollStatus.BLOCKED,
                updated_at=now,
                diagnostics=(*diagnostics, "最近报价读取失败"),
            )
        if bars_result.status is not HistoricalDataStatus.OK or not bars_result.bars:
            return SymbolRuntimeSnapshot(
                symbol=symbol,
                status=SymbolPollStatus.DEGRADED,
                latest_quote=_quote_snapshot(quote_result.quote, resolution),
                updated_at=now,
                diagnostics=(*diagnostics, "最近 K 线读取失败"),
            )
        return SymbolRuntimeSnapshot(
            symbol=symbol,
            status=SymbolPollStatus.OK,
            latest_quote=_quote_snapshot(quote_result.quote, resolution),
            latest_bars_summary=_bars_summary(
                symbol=symbol,
                bars=bars_result.bars,
                resolution=resolution,
                timeframe=self._config.timeframe,
            ),
            updated_at=now,
            diagnostics=diagnostics,
        )

    def _configuration_block_reason(self) -> str | None:
        if not self._config.enabled:
            return "真实行情运行时未配置：enabled=False"
        if self._config.source != _RUNTIME_SOURCE:
            return "真实行情运行时只允许 real_market_data 数据源"
        if self._config.trading_day is None:
            return "真实行情运行时未配置交易日"
        return None

    def _current_status(self) -> MarketDataRuntimeStatus:
        return self._last_status

    def _diagnostics(self, status: MarketDataRuntimeStatus) -> tuple[str, ...]:
        configured = "已配置" if self.configured else "未配置"
        started = "已启动" if self._started else "未启动"
        network = "已发生" if self._network_call_occurred else "未发生"
        latest_error = self._latest_error or "无"
        return (
            f"运行状态={status.value}",
            f"启动状态={started}",
            f"配置状态={configured}",
            f"数据源={self._config.source}",
            f"AkShare 可用={_akshare_available()}",
            f"网络调用={network}",
            f"最近错误={latest_error}",
            "只读运行时：不下单，不连接 Broker、CTP、SimNow，不启用实盘",
        )


class _RuntimeIdentity:
    def __init__(self, resolution: InstrumentResolution) -> None:
        self.symbol = resolution.symbol
        self.instrument_id = resolution.instrument_id or ""
        self.trade_instrument_id = resolution.trade_instrument_id or ""
        self.exchange = resolution.exchange or ""
        self.trading_day = resolution.trading_day or date.min


def _normalize_symbols(symbols: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    normalized = []
    for symbol in symbols:
        value = symbol.strip().lower()
        if value in SUPPORTED_RUNTIME_SYMBOLS and value not in normalized:
            normalized.append(value)
    return tuple(normalized)


def _resolution_has_identity(resolution: InstrumentResolution) -> bool:
    return all(
        (
            resolution.instrument_id,
            resolution.trade_instrument_id,
            resolution.exchange,
            resolution.trading_day,
        )
    )


def _symbol_blocked(
    symbol: str,
    reason: str,
    resolution: InstrumentResolution,
) -> SymbolRuntimeSnapshot:
    return SymbolRuntimeSnapshot(
        symbol=symbol,
        status=SymbolPollStatus.BLOCKED,
        diagnostics=(
            reason,
            *resolution.diagnostics,
            "不会自动猜测合约，不会自动补数据",
        ),
    )


def _quote_snapshot(
    quote: HistoricalQuote,
    resolution: InstrumentResolution,
) -> RuntimeQuoteSnapshot:
    assert resolution.instrument_id is not None
    assert resolution.trade_instrument_id is not None
    assert resolution.exchange is not None
    assert resolution.trading_day is not None
    return RuntimeQuoteSnapshot(
        symbol=resolution.symbol,
        instrument_id=resolution.instrument_id,
        trade_instrument_id=resolution.trade_instrument_id,
        exchange=resolution.exchange,
        trading_day=resolution.trading_day,
        ts=quote.ts,
        last_price=quote.last_price,
        volume=quote.volume,
        open_interest=quote.open_interest,
        source=_RUNTIME_SOURCE,
    )


def _bars_summary(
    *,
    symbol: str,
    bars: tuple[HistoricalBar, ...],
    resolution: InstrumentResolution,
    timeframe: BarTimeframe,
) -> RuntimeBarsSummary:
    assert resolution.instrument_id is not None
    assert resolution.trade_instrument_id is not None
    ordered = tuple(sorted(bars, key=lambda bar: bar.bar_ts))
    return RuntimeBarsSummary(
        symbol=symbol,
        instrument_id=resolution.instrument_id,
        trade_instrument_id=resolution.trade_instrument_id,
        timeframe=timeframe,
        count=len(ordered),
        first_ts=ordered[0].bar_ts if ordered else None,
        last_ts=ordered[-1].bar_ts if ordered else None,
        last_close=ordered[-1].close if ordered else None,
        source=_RUNTIME_SOURCE,
    )


def _first_symbol_error(symbols: tuple[SymbolRuntimeSnapshot, ...]) -> str | None:
    for item in symbols:
        if item.status is not SymbolPollStatus.OK and item.diagnostics:
            return f"{item.symbol}: {item.diagnostics[-1]}"
    return None


def _akshare_available() -> bool:
    return find_spec("akshare") is not None
