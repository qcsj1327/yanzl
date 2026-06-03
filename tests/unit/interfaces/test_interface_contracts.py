from typing import get_type_hints

from futures_mvp.domain.models import (
    OrderEvent,
    OrderEventApplicationResult,
    OrderRequest,
    OrderState,
    RiskResult,
    Signal,
)
from futures_mvp.interfaces.engines import OMS, FuturesRiskEngine, StrategyEngine


def test_strategy_engine_outputs_signals_not_orders() -> None:
    hints = get_type_hints(StrategyEngine.on_market_data)

    assert hints["return"] == list[Signal]


def test_risk_engine_accepts_signal_before_order_creation() -> None:
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
