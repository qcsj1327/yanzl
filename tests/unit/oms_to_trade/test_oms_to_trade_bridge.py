from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from futures_mvp.domain.enums import (
    Direction,
    EventSource,
    ExecutionReportStatus,
    ExecutionTarget,
    Offset,
    OrderStatus,
    TradeBridgeResultStatus,
    TradeIdentitySource,
)
from futures_mvp.domain.models import (
    NormalizedExecutionReport,
    OrderEvent,
    OrderRequest,
    OrderState,
    Trade,
    TradeBridgeContext,
)
from futures_mvp.interfaces.repositories import TradeIdempotencyConflictError
from futures_mvp.modules.oms_to_trade import (
    OMSToTradeBridgeService,
    build_exchange_trade_id_fallback,
    build_trade_identity,
    replay_oms_to_trade,
)

NOW = datetime(2026, 6, 8, 9, tzinfo=UTC)


class FakeTradeRepository:
    def __init__(self) -> None:
        self.trades: dict[tuple[str, str, str], Trade] = {}

    def append_trade(self, trade: Trade) -> Trade:
        key = (trade.account_id, trade.exchange, trade.exchange_trade_id)
        existing = self.trades.get(key)
        if existing is not None and _canonical(existing) != _canonical(trade):
            raise TradeIdempotencyConflictError("trade canonical conflict")
        self.trades.setdefault(key, trade)
        return self.trades[key]

    def create_or_get_trade(self, trade: Trade) -> Trade:
        return self.append_trade(trade)

    def get_by_exchange_trade_id(
        self,
        account_id: str,
        exchange: str,
        exchange_trade_id: str,
    ) -> Trade | None:
        return self.trades.get((account_id, exchange, exchange_trade_id))

    def get_by_trade_identity(
        self,
        account_id: str,
        exchange: str,
        exchange_trade_id: str,
    ) -> Trade | None:
        return self.get_by_exchange_trade_id(account_id, exchange, exchange_trade_id)

    def list_by_order_id(self, order_id: str) -> list[Trade]:
        return [trade for trade in self.trades.values() if trade.order_id == order_id]


def _canonical(trade: Trade) -> tuple[object, ...]:
    return (
        trade.account_id,
        trade.exchange,
        trade.exchange_trade_id,
        trade.identity_source,
        trade.order_id,
        trade.client_order_id,
        trade.instrument_id,
        trade.trade_instrument_id,
        trade.symbol,
        trade.direction,
        trade.offset,
        trade.price,
        trade.quantity,
        trade.fee_amount,
        trade.fee_currency,
        trade.fee_source,
        trade.trade_time,
        trade.trading_day,
        trade.source_report_id,
        trade.source_order_event_id,
    )


def _order_state(status: OrderStatus = OrderStatus.PARTIALLY_FILLED) -> OrderState:
    return OrderState(
        order_id="order-1",
        status=status,
        filled_quantity=Decimal("1"),
        request=OrderRequest(
            client_order_id="client-1",
            account_id="account-1",
            instrument_id="rb2601",
            exchange="SHFE",
            direction=Direction.BUY,
            offset=Offset.OPEN,
            limit_price=Decimal("3500"),
            quantity=Decimal("2"),
        ),
    )


def _report(**updates: object) -> NormalizedExecutionReport:
    values = {
        "report_id": "report-1",
        "raw_report_id": "raw-1",
        "adapter_name": "mock",
        "execution_target": ExecutionTarget.MOCK,
        "command_id": "command-1",
        "order_id": "order-1",
        "client_order_id": "client-1",
        "adapter_order_ref": "adapter-1",
        "exchange_order_id": "exchange-order-1",
        "exchange_trade_id": "exchange-trade-1",
        "fill_id": "fill-1",
        "execution_status": ExecutionReportStatus.PARTIALLY_FILLED,
        "filled_qty": Decimal("1"),
        "fill_price": Decimal("3500"),
        "cumulative_filled_qty": Decimal("1"),
        "remaining_qty": Decimal("1"),
        "fee_amount": None,
        "fee_currency": None,
        "fee_source": None,
        "report_ts": NOW,
        "normalized_at": NOW + timedelta(seconds=1),
        "reason": None,
        "source_report_hash": "hash-1",
        "raw_payload": {"diagnostic": True},
    }
    values.update(updates)
    return NormalizedExecutionReport(**values)


def _event(status: OrderStatus = OrderStatus.PARTIALLY_FILLED, **updates: object) -> OrderEvent:
    execution_status = (
        ExecutionReportStatus.FILLED
        if status is OrderStatus.FILLED
        else ExecutionReportStatus.PARTIALLY_FILLED
    )
    values = {
        "order_id": "order-1",
        "previous_status": OrderStatus.ACKED,
        "new_status": status,
        "event_source": EventSource.EXECUTION_REPORT_NORMALIZER,
        "external_event_id": "event-1",
        "execution_status": execution_status,
        "report_id": "report-1",
        "report_ts": NOW,
        "filled_qty": Decimal("1"),
        "fill_price": Decimal("3500"),
        "cumulative_filled_qty": Decimal("1"),
        "raw_payload": {"diagnostic": True},
        "occurred_at": NOW,
    }
    values.update(updates)
    return OrderEvent(
        **values,
    )


def _context(**updates: object) -> TradeBridgeContext:
    values = {
        "normalized_report": _report(),
        "order_state": _order_state(),
        "applied_order_event": _event(),
        "symbol": "rb",
        "trade_instrument_id": "rb2601",
        "trading_day": None,
        "raw_payload": {"bridge": "diagnostic"},
    }
    values.update(updates)
    return TradeBridgeContext(**values)


def test_partially_filled_trade_created_with_exchange_trade_id() -> None:
    service = OMSToTradeBridgeService(FakeTradeRepository())

    result = service.create_trade(_context())

    assert result.status is TradeBridgeResultStatus.CREATED
    assert result.trade is not None
    assert result.trade.exchange_trade_id == "exchange-trade-1"
    assert result.trade.identity_source is TradeIdentitySource.EXCHANGE_TRADE_ID
    assert result.trade.client_order_id == "client-1"
    assert result.trade.symbol == "rb"
    assert result.trade.trade_instrument_id == "rb2601"
    assert result.trade.source_report_id == "report-1"
    assert result.trade.source_order_event_id == "event-1"


def test_filled_trade_created_from_compatible_order_state_without_event() -> None:
    service = OMSToTradeBridgeService(FakeTradeRepository())

    result = service.create_trade(
        _context(
            normalized_report=_report(
                execution_status=ExecutionReportStatus.FILLED,
                cumulative_filled_qty=Decimal("2"),
                remaining_qty=Decimal("0"),
            ),
            order_state=_order_state(OrderStatus.FILLED).model_copy(
                update={"filled_quantity": Decimal("2")}
            ),
            applied_order_event=None,
        )
    )

    assert result.status is TradeBridgeResultStatus.CREATED
    assert result.source_order_event_id is None


@pytest.mark.parametrize(
    "status",
    [
        ExecutionReportStatus.ACKED,
        ExecutionReportStatus.SUBMITTED,
        ExecutionReportStatus.REJECTED,
        ExecutionReportStatus.CANCELED,
        ExecutionReportStatus.ERROR,
    ],
)
def test_non_filled_reports_do_not_create_trade(status: ExecutionReportStatus) -> None:
    repository = FakeTradeRepository()
    service = OMSToTradeBridgeService(repository)

    result = service.create_trade(
        _context(
            normalized_report=_report(
                execution_status=status,
                filled_qty=Decimal("0"),
                fill_price=None,
            ),
        )
    )

    assert result.status is TradeBridgeResultStatus.REJECTED_NOT_FILLED
    assert repository.trades == {}


def test_un_applied_candidate_rejected() -> None:
    service = OMSToTradeBridgeService(FakeTradeRepository())

    result = service.create_trade(
        _context(order_state=_order_state(OrderStatus.ACKED), applied_order_event=None)
    )

    assert result.status is TradeBridgeResultStatus.REJECTED_OMS_NOT_APPLIED


def test_applied_event_lineage_mismatch_rejected() -> None:
    service = OMSToTradeBridgeService(FakeTradeRepository())

    result = service.create_trade(
        _context(
            applied_order_event=_event().model_copy(update={"order_id": "other-order"}),
        )
    )

    assert result.status is TradeBridgeResultStatus.REJECTED_LINEAGE_MISMATCH


@pytest.mark.parametrize(
    ("event_updates", "expected_status"),
    [
        ({"report_id": "other-report"}, TradeBridgeResultStatus.REJECTED_LINEAGE_MISMATCH),
        ({"filled_qty": Decimal("2")}, TradeBridgeResultStatus.REJECTED_LINEAGE_MISMATCH),
        ({"fill_price": Decimal("3501")}, TradeBridgeResultStatus.REJECTED_LINEAGE_MISMATCH),
        (
            {"cumulative_filled_qty": Decimal("2")},
            TradeBridgeResultStatus.REJECTED_LINEAGE_MISMATCH,
        ),
        ({"new_status": OrderStatus.FILLED}, TradeBridgeResultStatus.REJECTED_LINEAGE_MISMATCH),
        (
            {"report_ts": NOW + timedelta(seconds=1)},
            TradeBridgeResultStatus.REJECTED_LINEAGE_MISMATCH,
        ),
        ({"report_id": None}, TradeBridgeResultStatus.REJECTED_OMS_NOT_APPLIED),
        ({"execution_status": None}, TradeBridgeResultStatus.REJECTED_OMS_NOT_APPLIED),
    ],
)
def test_applied_event_must_bind_to_current_report(
    event_updates: dict[str, object],
    expected_status: TradeBridgeResultStatus,
) -> None:
    repository = FakeTradeRepository()
    service = OMSToTradeBridgeService(repository)

    result = service.create_trade(_context(applied_order_event=_event(**event_updates)))

    assert result.status is expected_status
    assert repository.trades == {}


def test_applied_event_must_come_from_execution_report_normalizer() -> None:
    repository = FakeTradeRepository()
    service = OMSToTradeBridgeService(repository)

    result = service.create_trade(
        _context(applied_order_event=_event(event_source=EventSource.EXCHANGE))
    )

    assert result.status is TradeBridgeResultStatus.REJECTED_OMS_NOT_APPLIED
    assert repository.trades == {}


def test_source_order_event_id_override_must_match_applied_event() -> None:
    repository = FakeTradeRepository()
    service = OMSToTradeBridgeService(repository)

    result = service.create_trade(_context(source_order_event_id="other-event"))

    assert result.status is TradeBridgeResultStatus.REJECTED_LINEAGE_MISMATCH
    assert repository.trades == {}


def test_applied_event_allows_matching_source_order_event_id() -> None:
    service = OMSToTradeBridgeService(FakeTradeRepository())

    result = service.create_trade(_context(source_order_event_id="event-1"))

    assert result.status is TradeBridgeResultStatus.CREATED
    assert result.trade is not None
    assert result.trade.source_order_event_id == "event-1"


def test_state_only_proof_rejects_source_order_event_id_override() -> None:
    repository = FakeTradeRepository()
    service = OMSToTradeBridgeService(repository)

    result = service.create_trade(
        _context(
            applied_order_event=None,
            source_order_event_id="event-1",
        )
    )

    assert result.status is TradeBridgeResultStatus.REJECTED_LINEAGE_MISMATCH
    assert result.trade is None
    assert repository.trades == {}


def test_compatible_state_proof_requires_filled_quantity_not_behind_report() -> None:
    repository = FakeTradeRepository()
    service = OMSToTradeBridgeService(repository)

    result = service.create_trade(
        _context(
            normalized_report=_report(cumulative_filled_qty=Decimal("2")),
            order_state=_order_state(OrderStatus.PARTIALLY_FILLED),
            applied_order_event=None,
        )
    )

    assert result.status is TradeBridgeResultStatus.REJECTED_OMS_NOT_APPLIED
    assert repository.trades == {}


def test_filled_report_requires_filled_order_state_without_event() -> None:
    repository = FakeTradeRepository()
    service = OMSToTradeBridgeService(repository)

    result = service.create_trade(
        _context(
            normalized_report=_report(execution_status=ExecutionReportStatus.FILLED),
            order_state=_order_state(OrderStatus.PARTIALLY_FILLED),
            applied_order_event=None,
        )
    )

    assert result.status is TradeBridgeResultStatus.REJECTED_OMS_NOT_APPLIED
    assert repository.trades == {}


def test_partially_filled_report_allows_compatible_state_quantity_without_event() -> None:
    service = OMSToTradeBridgeService(FakeTradeRepository())

    result = service.create_trade(
        _context(
            order_state=_order_state(OrderStatus.PARTIALLY_FILLED),
            applied_order_event=None,
        )
    )

    assert result.status is TradeBridgeResultStatus.CREATED
    assert result.trade is not None
    assert result.trade.source_order_event_id is None
    assert result.source_order_event_id is None


def test_missing_exchange_trade_id_uses_deterministic_fallback() -> None:
    service = OMSToTradeBridgeService(FakeTradeRepository())
    report = _report(exchange_trade_id=None)

    result = service.create_trade(_context(normalized_report=report))

    assert result.status is TradeBridgeResultStatus.CREATED
    assert result.trade is not None
    assert result.trade.exchange_trade_id == build_exchange_trade_id_fallback(
        account_id="account-1",
        exchange="SHFE",
        order_id="order-1",
        report_id="report-1",
        cumulative_filled_qty=Decimal("1"),
        fill_price=Decimal("3500"),
        report_ts=NOW,
    )
    assert result.trade.exchange_trade_id.startswith("derived_")
    assert result.trade.identity_source is TradeIdentitySource.DERIVED_FROM_REPORT


def test_missing_stable_trade_identity_part_rejected() -> None:
    with pytest.raises(ValueError, match="report_id is required"):
        build_trade_identity(
            account_id="account-1",
            exchange="SHFE",
            exchange_trade_id=None,
            order_id="order-1",
            report_id="",
            cumulative_filled_qty=Decimal("1"),
            fill_price=Decimal("3500"),
            report_ts=NOW,
        )


def test_missing_stable_trade_identity_service_path_rejected() -> None:
    repository = FakeTradeRepository()
    service = OMSToTradeBridgeService(repository)
    order_state = _order_state().model_copy(
        update={
            "request": _order_state().request.model_copy(update={"account_id": ""}),
        }
    )

    result = service.create_trade(
        _context(
            normalized_report=_report(exchange_trade_id=None),
            order_state=order_state,
        )
    )

    assert result.status is TradeBridgeResultStatus.REJECTED_MISSING_TRADE_IDENTITY
    assert result.trade is None
    assert repository.trades == {}


def test_duplicate_same_canonical_no_op_and_different_canonical_conflict() -> None:
    repository = FakeTradeRepository()
    service = OMSToTradeBridgeService(repository)

    first = service.create_trade(_context())
    duplicate = service.create_trade(
        _context(normalized_report=_report(raw_payload={"changed": "diagnostic"}))
    )
    conflict = service.create_trade(
        _context(
            normalized_report=_report(fill_price=Decimal("3501")),
            applied_order_event=_event(fill_price=Decimal("3501")),
        )
    )

    assert first.status is TradeBridgeResultStatus.CREATED
    assert duplicate.status is TradeBridgeResultStatus.DUPLICATE
    assert conflict.status is TradeBridgeResultStatus.CONFLICT


def test_fee_unknown_vs_zero_is_preserved() -> None:
    service = OMSToTradeBridgeService(FakeTradeRepository())

    unknown = service.create_trade(_context())
    zero_report = _report(
        report_id="report-2",
        exchange_trade_id="exchange-trade-2",
        fee_amount=Decimal("0"),
        fee_currency="CNY",
        fee_source="EXCHANGE_REPORT",
    )
    zero = service.create_trade(
        _context(
            normalized_report=zero_report,
            applied_order_event=_event(report_id="report-2", external_event_id="event-2"),
        )
    )

    assert unknown.trade is not None
    assert zero.trade is not None
    assert unknown.trade.fee_amount is None
    assert zero.trade.fee_amount == Decimal("0")
    assert zero.trade.fee_currency == "CNY"


def test_replay_orders_inputs_and_is_deterministic() -> None:
    repository = FakeTradeRepository()
    service = OMSToTradeBridgeService(repository)
    later = _context(
        normalized_report=_report(
            report_id="report-2",
            exchange_trade_id="exchange-trade-2",
            report_ts=NOW + timedelta(minutes=1),
        ),
        applied_order_event=_event(
            report_id="report-2",
            report_ts=NOW + timedelta(minutes=1),
            external_event_id="event-2",
        ),
    )
    earlier = _context()

    first = replay_oms_to_trade([later, earlier], service=service)
    second = replay_oms_to_trade([earlier, later], service=service)

    assert [result.trade.exchange_trade_id for result in first if result.trade] == [
        "exchange-trade-1",
        "exchange-trade-2",
    ]
    assert [result.status for result in second] == [
        TradeBridgeResultStatus.DUPLICATE,
        TradeBridgeResultStatus.DUPLICATE,
    ]
