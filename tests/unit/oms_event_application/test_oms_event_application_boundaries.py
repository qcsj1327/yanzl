from pathlib import Path

from futures_mvp.db import models


def test_oms_event_application_has_no_forbidden_runtime_or_accounting_dependencies() -> None:
    module_dir = Path("src/futures_mvp/modules/oms_event_application")
    module_text = "\n".join(path.read_text() for path in module_dir.glob("*.py"))

    forbidden_terms = [
        "create_order",
        "ExecutionGateway",
        "Broker",
        "TradeRepository",
        "PositionManager",
        "Kafka",
        "Celery",
        "FastAPI",
        "alembic",
    ]
    for term in forbidden_terms:
        assert term not in module_text


def test_oms_event_application_adds_no_schema_table() -> None:
    table_names = set(models.Base.metadata.tables)

    assert "oms_event_application_events" not in table_names
    assert "oms_order_event_applications" not in table_names
