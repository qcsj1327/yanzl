import ast
from pathlib import Path

OPS_SAFETY_DIR = Path("src/futures_mvp/modules/ops_safety")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_ops_safety_does_not_add_schema_or_alembic_revision() -> None:
    assert not list(Path("alembic/versions").glob("*stage_o*"))
    assert not list(Path("alembic/versions").glob("*ops_safety*"))


def test_ops_safety_has_no_broker_or_external_monitoring_dependency() -> None:
    forbidden = {
        "broker",
        "ctp",
        "simnow",
        "fastapi",
        "celery",
        "kafka",
        "prometheus",
        "grafana",
    }
    imported = set()
    for path in OPS_SAFETY_DIR.glob("*.py"):
        imported.update(name.lower() for name in _imports(path))

    assert all(not any(fragment in name for fragment in forbidden) for name in imported)


def test_ops_safety_does_not_define_business_fact_mutation_calls() -> None:
    forbidden_calls = {
        "append_margin_snapshot",
        "append_pnl_snapshot",
        "append_settlement_snapshot",
        "append_position_event",
        "update_position",
        "apply_order_event(",
        "create_order(",
        "append_trade",
    }
    text = "\n".join(path.read_text() for path in OPS_SAFETY_DIR.glob("*.py"))

    assert all(call not in text for call in forbidden_calls)


def test_ops_safety_does_not_use_raw_payload_as_source_of_truth() -> None:
    text = "\n".join(path.read_text() for path in OPS_SAFETY_DIR.glob("*.py"))

    assert "raw_payload" not in text
