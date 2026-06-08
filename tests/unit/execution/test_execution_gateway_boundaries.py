import ast
from pathlib import Path


def _imports(module_path: Path) -> set[str]:
    tree = ast.parse(module_path.read_text())
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_execution_gateway_has_no_forbidden_runtime_or_broker_imports() -> None:
    module_dir = Path("src/futures_mvp/modules/execution_gateway")
    forbidden = {
        "futures_mvp.modules.oms.service",
        "futures_mvp.modules.oms.state_machine",
        "futures_mvp.modules.position",
        "futures_mvp.modules.margin",
        "futures_mvp.modules.pnl",
        "futures_mvp.modules.settlement",
        "futures_mvp.modules.execution.models",
        "futures_mvp.modules.execution.mapper",
        "futures_mvp.modules.execution.orchestrator",
        "futures_mvp.modules.execution.reports",
        "broker",
        "ctp",
        "simnow",
        "kafka",
        "fastapi",
        "celery",
    }

    imported: set[str] = set()
    for path in module_dir.glob("*.py"):
        imported.update(_imports(path))

    assert forbidden.isdisjoint(imported)


def test_execution_gateway_does_not_define_report_fill_trade_or_order_event_generation() -> None:
    module_text = "\n".join(
        path.read_text() for path in Path("src/futures_mvp/modules/execution_gateway").glob("*.py")
    )

    assert "ExecutionReport" not in module_text
    assert "ExchangeReport" not in module_text
    assert "FillEvent" not in module_text
    assert "Trade(" not in module_text
    assert "OrderEvent" not in module_text
    assert "apply_order_event" not in module_text
