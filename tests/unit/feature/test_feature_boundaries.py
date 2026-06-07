import ast
from pathlib import Path

FEATURE_MODULE = Path("src/futures_mvp/modules/feature")


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module)
    return imports


def test_feature_module_has_no_forbidden_boundary_imports() -> None:
    forbidden_prefixes = (
        "futures_mvp.modules.oms",
        "futures_mvp.modules.risk",
        "futures_mvp.modules.execution",
        "futures_mvp.modules.position",
        "futures_mvp.modules.margin",
        "futures_mvp.modules.pnl",
        "futures_mvp.modules.settlement",
        "futures_mvp.db",
        "futures_mvp.adapters",
        "futures_mvp.runtime",
        "kafka",
        "redis",
        "fastapi",
    )

    imported = set()
    for path in FEATURE_MODULE.glob("*.py"):
        imported.update(_imported_modules(path))

    assert not {
        module
        for module in imported
        if any(module.startswith(prefix) for prefix in forbidden_prefixes)
    }


def test_feature_service_does_not_query_market_bars_or_source_of_truth() -> None:
    source = Path("src/futures_mvp/modules/feature/service.py").read_text()

    assert "MarketBarRepository" not in source
    assert "market_bars" not in source
    assert "list_by_instrument" not in source
    assert "list_by_trading_day" not in source


def test_stage_h_does_not_implement_strategy_signal_or_aggregator() -> None:
    source = "\n".join(path.read_text() for path in FEATURE_MODULE.glob("*.py"))

    assert "Strategy" not in source
    assert "Signal" not in source
    assert "Aggregator" not in source
    assert "aggregate" not in source.lower()
