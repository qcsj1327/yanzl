from typing import get_type_hints

from futures_mvp.domain.models import OrderRequest, RiskResult, Signal
from futures_mvp.interfaces.engines import OMS, FuturesRiskEngine, StrategyEngine


def test_strategy_engine_outputs_signals_not_orders() -> None:
    hints = get_type_hints(StrategyEngine.on_market_data)

    assert hints["return"] == list[Signal]


def test_risk_engine_accepts_signal_before_order_creation() -> None:
    hints = get_type_hints(FuturesRiskEngine.check_order)

    assert hints["signal"] is Signal
    assert hints["return"] is RiskResult


def test_oms_create_order_requires_risk_result() -> None:
    hints = get_type_hints(OMS.create_order)

    assert hints["request"] is OrderRequest
    assert hints["risk_result"] is RiskResult
