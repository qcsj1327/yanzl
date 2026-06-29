from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date, timedelta
from enum import StrEnum
from typing import Protocol

from futures_mvp.modules.market_data.akshare_mapping import get_akshare_mapping
from futures_mvp.modules.market_data.consumer import build_resolver_consumer_context
from futures_mvp.modules.market_data.contracts import (
    BarTimeframe,
    HistoricalBar,
    HistoricalDataStatus,
    MarketDataAdapter,
    MarketDataSource,
)
from futures_mvp.modules.market_data.models import InstrumentResolveStatus
from futures_mvp.modules.market_data.resolver import InstrumentResolver


class HistoricalIngestionStatus(StrEnum):
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"


class HistoricalBarWriter(Protocol):
    def upsert_bars(
        self,
        bars: Iterable[HistoricalBar],
        *,
        source: str,
        resolver_source: str,
        resolver_confidence: str,
    ) -> int: ...

    def get_coverage(
        self,
        identity: object,
        timeframe: str | BarTimeframe,
        trading_day: date | None = None,
        *,
        source: str,
    ) -> dict[str, object]: ...


@dataclass(frozen=True)
class HistoricalDataIngestionResult:
    status: HistoricalIngestionStatus
    diagnostics: tuple[str, ...]
    bars_written: int = 0
    bars_updated: int = 0
    bars_skipped: int = 0
    bar_count: int = 0
    first_bar_ts: object | None = None
    latest_bar_ts: object | None = None
    latest_ingested_at: object | None = None
    source: str = MarketDataSource.READ_ONLY_ADAPTER.value
    reason: str | None = None


class HistoricalDataIngestionService:
    def __init__(
        self,
        *,
        resolver: InstrumentResolver,
        adapter: MarketDataAdapter,
        repository: HistoricalBarWriter,
    ) -> None:
        self._resolver = resolver
        self._adapter = adapter
        self._repository = repository

    def ingest_symbol(
        self,
        symbol: str,
        trading_day: date,
        timeframe: str | BarTimeframe,
        end_trading_day: date | None = None,
    ) -> HistoricalDataIngestionResult:
        normalized_timeframe = _normalize_timeframe(timeframe)
        if normalized_timeframe is None:
            return _blocked("周期不受支持")
        mapping = get_akshare_mapping(symbol)
        if mapping is None:
            return _blocked("品种未配置 AkShare 映射")
        if not mapping.enabled:
            return _blocked("AkShare 映射已禁用")
        if end_trading_day is not None and end_trading_day < trading_day:
            return _blocked("结束日期早于开始日期")
        days = _trading_days(trading_day, end_trading_day or trading_day)
        total_written = 0
        total_input_bars = 0
        latest_coverage: dict[str, object] = {}
        diagnostics: list[str] = [
            "历史行情同步完成",
            "链路=真实数据源 -> 标准化 -> 本地库",
            f"品种={mapping.symbol}",
            f"AkShare 符号={mapping.akshare_symbol}",
            f"周期={normalized_timeframe.value}",
            f"数据源={MarketDataSource.READ_ONLY_ADAPTER.value}",
        ]
        for day in days:
            day_result = self._ingest_day(symbol, day, normalized_timeframe)
            if day_result.status is HistoricalIngestionStatus.BLOCKED:
                return day_result
            total_written += day_result.bars_written
            total_input_bars += day_result.bars_written + day_result.bars_skipped
            latest_coverage = {
                "bar_count": day_result.bar_count,
                "first_bar_ts": day_result.first_bar_ts,
                "latest_bar_ts": day_result.latest_bar_ts,
                "latest_ingested_at": day_result.latest_ingested_at,
            }
            diagnostics.extend(day_result.diagnostics)
        skipped = max(total_input_bars - total_written, 0)
        return HistoricalDataIngestionResult(
            status=HistoricalIngestionStatus.COMPLETED,
            bars_written=total_written,
            bars_updated=0,
            bars_skipped=skipped,
            bar_count=_int_value(latest_coverage.get("bar_count")),
            first_bar_ts=latest_coverage.get("first_bar_ts"),
            latest_bar_ts=latest_coverage.get("latest_bar_ts"),
            latest_ingested_at=latest_coverage.get("latest_ingested_at"),
            diagnostics=(
                *tuple(dict.fromkeys(diagnostics)),
                f"写入条数={total_written}",
                "更新条数=0",
                f"跳过条数={skipped}",
                "未下单，未连接 Broker，未启用 ExecutionTarget",
            ),
        )

    def _ingest_day(
        self,
        symbol: str,
        trading_day: date,
        timeframe: BarTimeframe,
    ) -> HistoricalDataIngestionResult:
        resolution = self._resolver.resolve(symbol, trading_day)
        if resolution.status is not InstrumentResolveStatus.RESOLVED:
            return _blocked(
                "解析器失败，历史行情同步已阻断",
                f"resolver_status={resolution.status.value}",
                *resolution.diagnostics,
            )
        context_result = build_resolver_consumer_context(resolution)
        if context_result.blocked or context_result.context is None:
            return _blocked(
                "解析器身份上下文不可用，历史行情同步已阻断",
                context_result.reason or "resolver context blocked",
            )
        bars_result = self._adapter.get_bars(
            context_result.context,
            timeframe,
            start=trading_day,
            end=trading_day,
        )
        if bars_result.status is not HistoricalDataStatus.OK:
            return _blocked(
                "AkShare 只读数据源不可用，历史行情同步已阻断",
                *bars_result.diagnostics,
            )
        if not bars_result.bars:
            return _blocked("AkShare 返回空数据，历史行情同步已阻断")
        standardized = tuple(
            _standardize_bar(bar, context_result.context, timeframe)
            for bar in bars_result.bars
        )
        if not standardized or any(bar is None for bar in standardized):
            return _blocked("标准化失败，历史行情同步已阻断")
        normalized_bars = tuple(bar for bar in standardized if bar is not None)
        try:
            written = self._repository.upsert_bars(
                normalized_bars,
                source=MarketDataSource.READ_ONLY_ADAPTER.value,
                resolver_source=context_result.context.lineage.resolver_source,
                resolver_confidence=context_result.context.lineage.resolver_confidence,
            )
            coverage = self._repository.get_coverage(
                context_result.context,
                timeframe,
                trading_day,
                source=MarketDataSource.READ_ONLY_ADAPTER.value,
            )
        except Exception as exc:
            return _blocked(f"数据库不可用或写入失败：{type(exc).__name__}")
        bar_count = _int_value(coverage.get("bar_count"))
        skipped = max(len(normalized_bars) - written, 0)
        return HistoricalDataIngestionResult(
            status=HistoricalIngestionStatus.COMPLETED,
            bars_written=written,
            bars_updated=0,
            bars_skipped=skipped,
            bar_count=bar_count,
            first_bar_ts=coverage.get("first_bar_ts"),
            latest_bar_ts=coverage.get("latest_bar_ts"),
            latest_ingested_at=coverage.get("latest_ingested_at"),
            diagnostics=(
                f"品种={context_result.context.identity.symbol}",
                f"交易日={context_result.context.identity.trading_day}",
                f"本次新增={written}",
                "本次更新=0",
                f"本次跳过={skipped}",
                f"本地库条数={bar_count}",
            ),
        )


def _normalize_timeframe(value: str | BarTimeframe) -> BarTimeframe | None:
    if isinstance(value, BarTimeframe):
        return value
    try:
        return BarTimeframe(value.strip().lower())
    except ValueError:
        return None


def _standardize_bar(
    bar: HistoricalBar,
    context: object,
    timeframe: BarTimeframe,
) -> HistoricalBar | None:
    identity = getattr(context, "identity", None)
    if identity is None:
        return None
    return replace(
        bar,
        symbol=identity.symbol,
        instrument_id=identity.instrument_id,
        trade_instrument_id=identity.trade_instrument_id,
        exchange=identity.exchange,
        trading_day=identity.trading_day,
        timeframe=timeframe,
    )


def _blocked(*diagnostics: str) -> HistoricalDataIngestionResult:
    reason = diagnostics[0] if diagnostics else "历史行情同步已阻断"
    return HistoricalDataIngestionResult(
        status=HistoricalIngestionStatus.BLOCKED,
        reason=reason,
        diagnostics=(
            *diagnostics,
            "不会下单，不连接 Broker、CTP、SimNow，不启用实盘或执行目标",
        ),
    )


def _trading_days(start: date, end: date) -> tuple[date, ...]:
    days: list[date] = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return tuple(days)


def _int_value(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0
