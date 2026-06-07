import ast
from pathlib import Path

MARKET_MODULE = Path("src/futures_mvp/modules/market")


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module)
    return imports


def test_market_module_has_no_forbidden_boundary_imports() -> None:
    forbidden_prefixes = (
        "futures_mvp.modules.oms",
        "futures_mvp.modules.risk",
        "futures_mvp.modules.execution",
        "futures_mvp.modules.position",
        "futures_mvp.modules.margin",
        "futures_mvp.modules.pnl",
        "futures_mvp.modules.settlement",
        "futures_mvp.adapters",
        "futures_mvp.runtime",
        "kafka",
        "fastapi",
    )

    imported = set()
    for path in MARKET_MODULE.glob("*.py"):
        imported.update(_imported_modules(path))

    assert not {
        module
        for module in imported
        if any(module.startswith(prefix) for prefix in forbidden_prefixes)
    }


def test_stage_g_does_not_implement_tick_to_bar_aggregator() -> None:
    source = "\n".join(path.read_text() for path in MARKET_MODULE.glob("*.py"))

    assert "Aggregator" not in source
    assert "aggregate" not in source.lower()
