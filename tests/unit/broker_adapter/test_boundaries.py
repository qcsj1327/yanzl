import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BROKER_ADAPTER_DIR = ROOT / "src" / "futures_mvp" / "modules" / "broker_adapter"
RUNTIME_DIR = ROOT / "src" / "futures_mvp" / "modules" / "runtime"
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


def _broker_sources() -> str:
    return "\n".join(path.read_text() for path in BROKER_ADAPTER_DIR.glob("*.py"))


def test_broker_adapter_has_no_oms_risk_trade_position_or_accounting_imports() -> None:
    forbidden = {
        "futures_mvp.modules.oms.service",
        "futures_mvp.modules.oms",
        "futures_mvp.modules.risk",
        "futures_mvp.modules.trading_workflow",
        "futures_mvp.modules.oms_to_trade",
        "futures_mvp.modules.position",
        "futures_mvp.modules.margin",
        "futures_mvp.modules.pnl",
        "futures_mvp.modules.settlement",
        "futures_mvp.interfaces.repositories",
        "futures_mvp.db",
    }

    imported: set[str] = set()
    for path in BROKER_ADAPTER_DIR.glob("*.py"):
        imported.update(_imports(path))

    assert forbidden.isdisjoint(imported)


def test_broker_adapter_has_no_live_network_or_broker_dependencies() -> None:
    forbidden_fragments = ("ctp", "simnow", "brokerapi", "socket", "requests", "httpx", "grpc")

    imported: set[str] = set()
    for path in BROKER_ADAPTER_DIR.glob("*.py"):
        imported.update(name.lower() for name in _imports(path))

    assert all(
        not any(fragment in imported_name for fragment in forbidden_fragments)
        for imported_name in imported
    )


def test_broker_adapter_does_not_define_forbidden_business_fact_models() -> None:
    source = _broker_sources()

    assert "BrokerCommand" not in source
    assert "BrokerReport(" not in source
    assert "BrokerReportEnvelope" not in source
    assert "class BrokerReport" not in source


def test_broker_adapter_does_not_call_business_mutation_boundaries() -> None:
    source = _broker_sources()

    forbidden_calls = [
        "apply_order_event",
        "create_order",
        "append_trade",
        "create_or_get_trade",
        "apply_trade",
        "append_margin_snapshot",
        "append_pnl_snapshot",
        "settle(",
    ]
    for call in forbidden_calls:
        assert call not in source


def test_stage_n_schema_change_is_limited_to_report_identity_constraint() -> None:
    stage_n_migrations = [
        path
        for path in ALEMBIC_DIR.glob("*.py")
        if "stage_n" in path.name.lower() or "broker" in path.name.lower()
    ]

    assert {path.name for path in stage_n_migrations} == {
        "0016_stage_n_report_identity_conflict.py"
    }
    migration_source = stage_n_migrations[0].read_text()
    assert "normalized_execution_reports" in migration_source
    assert "raw_report_id" in migration_source
    assert "broker_" not in migration_source
    assert "create_table" not in migration_source


def test_runtime_does_not_import_or_call_broker_adapter_directly() -> None:
    imported: set[str] = set()
    for path in RUNTIME_DIR.glob("*.py"):
        imported.update(_imports(path))
    runtime_source = "\n".join(path.read_text() for path in RUNTIME_DIR.glob("*.py"))

    assert "futures_mvp.modules.broker_adapter" not in imported
    assert "MockBrokerAdapter(" not in runtime_source
    assert "BrokerAdapter" not in runtime_source
