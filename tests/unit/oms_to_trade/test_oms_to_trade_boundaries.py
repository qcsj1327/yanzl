import ast
from pathlib import Path

from futures_mvp.db import models

ROOT = Path(__file__).resolve().parents[3]
MODULE_DIR = ROOT / "src" / "futures_mvp" / "modules" / "oms_to_trade"
MIGRATION = ROOT / "alembic" / "versions" / "0014_stage_l3_oms_to_trade_bridge.py"


def _module_sources() -> str:
    return "\n".join(path.read_text() for path in MODULE_DIR.glob("*.py"))


def test_oms_to_trade_bridge_does_not_call_oms_or_position_accounting() -> None:
    source = _module_sources()
    tree = ast.parse(source)

    forbidden_names = {
        "OMSService",
        "PositionManager",
        "MarginEngine",
        "PnLEngine",
        "SettlementEngine",
        "Broker",
        "Kafka",
        "Celery",
        "FastAPI",
    }
    forbidden_attrs = {
        "apply_order_event",
        "create_order",
        "apply_trade",
        "update_position",
        "update_margin",
        "mark_to_market",
        "settle",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            assert node.id not in forbidden_names
        if isinstance(node, ast.Attribute):
            assert node.attr not in forbidden_attrs


def test_stage_l3_migration_does_not_create_second_trade_ledger_or_accounting_schema() -> None:
    source = MIGRATION.read_text()

    assert "op.create_table" not in source
    assert "trades" in source
    assert "normalized_execution_reports" in source
    for forbidden in [
        "position_events",
        "positions",
        "margin_snapshots",
        "pnl_snapshots",
        "settlement_snapshots",
        "order_events",
        "orders",
        "broker",
    ]:
        assert forbidden not in source


def test_stage_l3_adds_no_second_trade_table() -> None:
    table_names = set(models.Base.metadata.tables)

    assert "trades" in table_names
    assert "trade_ledger" not in table_names
    assert "oms_to_trade_events" not in table_names
