import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MODULE_DIR = ROOT / "src" / "futures_mvp" / "modules" / "execution_reports"
MIGRATION = ROOT / "alembic" / "versions" / "0013_stage_l_execution_report_normalization.py"


def _module_sources() -> str:
    return "\n".join(path.read_text() for path in MODULE_DIR.glob("*.py"))


def test_execution_report_normalizer_does_not_call_oms_apply() -> None:
    tree = ast.parse(_module_sources())

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            assert node.attr != "apply_order_event"
        if isinstance(node, ast.Name):
            assert node.id != "OMSService"


def test_execution_report_module_does_not_generate_trade_fill_position_or_accounting() -> None:
    source = _module_sources()

    forbidden = [
        "Trade(",
        "Fill",
        "Position",
        "Accounting",
        "Margin",
        "PnL",
        "Settlement",
        "Broker",
        "CTP",
        "SimNow",
    ]
    for token in forbidden:
        assert token not in source


def test_stage_l_migration_only_creates_normalized_execution_reports() -> None:
    source = MIGRATION.read_text()

    assert "normalized_execution_reports" in source
    for forbidden in [
        "raw_execution_reports",
        "trades",
        "fills",
        "broker",
        "accounting",
        "order_events",
    ]:
        assert forbidden not in source
