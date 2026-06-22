import ast
from datetime import date
from pathlib import Path

from futures_mvp.modules.market_data.adapters import ReadOnlyMarketDataAdapter
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


def test_read_only_adapter_placeholder_is_blocked_and_not_configured() -> None:
    adapter = ReadOnlyMarketDataAdapter()

    bars = adapter.get_bars(object(), BarTimeframe.M1)
    quote = adapter.get_latest_quote(object())

    assert adapter.list_symbols() == ()
    assert bars.status is HistoricalDataStatus.BLOCKED
    assert quote.status is HistoricalDataStatus.BLOCKED
    assert f"source={MarketDataSource.READ_ONLY_ADAPTER.value}" in bars.diagnostics
    assert "read-only market data adapter not configured" in bars.diagnostics
    assert any("no network" in item for item in bars.diagnostics)


def test_resolver_marks_read_only_adapter_source_without_raw_payload_identity() -> None:
    resolver = InstrumentResolver(data_source=MarketDataSource.READ_ONLY_ADAPTER)

    resolution = resolver.resolve("ao", "2026-06-12")

    assert resolution.source == MarketDataSource.READ_ONLY_ADAPTER.value
    assert resolution.instrument_id is None
    assert resolution.trade_instrument_id is None
    assert "read-only market data adapter not configured" in resolution.diagnostics
    assert "resolver does not use adapter raw payload as identity truth" in (
        resolution.diagnostics
    )
