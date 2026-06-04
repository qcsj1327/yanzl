from typing import get_type_hints

import futures_mvp.modules.execution  # noqa: F401
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
    ExchangeCommandPort,
    ExecutionReportSink,
    FuturesRiskEngine,
    MockFuturesExchange,
    StrategyEngine,
)
from futures_mvp.modules.execution import ExchangeReport


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


def test_exchange_command_port_keeps_reports_out_of_command_return() -> None:
    public_methods = {
        name
        for name, value in ExchangeCommandPort.__dict__.items()
        if not name.startswith("_") and callable(value)
    }

    assert public_methods == {"submit_limit_order", "cancel_order"}

    submit_hints = get_type_hints(ExchangeCommandPort.submit_limit_order)
    assert submit_hints["order"] is OrderState
    assert submit_hints["return"] is type(None)

    cancel_hints = get_type_hints(ExchangeCommandPort.cancel_order)
    assert cancel_hints["order"] is OrderState
    assert cancel_hints["return"] is type(None)


def test_execution_report_sink_is_separate_local_report_surface() -> None:
    public_methods = {
        name
        for name, value in ExecutionReportSink.__dict__.items()
        if not name.startswith("_") and callable(value)
    }

    assert public_methods == {"append", "list_reports", "drain_reports"}

    append_hints = get_type_hints(ExecutionReportSink.append)
    assert append_hints["report"] is ExchangeReport
    assert append_hints["return"] is type(None)

    list_hints = get_type_hints(ExecutionReportSink.list_reports)
    assert list_hints["return"] == list[ExchangeReport]

    drain_hints = get_type_hints(ExecutionReportSink.drain_reports)
    assert drain_hints["return"] == list[ExchangeReport]
    assert "Kafka" not in (ExecutionReportSink.__doc__ or "")
    assert "Redis" not in (ExecutionReportSink.__doc__ or "")
    assert "Celery" not in (ExecutionReportSink.__doc__ or "")


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
