from pathlib import Path

STRATEGY_MODULE_ROOT = Path("src/futures_mvp/modules/strategy")


def _strategy_source() -> str:
    return "\n".join(path.read_text() for path in STRATEGY_MODULE_ROOT.glob("*.py"))


def test_strategy_module_has_no_forbidden_integration_imports() -> None:
    source = _strategy_source()

    for forbidden in [
        "modules.oms",
        "modules.risk",
        "modules.execution",
        "modules.margin",
        "modules.pnl",
        "modules.position",
        "modules.settlement",
        "OrderRequest",
        "create_order",
        "orders",
        "broker",
        "modules.runtime",
    ]:
        assert forbidden not in source
