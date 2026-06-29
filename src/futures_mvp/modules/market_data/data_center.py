from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from time import perf_counter
from typing import Protocol

from futures_mvp.modules.market_data.akshare_mapping import AKSHARE_SYMBOL_MAPPINGS
from futures_mvp.modules.market_data.contracts import BarTimeframe, MarketDataSource
from futures_mvp.modules.market_data.ingestion import (
    HistoricalDataIngestionResult,
    HistoricalIngestionStatus,
)
from futures_mvp.modules.market_data.resolver import InstrumentResolver
from futures_mvp.modules.market_data.runtime import MarketDataRuntime

DATA_CENTER_SYMBOLS: tuple[str, ...] = ("ao", "rb", "ag", "cu")


class DataCenterRepository(Protocol):
    def list_coverage(
        self,
        *,
        symbols: tuple[str, ...],
        timeframe: str | BarTimeframe,
        source: str,
    ) -> tuple[dict[str, object], ...]: ...

    def get_quality_summary(
        self,
        *,
        symbol: str,
        timeframe: str | BarTimeframe,
        source: str,
    ) -> dict[str, object]: ...


class DataCenterIngestionService(Protocol):
    def ingest_symbol(
        self,
        symbol: str,
        trading_day: date,
        timeframe: str,
        *,
        end_trading_day: date | None = None,
    ) -> HistoricalDataIngestionResult: ...


@dataclass(frozen=True)
class DataSourceStatus:
    name: str
    status: str
    enabled: bool
    latest_connection: str
    latest_error: str
    version: str


@dataclass(frozen=True)
class InstrumentDataCenterRow:
    symbol: str
    main_contract: str
    trade_contract: str
    exchange: str
    resolver: str
    data_source: str
    mapping: str
    status: str


@dataclass(frozen=True)
class HistoricalCoverageRow:
    symbol: str
    coverage_start: str
    coverage_end: str
    bar_count: int
    latest_sync: str
    source: str


@dataclass(frozen=True)
class DataQualityRow:
    symbol: str
    missing_bars: int
    duplicate_bars: int
    abnormal_bars: int
    gap_count: int
    continuity: str
    coverage_ratio: str
    sync_status: str


@dataclass(frozen=True)
class DataCenterDiagnostics:
    resolver: str
    repository: str
    historical_bar: str
    akshare: str
    sync_service: str
    database: str


@dataclass(frozen=True)
class DataCenterSnapshot:
    data_sources: tuple[DataSourceStatus, ...]
    instruments: tuple[InstrumentDataCenterRow, ...]
    coverage: tuple[HistoricalCoverageRow, ...]
    quality: tuple[DataQualityRow, ...]
    diagnostics: DataCenterDiagnostics
    coverage_chart: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class DataCenterSyncResult:
    status: str
    added: int
    updated: int
    skipped: int
    failed: int
    elapsed_ms: int
    diagnostics: tuple[str, ...]


class DataCenterService:
    def __init__(
        self,
        *,
        repository: DataCenterRepository | None = None,
        ingestion_service: DataCenterIngestionService | None = None,
        runtime: MarketDataRuntime | None = None,
        resolver: InstrumentResolver | None = None,
        symbols: tuple[str, ...] = DATA_CENTER_SYMBOLS,
    ) -> None:
        self._repository = repository
        self._ingestion_service = ingestion_service
        self._runtime = runtime
        self._resolver = resolver or InstrumentResolver()
        self._symbols = symbols

    def snapshot(
        self,
        *,
        timeframe: str | BarTimeframe = BarTimeframe.M1,
        source: str = MarketDataSource.READ_ONLY_ADAPTER.value,
    ) -> DataCenterSnapshot:
        coverage_rows = self._coverage_rows(timeframe=timeframe, source=source)
        quality_rows = self._quality_rows(timeframe=timeframe, source=source)
        return DataCenterSnapshot(
            data_sources=(self._akshare_status(),),
            instruments=self._instrument_rows(source=source),
            coverage=coverage_rows,
            quality=quality_rows,
            diagnostics=self._diagnostics(),
            coverage_chart=tuple(
                (
                    row.symbol.upper(),
                    (
                        f"{row.coverage_start} -> {row.coverage_end}；"
                        f"Bar={row.bar_count}；覆盖率="
                        f"{_quality_ratio(row.symbol, quality_rows)}"
                    ),
                )
                for row in coverage_rows
            ),
        )

    def sync_history(
        self,
        *,
        symbol: str,
        start: date,
        end: date,
        timeframe: str = BarTimeframe.M1.value,
    ) -> DataCenterSyncResult:
        if self._ingestion_service is None:
            return DataCenterSyncResult(
                status="已阻断",
                added=0,
                updated=0,
                skipped=0,
                failed=1,
                elapsed_ms=0,
                diagnostics=(
                    "历史行情同步服务未配置",
                    "不会自动联网",
                    "未进入 Broker",
                    "未进入交易链路",
                ),
            )
        started = perf_counter()
        result = self._ingestion_service.ingest_symbol(
            symbol,
            start,
            timeframe,
            end_trading_day=end,
        )
        elapsed_ms = int((perf_counter() - started) * 1000)
        failed = 1 if result.status is HistoricalIngestionStatus.BLOCKED else 0
        return DataCenterSyncResult(
            status="完成" if failed == 0 else "已阻断",
            added=result.bars_written,
            updated=result.bars_updated,
            skipped=result.bars_skipped,
            failed=failed,
            elapsed_ms=elapsed_ms,
            diagnostics=(
                *result.diagnostics,
                "数据中心只管理历史行情、覆盖和质量",
                "未进入 Broker，未启用 ExecutionTarget",
            ),
        )

    def check_quality(
        self,
        *,
        timeframe: str | BarTimeframe = BarTimeframe.M1,
        source: str = MarketDataSource.READ_ONLY_ADAPTER.value,
    ) -> tuple[DataQualityRow, ...]:
        return self._quality_rows(timeframe=timeframe, source=source)

    def _akshare_status(self) -> DataSourceStatus:
        snapshot = self._runtime.health() if self._runtime is not None else None
        return DataSourceStatus(
            name="AkShare",
            status="已启用" if snapshot and snapshot.configured else "未配置",
            enabled=bool(snapshot and snapshot.configured),
            latest_connection="已连接" if snapshot and snapshot.network_call_occurred else "无",
            latest_error=str(snapshot.latest_error or "无") if snapshot else "无",
            version="运行时检测",
        )

    def _instrument_rows(self, *, source: str) -> tuple[InstrumentDataCenterRow, ...]:
        rows: list[InstrumentDataCenterRow] = []
        for symbol in self._symbols:
            mapping = AKSHARE_SYMBOL_MAPPINGS[symbol]
            resolution = self._resolver.resolve(symbol, date(2026, 6, 29))
            rows.append(
                InstrumentDataCenterRow(
                    symbol=symbol.upper(),
                    main_contract=resolution.instrument_id or mapping.akshare_symbol,
                    trade_contract=resolution.trade_instrument_id or "未解析",
                    exchange=resolution.exchange or mapping.exchange,
                    resolver="InstrumentResolver",
                    data_source=source,
                    mapping=mapping.akshare_symbol,
                    status="可用" if mapping.enabled else "已禁用",
                )
            )
        return tuple(rows)

    def _coverage_rows(
        self,
        *,
        timeframe: str | BarTimeframe,
        source: str,
    ) -> tuple[HistoricalCoverageRow, ...]:
        raw_rows: tuple[dict[str, object], ...] = ()
        if self._repository is not None:
            raw_rows = self._repository.list_coverage(
                symbols=self._symbols,
                timeframe=timeframe,
                source=source,
            )
        by_symbol: dict[str, dict[str, object]] = {
            str(row.get("symbol", "")).lower(): row for row in raw_rows
        }
        rows: list[HistoricalCoverageRow] = []
        for symbol in self._symbols:
            raw: dict[str, object] = by_symbol.get(symbol, {})
            rows.append(
                HistoricalCoverageRow(
                    symbol=symbol.upper(),
                    coverage_start=_text(raw.get("coverage_start"), "无"),
                    coverage_end=_text(raw.get("coverage_end"), "无"),
                    bar_count=_int(raw.get("bar_count"), 0),
                    latest_sync=_text(raw.get("latest_sync"), "未同步"),
                    source=_text(raw.get("source"), source),
                )
            )
        return tuple(rows)

    def _quality_rows(
        self,
        *,
        timeframe: str | BarTimeframe,
        source: str,
    ) -> tuple[DataQualityRow, ...]:
        rows: list[DataQualityRow] = []
        for symbol in self._symbols:
            raw: dict[str, object] = (
                self._repository.get_quality_summary(
                    symbol=symbol,
                    timeframe=timeframe,
                    source=source,
                )
                if self._repository is not None
                else {}
            )
            rows.append(
                DataQualityRow(
                    symbol=symbol.upper(),
                    missing_bars=_int(raw.get("missing_bars"), 0),
                    duplicate_bars=_int(raw.get("duplicate_bars"), 0),
                    abnormal_bars=_int(raw.get("abnormal_bars"), 0),
                    gap_count=_int(raw.get("gap_count"), 0),
                    continuity=_text(raw.get("continuity"), "待检查"),
                    coverage_ratio=_text(raw.get("coverage_ratio"), "0%"),
                    sync_status=_text(raw.get("sync_status"), "待同步"),
                )
            )
        return tuple(rows)

    def _diagnostics(self) -> DataCenterDiagnostics:
        return DataCenterDiagnostics(
            resolver="可用",
            repository="已配置" if self._repository is not None else "未配置",
            historical_bar="已建模",
            akshare="显式点击才读取",
            sync_service="已配置" if self._ingestion_service is not None else "未配置",
            database="只读查询；同步仅写 HistoricalBar",
        )


def _quality_ratio(symbol: str, rows: tuple[DataQualityRow, ...]) -> str:
    for row in rows:
        if row.symbol == symbol.upper():
            return row.coverage_ratio
    return "未知"


def _text(value: object, default: str) -> str:
    if value is None:
        return default
    return str(value)


def _int(value: object, default: int) -> int:
    try:
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            return int(value)
        return default
    except (TypeError, ValueError):
        return default
