import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CONSOLE_DIR = ROOT / "src" / "futures_mvp" / "modules" / "operator_console"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def _console_sources() -> str:
    return "\n".join(path.read_text() for path in CONSOLE_DIR.glob("*.py"))


def test_operator_console_has_no_forbidden_imports() -> None:
    forbidden_fragments = (
        "fastapi",
        "socket",
        "requests",
        "httpx",
        "grpc",
        "futures_mvp.db",
        "futures_mvp.interfaces.repositories",
        "futures_mvp.modules.broker_adapter",
        "futures_mvp.modules.oms",
        "futures_mvp.modules.oms_to_trade",
        "futures_mvp.modules.position",
        "futures_mvp.modules.margin",
        "futures_mvp.modules.pnl",
        "futures_mvp.modules.settlement",
        "futures_mvp.modules.paper_trading",
        "futures_mvp.modules.sim_trading",
        "alembic",
    )
    imported: set[str] = set()
    for path in CONSOLE_DIR.glob("*.py"):
        imported.update(name.lower() for name in _imports(path))

    assert all(
        not any(fragment in imported_name for fragment in forbidden_fragments)
        for imported_name in imported
    )


def test_operator_console_has_no_direct_ledger_mutation_calls() -> None:
    source = _console_sources()

    forbidden_calls = (
        "append_trade",
        "create_or_get_trade",
        "append_margin_snapshot",
        "append_pnl_snapshot",
        "append_settlement_snapshot",
        "append_position_event",
        "apply_order_event(",
        "create_order(",
        "apply_trade(",
        "commit(",
        "rollback(",
    )

    for call in forbidden_calls:
        assert call not in source


def test_operator_console_does_not_enable_non_mock_targets() -> None:
    for path in CONSOLE_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            assert not (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "ExecutionTarget"
                and node.attr in {"PAPER", "SIM", "LIVE"}
            )
