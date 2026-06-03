from datetime import UTC, datetime
from decimal import Decimal

import pytest

from futures_mvp.domain.enums import (
    Direction,
    EventApplicationStatus,
    EventSource,
    Offset,
    OrderStatus,
    OrderType,
)
from futures_mvp.domain.errors import DecimalRequiredError
from futures_mvp.domain.models import (
    OrderEvent,
    OrderEventApplicationResult,
    OrderRequest,
    OrderState,
    Position,
    Signal,
    Trade,
)


def test_order_status_complete_state_machine() -> None:
    assert [status.value for status in OrderStatus] == [
        "CREATED",
        "RISK_CHECKING",
        "REJECTED_BY_RISK",
        "RISK_ACCEPTED",
        "SUBMITTING",
        "SUBMIT_TIMEOUT",
        "SUBMIT_FAILED",
        "SUBMITTED",
        "ACKED",
        "PARTIALLY_FILLED",
        "CANCEL_PENDING",
        "CANCEL_FAILED",
        "CANCELED",
        "FILLED",
        "REJECTED_BY_EXCHANGE",
        "EXPIRED",
        "UNKNOWN",
    ]


def test_event_application_status_complete_contract() -> None:
    assert [status.value for status in EventApplicationStatus] == [
        "APPLIED",
        "DUPLICATE",
        "OLD_IGNORED",
        "MISMATCH_REJECTED",
        "ENTERED_UNKNOWN",
        "RECOVERED_FROM_UNKNOWN",
        "IGNORED_TERMINAL",
        "EVENT_KEY_COLLISION",
    ]


def test_core_models_reject_float_prices_and_quantities() -> None:
    with pytest.raises(DecimalRequiredError):
        Signal(
            signal_id="sig-1",
            account_id="acct-1",
            instrument_id="rb2610",
            exchange="SHFE",
            direction=Direction.BUY,
            offset=Offset.OPEN,
            limit_price=3500.0,
            quantity=Decimal("1"),
            created_at=datetime.now(UTC),
        )

    with pytest.raises(DecimalRequiredError):
        OrderRequest(
            client_order_id="coid-1",
            account_id="acct-1",
            instrument_id="rb2610",
            exchange="SHFE",
            direction=Direction.BUY,
            offset=Offset.OPEN,
            order_type=OrderType.LIMIT,
            limit_price=Decimal("3500"),
            quantity=1.0,
        )


def test_strategy_signal_contains_no_order_identity_or_status() -> None:
    signal = Signal(
        signal_id="sig-1",
        account_id="acct-1",
        instrument_id="rb2610",
        exchange="SHFE",
        direction=Direction.BUY,
        offset=Offset.OPEN,
        limit_price=Decimal("3500"),
        quantity=Decimal("1"),
        created_at=datetime.now(UTC),
    )

    dumped = signal.model_dump()
    assert "client_order_id" not in dumped
    assert "status" not in dumped


def test_order_event_requires_idempotency_fields_and_raw_payload() -> None:
    event = OrderEvent(
        order_id="order-1",
        previous_status=OrderStatus.SUBMITTED,
        new_status=OrderStatus.ACKED,
        event_source=EventSource.EXCHANGE,
        external_event_id="exchange-report-1",
        raw_payload={"raw": "payload"},
        occurred_at=datetime.now(UTC),
    )

    assert event.external_event_id == "exchange-report-1"
    assert event.raw_payload == {"raw": "payload"}


def test_order_state_version_defaults_to_zero_for_optimistic_locking() -> None:
    state = OrderState(order_id="order-1", request=_order_request())

    assert state.version == 0


def test_order_event_application_result_uses_typed_status_and_order() -> None:
    state = OrderState(order_id="order-1", request=_order_request())
    result = OrderEventApplicationResult(
        status=EventApplicationStatus.APPLIED,
        order=state,
    )

    assert result.status == EventApplicationStatus.APPLIED
    assert result.order == state
    assert result.reason is None


def _order_request() -> OrderRequest:
    return OrderRequest(
        client_order_id="coid-1",
        account_id="acct-1",
        instrument_id="rb2610",
        exchange="SHFE",
        direction=Direction.BUY,
        offset=Offset.OPEN,
        order_type=OrderType.LIMIT,
        limit_price=Decimal("3500"),
        quantity=Decimal("1"),
    )


def test_trade_identity_uses_account_exchange_and_exchange_trade_id() -> None:
    trade = Trade(
        account_id="acct-1",
        exchange="SHFE",
        exchange_trade_id="trade-1",
        order_id="order-1",
        instrument_id="rb2610",
        direction=Direction.BUY,
        offset=Offset.OPEN,
        price=Decimal("3500"),
        quantity=Decimal("1"),
        trade_time=datetime.now(UTC),
    )

    assert (trade.account_id, trade.exchange, trade.exchange_trade_id) == (
        "acct-1",
        "SHFE",
        "trade-1",
    )


def test_position_is_single_row_with_long_short_today_yesterday_fields() -> None:
    position = Position(account_id="acct-1", instrument_id="rb2610")

    assert position.long_today_qty == Decimal("0")
    assert position.long_yesterday_qty == Decimal("0")
    assert position.short_today_qty == Decimal("0")
    assert position.short_yesterday_qty == Decimal("0")
    assert position.frozen_long_qty == Decimal("0")
    assert position.frozen_short_qty == Decimal("0")
    assert position.margin_used == Decimal("0")
