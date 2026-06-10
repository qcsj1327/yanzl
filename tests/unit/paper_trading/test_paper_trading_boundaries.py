import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PAPER_TRADING_DIR = ROOT / "src" / "futures_mvp" / "modules" / "paper_trading"
EXECUTION_GATEWAY_SERVICE = (
    ROOT / "src" / "futures_mvp" / "modules" / "execution_gateway" / "service.py"
)
ALEMBIC_DIR = ROOT / "alembic" / "versions"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def _paper_sources() -> str:
    return "\n".join(path.read_text() for path in PAPER_TRADING_DIR.glob("*.py"))


def test_paper_trading_has_no_business_mutation_imports() -> None:
    forbidden = {
        "futures_mvp.modules.oms",
        "futures_mvp.modules.oms.service",
        "futures_mvp.modules.oms_to_trade",
        "futures_mvp.modules.position",
        "futures_mvp.modules.margin",
        "futures_mvp.modules.pnl",
        "futures_mvp.modules.settlement",
        "futures_mvp.interfaces.repositories",
        "futures_mvp.db",
    }
    imported: set[str] = set()
    for path in PAPER_TRADING_DIR.glob("*.py"):
        imported.update(_imports(path))

    assert forbidden.isdisjoint(imported)


def test_paper_trading_does_not_call_business_mutation_boundaries() -> None:
    source = _paper_sources()

    forbidden_calls = [
        "apply_order_event",
        "append_trade",
        "create_or_get_trade",
        "apply_trade",
        "append_margin_snapshot",
        "append_pnl_snapshot",
        "settle(",
    ]
    for call in forbidden_calls:
        assert call not in source


def test_paper_trading_has_no_live_network_or_broker_dependencies() -> None:
    forbidden_fragments = ("ctp", "simnow", "brokerapi", "socket", "requests", "httpx", "grpc")
    imported: set[str] = set()
    for path in PAPER_TRADING_DIR.glob("*.py"):
        imported.update(name.lower() for name in _imports(path))

    assert all(
        not any(fragment in imported_name for fragment in forbidden_fragments)
        for imported_name in imported
    )


def test_paper_trading_does_not_add_schema_or_alembic_revision() -> None:
    stage_p1_migrations = [
        path
        for path in ALEMBIC_DIR.glob("*.py")
        if "paper" in path.name.lower() or "stage_p1" in path.name.lower()
    ]

    assert stage_p1_migrations == []


def test_execution_gateway_still_rejects_non_mock_targets() -> None:
    source = EXECUTION_GATEWAY_SERVICE.read_text()

    assert "if execution_target is not ExecutionTarget.MOCK" in source
    assert "REJECTED_UNSUPPORTED_TARGET" in source
    assert "ExecutionTarget.PAPER" not in source
