import inspect
from pathlib import Path

from futures_mvp.db.repositories import SQLAlchemyOrderIntentRepository


def _workflow_source() -> str:
    module_dir = Path("src/futures_mvp/modules/trading_workflow")
    return "\n".join(path.read_text() for path in module_dir.glob("*.py"))


def test_trading_workflow_module_has_no_forbidden_runtime_imports() -> None:
    source = _workflow_source()

    for forbidden in [
        "modules.oms",
        "modules.execution",
        "modules.risk",
        "mock_exchange",
        "Broker",
        "Accounting",
        "OrderRequest",
        "OrderStatus",
        "OrderEvent",
        "RiskEngine",
        "create_order",
        "submit(",
        "orders",
        "order_events",
    ]:
        assert forbidden not in source


def test_order_intent_is_not_persisted_to_orders_table() -> None:
    source = inspect.getsource(SQLAlchemyOrderIntentRepository)

    assert "OrderIntentOrm" in source
    assert "OrderIntentOrm(" in source
    assert "Order(" not in source
    assert "create_order" not in source
