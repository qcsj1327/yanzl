from futures_mvp.interfaces.repositories import (
    OrderIntentRepository,
    TradingRiskResultRepository,
    TradingWorkflowUnitOfWork,
    UnitOfWork,
)


def test_trading_workflow_repository_protocols_are_runtime_checkable() -> None:
    assert TradingRiskResultRepository
    assert OrderIntentRepository


def test_uow_exposes_trading_workflow_repositories() -> None:
    assert "trading_risk_results" in UnitOfWork.__annotations__
    assert "order_intents" in UnitOfWork.__annotations__
    assert "trading_risk_results" in TradingWorkflowUnitOfWork.__annotations__
    assert "order_intents" in TradingWorkflowUnitOfWork.__annotations__
    for forbidden in [
        "orders",
        "order_events",
        "trades",
        "positions",
        "position_events",
        "margin_snapshots",
        "pnl_snapshots",
        "account_snapshots",
        "settlement_snapshots",
    ]:
        assert forbidden not in TradingWorkflowUnitOfWork.__annotations__
