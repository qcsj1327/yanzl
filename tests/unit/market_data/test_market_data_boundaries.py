import ast
import importlib.util
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from futures_mvp.modules.market_data import adapters as adapters_module
from futures_mvp.modules.market_data.adapters import (
    ReadOnlyMarketDataAdapter,
    ReadOnlyMarketDataAdapterConfig,
)
from futures_mvp.modules.market_data.contracts import (
    BarTimeframe,
    HistoricalDataStatus,
    MarketDataAdapter,
    MarketDataSource,
)
from futures_mvp.modules.market_data.fixtures import StaticHistoricalDataFixtureProvider
from futures_mvp.modules.market_data.resolver import InstrumentResolver

ROOT = Path(__file__).resolve().parents[3]
MARKET_DATA_DIR = ROOT / "src" / "futures_mvp" / "modules" / "market_data"
ALEMBIC_DIR = ROOT / "alembic"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_market_data_has_no_db_broker_live_or_network_imports() -> None:
    forbidden_fragments = (
        "socket",
        "requests",
        "httpx",
        "grpc",
        "futures_mvp.db",
        "futures_mvp.interfaces.repositories",
        "futures_mvp.modules.broker_adapter",
        "futures_mvp.modules.execution_gateway",
        "futures_mvp.modules.oms",
        "futures_mvp.modules.paper_trading",
        "futures_mvp.modules.sim_trading",
        "alembic",
        "subprocess",
    )

    for path in MARKET_DATA_DIR.glob("*.py"):
        imported = {name.lower() for name in _imports(path)}
        assert all(
            not any(fragment in imported_name for fragment in forbidden_fragments)
            for imported_name in imported
        )


def test_stage_u2_does_not_add_schema_or_alembic_files() -> None:
    assert MARKET_DATA_DIR.exists()
    assert not any(path.name.startswith("stage_u2") for path in ALEMBIC_DIR.rglob("*"))


def test_static_fixture_provider_satisfies_read_only_adapter_protocol() -> None:
    provider: MarketDataAdapter = StaticHistoricalDataFixtureProvider()

    symbols = provider.list_symbols()
    contracts = provider.list_contracts("ao", date(2026, 6, 12))
    main = provider.get_main_contract("ao", date(2026, 6, 12))
    trade = provider.get_trade_contract("ao", date(2026, 6, 12))

    assert "ao" in symbols
    assert len(contracts) >= 2
    assert main is not None
    assert main.instrument_id == "ao9999"
    assert trade is not None
    assert trade.instrument_id == "ao2609"


def test_akshare_dependency_is_available_in_uv_environment() -> None:
    assert importlib.util.find_spec("akshare") is not None


def test_disabled_read_only_adapter_does_not_touch_akshare_client() -> None:
    adapter = ReadOnlyMarketDataAdapter(client=_ExplodingAkShareClient())

    bars = adapter.get_bars(object(), BarTimeframe.M1)
    quote = adapter.get_latest_quote(object())

    assert adapter.configured is False
    assert adapter.list_symbols() == ()
    assert bars.status is HistoricalDataStatus.BLOCKED
    assert quote.status is HistoricalDataStatus.BLOCKED
    assert "只读行情适配器未配置" in bars.diagnostics


def test_read_only_adapter_placeholder_is_blocked_and_not_configured() -> None:
    adapter = ReadOnlyMarketDataAdapter()

    bars = adapter.get_bars(object(), BarTimeframe.M1)
    quote = adapter.get_latest_quote(object())

    assert adapter.list_symbols() == ()
    assert bars.status is HistoricalDataStatus.BLOCKED
    assert quote.status is HistoricalDataStatus.BLOCKED
    assert f"数据源={MarketDataSource.READ_ONLY_ADAPTER.value}" in bars.diagnostics
    assert "只读行情适配器未配置" in bars.diagnostics
    assert any("不会访问网络" in item for item in bars.diagnostics)


def test_resolver_marks_read_only_adapter_source_without_raw_payload_identity() -> None:
    resolver = InstrumentResolver(data_source=MarketDataSource.READ_ONLY_ADAPTER)

    resolution = resolver.resolve("ao", "2026-06-12")

    assert resolution.source == MarketDataSource.READ_ONLY_ADAPTER.value
    assert resolution.instrument_id is None
    assert resolution.trade_instrument_id is None
    assert "只读行情适配器未配置" in resolution.diagnostics
    assert "解析器不会把适配器原始载荷作为身份事实源" in resolution.diagnostics


def test_configured_read_only_adapter_reads_symbols_contract_quote_and_bars() -> None:
    adapter = ReadOnlyMarketDataAdapter(
        ReadOnlyMarketDataAdapterConfig(enabled=True),
        client=_FakeAkShareClient(),
        now=datetime(2026, 6, 12, 10, 0),
    )
    resolver = InstrumentResolver(
        data_source=MarketDataSource.READ_ONLY_ADAPTER,
        adapter=adapter,
    )
    resolution = resolver.resolve("ao", date(2026, 6, 12))

    assert adapter.list_symbols() == ("ao",)
    assert resolution.status.name == "RESOLVED"
    assert resolution.instrument_id == "ao9999"
    assert resolution.trade_instrument_id == "ao2609"
    assert resolution.source == MarketDataSource.READ_ONLY_ADAPTER.value
    context = resolver.resolve("ao", date(2026, 6, 12))
    bars = adapter.get_bars(
        _Identity(
            symbol="ao",
            instrument_id=context.instrument_id or "",
            trade_instrument_id=context.trade_instrument_id or "",
            exchange=context.exchange or "",
            trading_day=date(2026, 6, 12),
        ),
        BarTimeframe.M1,
    )
    quote = adapter.get_latest_quote(
        _Identity(
            symbol="ao",
            instrument_id="ao9999",
            trade_instrument_id="ao2609",
            exchange="SHFE",
            trading_day=date(2026, 6, 12),
        )
    )

    assert bars.status is HistoricalDataStatus.OK
    assert bars.bars[0].close == Decimal("3205")
    assert quote.status is HistoricalDataStatus.OK
    assert quote.quote is not None
    assert quote.quote.trade_instrument_id == "ao2609"


def test_configured_read_only_adapter_fails_closed_on_empty_data() -> None:
    adapter = ReadOnlyMarketDataAdapter(
        ReadOnlyMarketDataAdapterConfig(enabled=True),
        client=_EmptyAkShareClient(),
    )

    quote = adapter.get_latest_quote(
        _Identity(
            symbol="ao",
            instrument_id="ao9999",
            trade_instrument_id="ao2609",
            exchange="SHFE",
            trading_day=date(2026, 6, 12),
        )
    )

    assert quote.status is HistoricalDataStatus.BLOCKED
    assert "行情接口返回空报价" in quote.diagnostics


def test_configured_read_only_adapter_blocks_when_akshare_import_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_import_error(name: str) -> object:
        raise ImportError(name)

    monkeypatch.setattr(adapters_module, "import_module", _raise_import_error)
    adapter = ReadOnlyMarketDataAdapter(ReadOnlyMarketDataAdapterConfig(enabled=True))

    quote = adapter.get_latest_quote(
        _Identity(
            symbol="ao",
            instrument_id="ao9999",
            trade_instrument_id="ao2609",
            exchange="SHFE",
            trading_day=date(2026, 6, 12),
        )
    )

    assert quote.status is HistoricalDataStatus.BLOCKED
    assert "AkShare 未安装或不可用：ImportError" in quote.diagnostics


def test_configured_read_only_adapter_fails_closed_on_api_error() -> None:
    adapter = ReadOnlyMarketDataAdapter(
        ReadOnlyMarketDataAdapterConfig(enabled=True),
        client=_ExplodingAkShareClient(),
    )

    bars = adapter.get_bars(
        _Identity(
            symbol="ao",
            instrument_id="ao9999",
            trade_instrument_id="ao2609",
            exchange="SHFE",
            trading_day=date(2026, 6, 12),
        ),
        BarTimeframe.M1,
    )

    assert bars.status is HistoricalDataStatus.BLOCKED
    assert "行情接口异常：RuntimeError" in bars.diagnostics


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
                "bid_price": "3204",
                "ask_price": "3206",
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


class _EmptyAkShareClient(_FakeAkShareClient):
    def futures_zh_spot(
        self,
        symbol: str,
        market: str = "CF",
        adjust: str = "0",
    ) -> list[dict[str, object]]:
        return []


class _ExplodingAkShareClient(_FakeAkShareClient):
    def futures_display_main_sina(self) -> list[dict[str, object]]:
        raise RuntimeError("不应调用")

    def futures_zh_spot(
        self,
        symbol: str,
        market: str = "CF",
        adjust: str = "0",
    ) -> list[dict[str, object]]:
        raise RuntimeError("接口错误")

    def futures_zh_minute_sina(self, symbol: str, period: str) -> list[dict[str, object]]:
        raise RuntimeError("接口错误")


class _Identity:
    def __init__(
        self,
        *,
        symbol: str,
        instrument_id: str,
        trade_instrument_id: str,
        exchange: str,
        trading_day: date,
    ) -> None:
        self.symbol = symbol
        self.instrument_id = instrument_id
        self.trade_instrument_id = trade_instrument_id
        self.exchange = exchange
        self.trading_day = trading_day
