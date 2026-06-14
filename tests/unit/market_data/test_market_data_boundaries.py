import ast
from pathlib import Path

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
