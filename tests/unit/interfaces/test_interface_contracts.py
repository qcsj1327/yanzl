from typing import get_type_hints

from futures_mvp.domain.models import (
    OrderEvent,
    OrderEventApplicationResult,
    OrderRequest,
    OrderState,
    RiskResult,
    Signal,
)
from futures_mvp.interfaces.engines import (
    EMS,
    OMS,
    FuturesRiskEngine,
    MockFuturesExchange,
    StrategyEngine,
)


def test_strategy_engine_outputs_signals_not_orders() -> None:
    hints = get_type_hints(StrategyEngine.on_market_data)

    assert hints["return"] == list[Signal]


def test_risk_engine_accepts_signal_as_pure_risk_input() -> None:
    hints = get_type_hints(FuturesRiskEngine.check_order)

    assert hints["signal"] is Signal
    assert hints["return"] is RiskResult


def test_oms_protocol_matches_application_service_contract() -> None:
    hints = get_type_hints(OMS.create_order)

    assert hints["request"] is OrderRequest
    assert hints["client_order_id"] is str
    assert hints["return"] is OrderState

    risk_hints = get_type_hints(OMS.apply_risk_result)
    assert risk_hints["order_id"] is str
    assert risk_hints["risk_result"] is RiskResult
    assert risk_hints["external_event_id"] is str
    assert risk_hints["return"] is OrderEventApplicationResult

    event_hints = get_type_hints(OMS.apply_order_event)
    assert event_hints["event"] is OrderEvent
    assert event_hints["return"] is OrderEventApplicationResult

    recovery_hints = get_type_hints(OMS.recover_order)
    assert recovery_hints["order_id"] is str
    assert recovery_hints["return"] is OrderEventApplicationResult


def test_mock_futures_exchange_protocol_excludes_settlement() -> None:
    public_methods = {
        name
        for name, value in MockFuturesExchange.__dict__.items()
        if not name.startswith("_") and callable(value)
    }

    assert public_methods == {"submit_limit_order", "cancel_order"}
    assert "run_daily_settlement" not in MockFuturesExchange.__dict__

    submit_hints = get_type_hints(MockFuturesExchange.submit_limit_order)
    assert submit_hints["order"] is OrderState
    assert submit_hints["return"] is type(None)

    cancel_hints = get_type_hints(MockFuturesExchange.cancel_order)
    assert cancel_hints["order"] is OrderState
    assert cancel_hints["return"] is type(None)


def test_ems_protocol_is_command_port_only() -> None:
    public_methods = {
        name
        for name, value in EMS.__dict__.items()
        if not name.startswith("_") and callable(value)
    }

    assert public_methods == {"submit", "cancel"}

    submit_hints = get_type_hints(EMS.submit)
    assert submit_hints["order"] is OrderState
    assert submit_hints["return"] is type(None)

    cancel_hints = get_type_hints(EMS.cancel)
    assert cancel_hints["order"] is OrderState
    assert cancel_hints["return"] is type(None)
