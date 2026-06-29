from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from futures_mvp.modules.backtest import BacktestRequest, BacktestStatus, LocalBacktestEngine
from futures_mvp.modules.market_data.adapters import (
    ReadOnlyMarketDataAdapter,
    ReadOnlyMarketDataAdapterConfig,
)
from futures_mvp.modules.market_data.akshare_mapping import (
    AKSHARE_SYMBOL_MAPPINGS,
    AkShareSymbolMapping,
)
from futures_mvp.modules.market_data.contracts import (
    BarTimeframe,
    HistoricalBar,
    HistoricalBarsResult,
    HistoricalDataStatus,
    MarketDataSource,
)
from futures_mvp.modules.market_data.fixtures import StaticHistoricalDataFixtureProvider
from futures_mvp.modules.market_data.ingestion import (
    HistoricalDataIngestionService,
    HistoricalIngestionStatus,
)
from futures_mvp.modules.market_data.resolver import InstrumentResolver


class _MemoryHistoricalRepository:
    def __init__(self) -> None:
        self.bars: tuple[HistoricalBar, ...] = ()

    def upsert_bars(
        self,
        bars: tuple[HistoricalBar, ...],
        *,
        source: str,
        resolver_source: str,
        resolver_confidence: str,
    ) -> int:
        existing = {
            (
                bar.instrument_id,
                bar.trade_instrument_id,
                bar.exchange,
                bar.trading_day,
                bar.timeframe,
                bar.bar_ts,
            ): bar
            for bar in self.bars
        }
        added = 0
        for bar in bars:
            key = (
                bar.instrument_id,
                bar.trade_instrument_id,
                bar.exchange,
                bar.trading_day,
                bar.timeframe,
                bar.bar_ts,
            )
            if key not in existing:
                added += 1
            existing[key] = bar
        self.bars = tuple(existing.values())
        return added

    def get_bars(
        self,
        identity: object,
        timeframe: str | BarTimeframe,
        trading_day: date | None = None,
        *,
        source: str = MarketDataSource.READ_ONLY_ADAPTER.value,
    ) -> HistoricalBarsResult:
        value = getattr(identity, "identity", identity)
        day = trading_day or getattr(value, "trading_day", None)
        requested = BarTimeframe(timeframe)
        bars = tuple(
            bar
            for bar in self.bars
            if bar.symbol == getattr(value, "symbol", None)
            and bar.instrument_id == getattr(value, "instrument_id", None)
            and bar.trade_instrument_id == getattr(value, "trade_instrument_id", None)
            and bar.exchange == getattr(value, "exchange", None)
            and bar.trading_day == day
            and bar.timeframe is requested
        )
        if not bars:
            return HistoricalBarsResult(
                status=HistoricalDataStatus.BLOCKED,
                diagnostics=("本地历史行情库无数据", "Backtest 不会直接访问 AkShare"),
            )
        return HistoricalBarsResult(
            status=HistoricalDataStatus.OK,
            bars=tuple(sorted(bars, key=lambda bar: bar.bar_ts)),
            diagnostics=("数据源=local_historical_db",),
        )

    def get_coverage(
        self,
        identity: object,
        timeframe: str | BarTimeframe,
        trading_day: date | None = None,
        *,
        source: str,
    ) -> dict[str, object]:
        result = self.get_bars(identity, timeframe, trading_day, source=source)
        return {
            "status": "OK" if result.bars else "BLOCKED",
            "bar_count": len(result.bars),
            "latest_bar_ts": result.bars[-1].bar_ts if result.bars else None,
            "latest_ingested_at": datetime(2026, 6, 12, 10, 0)
            if result.bars
            else None,
            "source": source,
            "reason": "无" if result.bars else "本地历史行情库无数据",
        }


class _EmptyAdapter(StaticHistoricalDataFixtureProvider):
    def get_bars(self, *_args: object, **_kwargs: object) -> HistoricalBarsResult:
        return HistoricalBarsResult(status=HistoricalDataStatus.OK, bars=())


class _UnavailableAdapter(StaticHistoricalDataFixtureProvider):
    def get_bars(self, *_args: object, **_kwargs: object) -> HistoricalBarsResult:
        return HistoricalBarsResult(
            status=HistoricalDataStatus.BLOCKED,
            diagnostics=("AkShare 未安装或不可用：ImportError",),
        )


class _FailingHistoricalRepository(_MemoryHistoricalRepository):
    def upsert_bars(
        self,
        bars: tuple[HistoricalBar, ...],
        *,
        source: str,
        resolver_source: str,
        resolver_confidence: str,
    ) -> int:
        raise RuntimeError("数据库不可用")


def _request(repository: object) -> BacktestRequest:
    return BacktestRequest(
        strategy_name="noop",
        symbol="ao",
        start_trading_day=date(2026, 6, 12),
        end_trading_day=date(2026, 6, 12),
        timeframe="1m",
        initial_cash=Decimal("100000"),
        resolver=InstrumentResolver(),
        data_provider=repository,
        data_source=MarketDataSource.LOCAL_HISTORICAL_DB.value,
    )


def test_ingestion_fake_adapter_success_writes_standardized_bars() -> None:
    repository = _MemoryHistoricalRepository()
    service = HistoricalDataIngestionService(
        resolver=InstrumentResolver(),
        adapter=StaticHistoricalDataFixtureProvider(),
        repository=repository,
    )

    result = service.ingest_symbol("ao", date(2026, 6, 12), BarTimeframe.M1)

    assert result.status is HistoricalIngestionStatus.COMPLETED
    assert result.bar_count == 3
    assert repository.bars[0].instrument_id == "ao9999"
    assert repository.bars[0].trade_instrument_id == "ao2609"
    assert "链路=真实数据源 -> 标准化 -> 本地库" in result.diagnostics


def test_ingestion_fake_akshare_success_writes_to_repository() -> None:
    repository = _MemoryHistoricalRepository()
    adapter = ReadOnlyMarketDataAdapter(
        ReadOnlyMarketDataAdapterConfig(enabled=True),
        client=_FakeAkShareClient(),
    )
    service = HistoricalDataIngestionService(
        resolver=InstrumentResolver(
            data_source=MarketDataSource.READ_ONLY_ADAPTER,
            adapter=adapter,
        ),
        adapter=adapter,
        repository=repository,
    )

    result = service.ingest_symbol("ao", date(2026, 6, 12), BarTimeframe.M1)

    assert result.status is HistoricalIngestionStatus.COMPLETED
    assert result.bars_written == 1
    assert result.bars_updated == 0
    assert result.bars_skipped == 0
    assert result.bar_count == 1
    assert repository.bars[0].close == Decimal("3205")


def test_repeated_ingestion_is_idempotent() -> None:
    repository = _MemoryHistoricalRepository()
    service = HistoricalDataIngestionService(
        resolver=InstrumentResolver(),
        adapter=StaticHistoricalDataFixtureProvider(),
        repository=repository,
    )

    first = service.ingest_symbol("ao", date(2026, 6, 12), BarTimeframe.M1)
    second = service.ingest_symbol("ao", date(2026, 6, 12), BarTimeframe.M1)

    assert first.status is HistoricalIngestionStatus.COMPLETED
    assert second.status is HistoricalIngestionStatus.COMPLETED
    assert first.bars_written == 3
    assert second.bars_written == 0
    assert second.bars_skipped == 3
    assert len(repository.bars) == 3


def test_ingestion_resolver_failure_is_blocked() -> None:
    service = HistoricalDataIngestionService(
        resolver=InstrumentResolver(),
        adapter=StaticHistoricalDataFixtureProvider(),
        repository=_MemoryHistoricalRepository(),
    )

    result = service.ingest_symbol("ao", date(2027, 1, 1), BarTimeframe.M1)

    assert result.status is HistoricalIngestionStatus.BLOCKED
    assert result.reason == "解析器失败，历史行情同步已阻断"


def test_ingestion_unmapped_symbol_is_blocked_before_resolver() -> None:
    service = HistoricalDataIngestionService(
        resolver=InstrumentResolver(),
        adapter=StaticHistoricalDataFixtureProvider(),
        repository=_MemoryHistoricalRepository(),
    )

    result = service.ingest_symbol("zz", date(2026, 6, 12), BarTimeframe.M1)

    assert result.status is HistoricalIngestionStatus.BLOCKED
    assert result.reason == "品种未配置 AkShare 映射"


def test_ingestion_disabled_mapping_is_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    disabled_mapping = AkShareSymbolMapping(
        symbol="ao",
        akshare_symbol="AO0",
        exchange="SHFE",
        display_name="氧化铝",
        enabled=False,
        diagnostics=("测试禁用",),
    )
    monkeypatch.setitem(AKSHARE_SYMBOL_MAPPINGS, "ao", disabled_mapping)
    service = HistoricalDataIngestionService(
        resolver=InstrumentResolver(),
        adapter=StaticHistoricalDataFixtureProvider(),
        repository=_MemoryHistoricalRepository(),
    )

    result = service.ingest_symbol("ao", date(2026, 6, 12), BarTimeframe.M1)

    assert result.status is HistoricalIngestionStatus.BLOCKED
    assert result.reason == "AkShare 映射已禁用"


def test_ingestion_empty_data_is_blocked() -> None:
    service = HistoricalDataIngestionService(
        resolver=InstrumentResolver(),
        adapter=_EmptyAdapter(),
        repository=_MemoryHistoricalRepository(),
    )

    result = service.ingest_symbol("ao", date(2026, 6, 12), BarTimeframe.M1)

    assert result.status is HistoricalIngestionStatus.BLOCKED
    assert result.reason == "AkShare 返回空数据，历史行情同步已阻断"


def test_ingestion_akshare_unavailable_is_blocked() -> None:
    service = HistoricalDataIngestionService(
        resolver=InstrumentResolver(),
        adapter=_UnavailableAdapter(),
        repository=_MemoryHistoricalRepository(),
    )

    result = service.ingest_symbol("ao", date(2026, 6, 12), BarTimeframe.M1)

    assert result.status is HistoricalIngestionStatus.BLOCKED
    assert result.reason == "AkShare 只读数据源不可用，历史行情同步已阻断"
    assert "AkShare 未安装或不可用：ImportError" in result.diagnostics


def test_ingestion_database_unavailable_is_blocked() -> None:
    service = HistoricalDataIngestionService(
        resolver=InstrumentResolver(),
        adapter=StaticHistoricalDataFixtureProvider(),
        repository=_FailingHistoricalRepository(),
    )

    result = service.ingest_symbol("ao", date(2026, 6, 12), BarTimeframe.M1)

    assert result.status is HistoricalIngestionStatus.BLOCKED
    assert result.reason == "数据库不可用或写入失败：RuntimeError"


def test_backtest_local_historical_db_without_data_is_blocked() -> None:
    result = LocalBacktestEngine().run(_request(_MemoryHistoricalRepository()))

    assert result.status is BacktestStatus.BLOCKED
    assert result.data_source_summary is not None
    assert result.data_source_summary.source == MarketDataSource.LOCAL_HISTORICAL_DB.value
    assert "本地历史行情库无数据" in result.data_source_summary.diagnostics_summary


def test_backtest_local_historical_db_with_data_completes_without_akshare() -> None:
    repository = _MemoryHistoricalRepository()
    service = HistoricalDataIngestionService(
        resolver=InstrumentResolver(),
        adapter=StaticHistoricalDataFixtureProvider(),
        repository=repository,
    )
    ingestion_result = service.ingest_symbol("ao", date(2026, 6, 12), BarTimeframe.M1)

    result = LocalBacktestEngine().run(_request(repository))

    assert ingestion_result.status is HistoricalIngestionStatus.COMPLETED
    assert result.status is BacktestStatus.COMPLETED
    assert result.bars_consumed_count == 3
    assert result.data_source_summary is not None
    assert result.data_source_summary.source == MarketDataSource.LOCAL_HISTORICAL_DB.value
    assert all("AkShare" not in message for message in result.diagnostics.messages)


def test_local_historical_db_path_does_not_enable_execution_targets() -> None:
    import futures_mvp.modules.backtest.engine as engine_module
    import futures_mvp.modules.market_data.ingestion as ingestion_module

    assert "ExecutionTarget" not in engine_module.__dict__
    assert "ExecutionTarget" not in ingestion_module.__dict__


class _FakeAkShareClient:
    def futures_display_main_sina(self) -> list[dict[str, object]]:
        return [{"symbol": "AO0", "exchange": "SHFE"}]

    def match_main_contract(self, symbol: str) -> str:
        return "AO0"

    def futures_zh_spot(
        self,
        symbol: str,
        market: str = "CF",
        adjust: str = "0",
    ) -> list[dict[str, object]]:
        return [
            {
                "symbol": "ao2609",
                "current_price": "3205",
                "volume": "10",
                "hold": "20",
            }
        ]

    def futures_zh_minute_sina(self, symbol: str, period: str) -> list[dict[str, object]]:
        return [
            {
                "datetime": "2026-06-12 09:01:00",
                "open": "3200",
                "high": "3210",
                "low": "3190",
                "close": "3205",
                "volume": "10",
                "hold": "20",
            }
        ]

    def futures_zh_daily_sina(self, symbol: str) -> list[dict[str, object]]:
        return self.futures_zh_minute_sina(symbol, "1")
