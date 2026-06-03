from __future__ import annotations

import inspect
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from futures_mvp.domain.enums import (
    Direction,
    EventApplicationStatus,
    EventSource,
    Offset,
    OrderStatus,
    OrderType,
    RiskDecision,
)
from futures_mvp.domain.models import OrderEvent, OrderRequest, OrderState, RiskResult
from futures_mvp.interfaces.repositories import (
    EventAlreadyExistsError,
    IdempotencyConflictError,
    OptimisticLockError,
    OrderNotFoundError,
)
from futures_mvp.modules.oms import OMSService

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _clock() -> datetime:
    return NOW


def _order_request(
    client_order_id: str = "client-1",
    *,
    quantity: Decimal = Decimal("1"),
) -> OrderRequest:
    return OrderRequest(
        client_order_id=client_order_id,
        account_id="account-1",
        instrument_id="rb2601",
        exchange="SHFE",
        direction=Direction.BUY,
        offset=Offset.OPEN,
        order_type=OrderType.LIMIT,
        limit_price=Decimal("3500"),
        quantity=quantity,
    )


def _risk_result(decision: RiskDecision) -> RiskResult:
    return RiskResult(decision=decision, rule_name="unit-test-risk", reason="test")


def _event(
    order_id: str,
    *,
    previous_status: OrderStatus | None,
    new_status: OrderStatus,
    external_event_id: str = "exchange-event-1",
    event_source: EventSource = EventSource.EXCHANGE,
) -> OrderEvent:
    return OrderEvent(
        order_id=order_id,
        previous_status=previous_status,
        new_status=new_status,
        event_source=event_source,
        external_event_id=external_event_id,
        raw_payload={"diagnostic": True},
        occurred_at=NOW,
    )


class FakeOrderRepository:
    def __init__(self) -> None:
        self.orders_by_id: dict[str, OrderState] = {}
        self.client_index: dict[str, str] = {}
        self.next_id = 1
        self.force_stale_read = False
        self.update_expected_versions: list[int | None] = []

    def create_order(self, order_request: OrderRequest, *, client_order_id: str) -> OrderState:
        existing_id = self.client_index.get(client_order_id)
        if existing_id is not None:
            existing = self.orders_by_id[existing_id]
            if not self._same_payload(existing.request, order_request):
                raise IdempotencyConflictError(
                    f"client_order_id reused with different canonical payload: {client_order_id}"
                )
            return existing

        order = OrderState(order_id=str(self.next_id), request=order_request, version=0)
        self.next_id += 1
        self.orders_by_id[order.order_id] = order
        self.client_index[client_order_id] = order.order_id
        return order

    def get_by_id(self, order_id: str) -> OrderState | None:
        order = self.orders_by_id.get(order_id)
        if order is not None and self.force_stale_read:
            return order.model_copy(update={"version": max(order.version - 1, 0)})
        return order

    def get_by_client_order_id(self, client_order_id: str) -> OrderState | None:
        order_id = self.client_index.get(client_order_id)
        if order_id is None:
            return None
        return self.orders_by_id[order_id]

    def update_status(
        self,
        order_id: str,
        new_status: OrderStatus,
        *,
        expected_version: int | None = None,
    ) -> OrderState:
        order = self.orders_by_id.get(order_id)
        if order is None:
            raise OrderNotFoundError(order_id)
        self.update_expected_versions.append(expected_version)
        if expected_version is not None and expected_version != order.version:
            raise OptimisticLockError(
                f"order {order_id} version mismatch: expected {expected_version}"
            )
        updated = order.model_copy(update={"status": new_status, "version": order.version + 1})
        self.orders_by_id[order_id] = updated
        return updated

    def list_open_orders(self) -> list[OrderState]:
        return list(self.orders_by_id.values())

    def restore(self, snapshot: FakeOrderRepository) -> None:
        self.orders_by_id = deepcopy(snapshot.orders_by_id)
        self.client_index = deepcopy(snapshot.client_index)
        self.next_id = snapshot.next_id
        self.force_stale_read = snapshot.force_stale_read
        self.update_expected_versions = deepcopy(snapshot.update_expected_versions)

    def clone(self) -> FakeOrderRepository:
        clone = FakeOrderRepository()
        clone.restore(self)
        return clone

    def _same_payload(self, left: OrderRequest, right: OrderRequest) -> bool:
        return (
            left.account_id,
            left.instrument_id,
            left.exchange,
            left.direction,
            left.offset,
            left.order_type,
            left.limit_price,
            left.quantity,
        ) == (
            right.account_id,
            right.instrument_id,
            right.exchange,
            right.direction,
            right.offset,
            right.order_type,
            right.limit_price,
            right.quantity,
        )


class FakeOrderEventRepository:
    def __init__(self) -> None:
        self.events: list[OrderEvent] = []
        self.fail_next_append = False

    def append_event(self, event: OrderEvent) -> OrderEvent:
        if self.fail_next_append:
            self.fail_next_append = False
            raise RuntimeError("append failed")
        if self.get_by_event_key(event.event_source, event.external_event_id) is not None:
            raise EventAlreadyExistsError("duplicate event append")
        self.events.append(event)
        return event

    def get_by_event_key(
        self,
        event_source: EventSource,
        external_event_id: str,
    ) -> OrderEvent | None:
        return next(
            (
                event
                for event in self.events
                if event.event_source == event_source
                and event.external_event_id == external_event_id
            ),
            None,
        )

    def list_by_order_id(self, order_id: str) -> list[OrderEvent]:
        return [event for event in self.events if event.order_id == order_id]

    def restore(self, snapshot: FakeOrderEventRepository) -> None:
        self.events = deepcopy(snapshot.events)
        self.fail_next_append = snapshot.fail_next_append

    def clone(self) -> FakeOrderEventRepository:
        clone = FakeOrderEventRepository()
        clone.restore(self)
        return clone


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.orders = FakeOrderRepository()
        self.order_events = FakeOrderEventRepository()
        self.commit_count = 0
        self.rollback_count = 0
        self._orders_snapshot: FakeOrderRepository | None = None
        self._events_snapshot: FakeOrderEventRepository | None = None

    def commit(self) -> None:
        self.commit_count += 1
        self._orders_snapshot = None
        self._events_snapshot = None

    def rollback(self) -> None:
        self.rollback_count += 1
        if self._orders_snapshot is not None and self._events_snapshot is not None:
            self.orders.restore(self._orders_snapshot)
            self.order_events.restore(self._events_snapshot)

    def __enter__(self) -> FakeUnitOfWork:
        self._orders_snapshot = self.orders.clone()
        self._events_snapshot = self.order_events.clone()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> bool | None:
        del exc, tb
        if exc_type is not None:
            self.rollback()
        return None


def _service(uow: FakeUnitOfWork) -> OMSService:
    return OMSService(lambda: uow, clock=_clock)


def test_oms_service_constructor_dependency_boundary() -> None:
    signature = inspect.signature(OMSService)
    assert list(signature.parameters) == ["uow_factory", "clock"]
    assert signature.parameters["clock"].kind is inspect.Parameter.KEYWORD_ONLY

    source = Path("src/futures_mvp/modules/oms/service.py").read_text()
    forbidden = {
        "sqlalchemy",
        "futures_mvp.db",
        "futures_mvp.interfaces.engines",
        "FuturesRiskEngine",
        "EMS",
        "MockFuturesExchange",
        "PositionManager",
        "MarginEngine",
        "PnLEngine",
        "SettlementEngine",
    }
    assert all(term not in source for term in forbidden)


def test_create_order_new_order_appends_initial_event_and_commits() -> None:
    uow = FakeUnitOfWork()
    request = _order_request()

    order = _service(uow).create_order(request, client_order_id=request.client_order_id)

    assert order.status == OrderStatus.CREATED
    assert order.version == 0
    assert len(uow.orders.orders_by_id) == 1
    assert len(uow.order_events.events) == 1
    assert uow.order_events.events[0].previous_status is None
    assert uow.order_events.events[0].new_status == OrderStatus.CREATED
    assert uow.order_events.events[0].event_source == EventSource.OMS
    assert uow.commit_count == 1


def test_create_order_same_payload_is_idempotent_without_new_event() -> None:
    uow = FakeUnitOfWork()
    request = _order_request()
    service = _service(uow)

    first = service.create_order(request, client_order_id=request.client_order_id)
    second = service.create_order(request, client_order_id=request.client_order_id)

    assert second == first
    assert len(uow.orders.orders_by_id) == 1
    assert len(uow.order_events.events) == 1
    assert uow.commit_count == 1


def test_create_order_different_payload_conflicts_without_event() -> None:
    uow = FakeUnitOfWork()
    service = _service(uow)
    request = _order_request()
    service.create_order(request, client_order_id=request.client_order_id)

    with pytest.raises(IdempotencyConflictError):
        service.create_order(
            _order_request(request.client_order_id, quantity=Decimal("2")),
            client_order_id=request.client_order_id,
        )

    assert len(uow.orders.orders_by_id) == 1
    assert len(uow.order_events.events) == 1
    assert uow.rollback_count == 1


def test_create_order_event_append_failure_rolls_back_new_order() -> None:
    uow = FakeUnitOfWork()
    uow.order_events.fail_next_append = True
    request = _order_request()

    with pytest.raises(RuntimeError, match="append failed"):
        _service(uow).create_order(request, client_order_id=request.client_order_id)

    assert uow.orders.orders_by_id == {}
    assert uow.order_events.events == []
    assert uow.rollback_count == 1


def test_apply_risk_result_accepted_bridges_created_to_risk_accepted() -> None:
    uow = FakeUnitOfWork()
    service = _service(uow)
    order = service.create_order(_order_request(), client_order_id="client-1")

    result = service.apply_risk_result(
        order.order_id,
        _risk_result(RiskDecision.ACCEPTED),
        external_event_id="risk-accepted-1",
    )

    assert result.status == EventApplicationStatus.APPLIED
    accepted = result.order
    assert accepted.status == OrderStatus.RISK_ACCEPTED
    assert accepted.version == 2
    assert uow.orders.update_expected_versions == [0, 1]
    assert [event.new_status for event in uow.order_events.events] == [
        OrderStatus.CREATED,
        OrderStatus.RISK_CHECKING,
        OrderStatus.RISK_ACCEPTED,
    ]


def test_apply_risk_result_rejected_from_created() -> None:
    uow = FakeUnitOfWork()
    service = _service(uow)
    order = service.create_order(_order_request(), client_order_id="client-1")

    result = service.apply_risk_result(
        order.order_id,
        _risk_result(RiskDecision.REJECTED),
        external_event_id="risk-rejected-1",
    )

    assert result.status == EventApplicationStatus.APPLIED
    rejected = result.order
    assert rejected.status == OrderStatus.REJECTED_BY_RISK
    assert uow.order_events.events[-1].new_status == OrderStatus.REJECTED_BY_RISK


def test_apply_risk_result_accepted_from_risk_checking() -> None:
    uow = FakeUnitOfWork()
    service = _service(uow)
    order = service.create_order(_order_request(), client_order_id="client-1")
    uow.orders.update_status(order.order_id, OrderStatus.RISK_CHECKING)
    uow.orders.update_expected_versions.clear()

    result = service.apply_risk_result(
        order.order_id,
        _risk_result(RiskDecision.ACCEPTED),
        external_event_id="risk-accepted-1",
    )

    assert result.status == EventApplicationStatus.APPLIED
    accepted = result.order
    assert accepted.status == OrderStatus.RISK_ACCEPTED
    assert accepted.version == 2
    assert uow.orders.update_expected_versions == [1]
    assert uow.order_events.events[-1].previous_status == OrderStatus.RISK_CHECKING
    assert uow.order_events.events[-1].new_status == OrderStatus.RISK_ACCEPTED


def test_apply_risk_result_rejected_from_risk_checking() -> None:
    uow = FakeUnitOfWork()
    service = _service(uow)
    order = service.create_order(_order_request(), client_order_id="client-1")
    uow.orders.update_status(order.order_id, OrderStatus.RISK_CHECKING)
    uow.orders.update_expected_versions.clear()

    result = service.apply_risk_result(
        order.order_id,
        _risk_result(RiskDecision.REJECTED),
        external_event_id="risk-rejected-1",
    )

    assert result.status == EventApplicationStatus.APPLIED
    rejected = result.order
    assert rejected.status == OrderStatus.REJECTED_BY_RISK
    assert rejected.version == 2
    assert uow.orders.update_expected_versions == [1]
    assert uow.order_events.events[-1].previous_status == OrderStatus.RISK_CHECKING
    assert uow.order_events.events[-1].new_status == OrderStatus.REJECTED_BY_RISK


def test_apply_risk_result_duplicate_event_does_not_append_again() -> None:
    uow = FakeUnitOfWork()
    service = _service(uow)
    order = service.create_order(_order_request(), client_order_id="client-1")
    first = service.apply_risk_result(
        order.order_id,
        _risk_result(RiskDecision.REJECTED),
        external_event_id="risk-rejected-1",
    )

    second = service.apply_risk_result(
        order.order_id,
        _risk_result(RiskDecision.REJECTED),
        external_event_id="risk-rejected-1",
    )

    assert first.status == EventApplicationStatus.APPLIED
    assert second.status == EventApplicationStatus.DUPLICATE
    assert second.order == first.order
    assert len(uow.order_events.events) == 2


def test_apply_risk_result_duplicate_key_for_different_order_is_collision() -> None:
    uow = FakeUnitOfWork()
    service = _service(uow)
    first_order = service.create_order(_order_request("client-1"), client_order_id="client-1")
    second_order = service.create_order(_order_request("client-2"), client_order_id="client-2")
    service.apply_risk_result(
        first_order.order_id,
        _risk_result(RiskDecision.REJECTED),
        external_event_id="risk-shared-1",
    )
    before_events = len(uow.order_events.events)

    result = service.apply_risk_result(
        second_order.order_id,
        _risk_result(RiskDecision.REJECTED),
        external_event_id="risk-shared-1",
    )

    assert result.status == EventApplicationStatus.EVENT_KEY_COLLISION
    assert result.order.order_id == second_order.order_id
    assert uow.orders.get_by_id(second_order.order_id).status == OrderStatus.CREATED  # type: ignore[union-attr]
    assert len(uow.order_events.events) == before_events


def test_apply_risk_result_accepted_illegal_transition_returns_typed_rejection() -> None:
    uow = FakeUnitOfWork()
    service = _service(uow)
    order = service.create_order(_order_request(), client_order_id="client-1")
    service.apply_risk_result(
        order.order_id,
        _risk_result(RiskDecision.REJECTED),
        external_event_id="risk-rejected-1",
    )
    before_events = len(uow.order_events.events)

    result = service.apply_risk_result(
        order.order_id,
        _risk_result(RiskDecision.ACCEPTED),
        external_event_id="risk-accepted-1",
    )

    assert result.status == EventApplicationStatus.MISMATCH_REJECTED
    assert result.order.status == OrderStatus.REJECTED_BY_RISK
    assert uow.orders.get_by_id(order.order_id).status == OrderStatus.REJECTED_BY_RISK  # type: ignore[union-attr]
    assert len(uow.order_events.events) == before_events
    assert "risk-accepted-1" not in [
        event.external_event_id for event in uow.order_events.events
    ]


def test_apply_risk_result_rejected_illegal_transition_returns_typed_rejection() -> None:
    uow = FakeUnitOfWork()
    service = _service(uow)
    order = service.create_order(_order_request(), client_order_id="client-1")
    service.apply_risk_result(
        order.order_id,
        _risk_result(RiskDecision.ACCEPTED),
        external_event_id="risk-accepted-1",
    )
    before_events = len(uow.order_events.events)

    result = service.apply_risk_result(
        order.order_id,
        _risk_result(RiskDecision.REJECTED),
        external_event_id="risk-rejected-1",
    )

    assert result.status == EventApplicationStatus.MISMATCH_REJECTED
    assert result.order.status == OrderStatus.RISK_ACCEPTED
    assert uow.orders.get_by_id(order.order_id).status == OrderStatus.RISK_ACCEPTED  # type: ignore[union-attr]
    assert len(uow.order_events.events) == before_events
    assert "risk-rejected-1" not in [
        event.external_event_id for event in uow.order_events.events
    ]


def test_apply_order_event_previous_status_match_updates_status_and_appends() -> None:
    uow = FakeUnitOfWork()
    service = _service(uow)
    order = service.create_order(_order_request(), client_order_id="client-1")
    service.apply_risk_result(
        order.order_id,
        _risk_result(RiskDecision.ACCEPTED),
        external_event_id="risk-accepted-1",
    )

    result = service.apply_order_event(
        _event(
            order.order_id,
            previous_status=OrderStatus.RISK_ACCEPTED,
            new_status=OrderStatus.SUBMITTING,
        )
    )

    assert result.status == EventApplicationStatus.APPLIED
    updated = result.order
    assert updated.status == OrderStatus.SUBMITTING
    assert updated.version == 3
    assert uow.orders.update_expected_versions[-1] == 2
    assert uow.order_events.events[-1].external_event_id == "exchange-event-1"


def test_apply_order_event_duplicate_does_not_apply_twice() -> None:
    uow = FakeUnitOfWork()
    service = _service(uow)
    order = service.create_order(_order_request(), client_order_id="client-1")
    service.apply_risk_result(
        order.order_id,
        _risk_result(RiskDecision.ACCEPTED),
        external_event_id="risk-accepted-1",
    )
    event = _event(
        order.order_id,
        previous_status=OrderStatus.RISK_ACCEPTED,
        new_status=OrderStatus.SUBMITTING,
    )
    first = service.apply_order_event(event)

    second = service.apply_order_event(event)

    assert first.status == EventApplicationStatus.APPLIED
    assert second.status == EventApplicationStatus.DUPLICATE
    assert second.order == first.order
    exchange_event_count = [
        item.external_event_id for item in uow.order_events.events
    ].count("exchange-event-1")
    assert exchange_event_count == 1


def test_apply_order_event_duplicate_key_for_different_order_is_collision() -> None:
    uow = FakeUnitOfWork()
    service = _service(uow)
    first_order = service.create_order(_order_request("client-1"), client_order_id="client-1")
    second_order = service.create_order(_order_request("client-2"), client_order_id="client-2")
    uow.order_events.append_event(
        _event(
            first_order.order_id,
            previous_status=OrderStatus.CREATED,
            new_status=OrderStatus.UNKNOWN,
            external_event_id="shared-exchange-event",
        )
    )
    before_events = len(uow.order_events.events)

    result = service.apply_order_event(
        _event(
            second_order.order_id,
            previous_status=OrderStatus.CREATED,
            new_status=OrderStatus.UNKNOWN,
            external_event_id="shared-exchange-event",
        )
    )

    assert result.status == EventApplicationStatus.EVENT_KEY_COLLISION
    assert result.order.order_id == second_order.order_id
    assert uow.orders.get_by_id(second_order.order_id).status == OrderStatus.CREATED  # type: ignore[union-attr]
    assert len(uow.order_events.events) == before_events


def test_apply_order_event_terminal_same_status_late_event_is_old_ignored() -> None:
    uow = FakeUnitOfWork()
    service = _service(uow)
    order = service.create_order(_order_request(), client_order_id="client-1")
    uow.orders.update_status(order.order_id, OrderStatus.FILLED)
    before_count = len(uow.order_events.events)

    result = service.apply_order_event(
        _event(
            order.order_id,
            previous_status=OrderStatus.ACKED,
            new_status=OrderStatus.FILLED,
        )
    )

    assert result.status == EventApplicationStatus.OLD_IGNORED
    current = result.order
    assert current.status == OrderStatus.FILLED
    assert len(uow.order_events.events) == before_count


def test_apply_order_event_terminal_conflicting_terminal_event_is_rejected() -> None:
    uow = FakeUnitOfWork()
    service = _service(uow)
    order = service.create_order(_order_request(), client_order_id="client-1")
    uow.orders.update_status(order.order_id, OrderStatus.CANCELED)
    before_count = len(uow.order_events.events)

    result = service.apply_order_event(
        _event(
            order.order_id,
            previous_status=OrderStatus.ACKED,
            new_status=OrderStatus.FILLED,
        )
    )

    assert result.status == EventApplicationStatus.MISMATCH_REJECTED
    assert result.order.status == OrderStatus.CANCELED
    assert uow.orders.get_by_id(order.order_id).status == OrderStatus.CANCELED  # type: ignore[union-attr]
    assert len(uow.order_events.events) == before_count


def test_apply_order_event_terminal_non_terminal_late_event_is_ignored() -> None:
    uow = FakeUnitOfWork()
    service = _service(uow)
    order = service.create_order(_order_request(), client_order_id="client-1")
    uow.orders.update_status(order.order_id, OrderStatus.FILLED)
    before_count = len(uow.order_events.events)

    result = service.apply_order_event(
        _event(
            order.order_id,
            previous_status=OrderStatus.ACKED,
            new_status=OrderStatus.PARTIALLY_FILLED,
        )
    )

    assert result.status == EventApplicationStatus.IGNORED_TERMINAL
    assert result.order.status == OrderStatus.FILLED
    assert uow.orders.get_by_id(order.order_id).status == OrderStatus.FILLED  # type: ignore[union-attr]
    assert len(uow.order_events.events) == before_count


def test_apply_order_event_non_terminal_old_process_event_is_ignored() -> None:
    uow = FakeUnitOfWork()
    service = _service(uow)
    order = service.create_order(_order_request(), client_order_id="client-1")
    uow.orders.update_status(order.order_id, OrderStatus.SUBMITTED)
    before_count = len(uow.order_events.events)

    result = service.apply_order_event(
        _event(
            order.order_id,
            previous_status=OrderStatus.RISK_ACCEPTED,
            new_status=OrderStatus.SUBMITTING,
        )
    )

    assert result.status == EventApplicationStatus.OLD_IGNORED
    assert result.order.status == OrderStatus.SUBMITTED
    assert uow.orders.get_by_id(order.order_id).status == OrderStatus.SUBMITTED  # type: ignore[union-attr]
    assert len(uow.order_events.events) == before_count


def test_apply_order_event_previous_status_mismatch_enters_unknown() -> None:
    uow = FakeUnitOfWork()
    service = _service(uow)
    order = service.create_order(_order_request(), client_order_id="client-1")

    result = service.apply_order_event(
        _event(
            order.order_id,
            previous_status=OrderStatus.ACKED,
            new_status=OrderStatus.FILLED,
        )
    )

    assert result.status == EventApplicationStatus.ENTERED_UNKNOWN
    unknown = result.order
    assert unknown.status == OrderStatus.UNKNOWN
    assert uow.order_events.events[-1].new_status == OrderStatus.UNKNOWN
    assert uow.order_events.events[-1].raw_payload["reason"] == (
        "previous_status_mismatch_unresolved"
    )


def test_apply_order_event_invalid_transition_returns_typed_rejection() -> None:
    uow = FakeUnitOfWork()
    service = _service(uow)
    order = service.create_order(_order_request(), client_order_id="client-1")
    before_count = len(uow.order_events.events)

    result = service.apply_order_event(
        _event(
            order.order_id,
            previous_status=OrderStatus.CREATED,
            new_status=OrderStatus.FILLED,
            external_event_id="invalid-created-to-filled",
        )
    )

    assert result.status == EventApplicationStatus.MISMATCH_REJECTED
    assert result.order.status == OrderStatus.CREATED
    assert len(uow.order_events.events) == before_count
    assert uow.orders.get_by_id(order.order_id).status == OrderStatus.CREATED  # type: ignore[union-attr]


def test_apply_order_event_missing_previous_status_enters_unknown() -> None:
    uow = FakeUnitOfWork()
    service = _service(uow)
    order = service.create_order(_order_request(), client_order_id="client-1")
    service.apply_risk_result(
        order.order_id,
        _risk_result(RiskDecision.ACCEPTED),
        external_event_id="risk-accepted-1",
    )

    result = service.apply_order_event(
        _event(
            order.order_id,
            previous_status=None,
            new_status=OrderStatus.SUBMITTING,
            external_event_id="missing-previous-status",
        )
    )

    assert result.status == EventApplicationStatus.ENTERED_UNKNOWN
    assert result.order.status == OrderStatus.UNKNOWN


@pytest.mark.parametrize(
    "forbidden_status",
    [OrderStatus.CANCEL_PENDING, OrderStatus.CANCEL_FAILED],
)
def test_unknown_cannot_recover_to_forbidden_process_states(
    forbidden_status: OrderStatus,
) -> None:
    uow = FakeUnitOfWork()
    service = _service(uow)
    order = service.create_order(_order_request(), client_order_id="client-1")
    uow.orders.update_status(order.order_id, OrderStatus.UNKNOWN)

    result = service.apply_order_event(
        _event(
            order.order_id,
            previous_status=OrderStatus.UNKNOWN,
            new_status=forbidden_status,
        )
    )

    assert result.status == EventApplicationStatus.MISMATCH_REJECTED
    current = result.order
    assert current.status == OrderStatus.UNKNOWN
    assert uow.orders.get_by_id(order.order_id).status == OrderStatus.UNKNOWN  # type: ignore[union-attr]


def test_unknown_can_recover_to_allowed_target_from_explicit_event() -> None:
    uow = FakeUnitOfWork()
    service = _service(uow)
    order = service.create_order(_order_request(), client_order_id="client-1")
    uow.orders.update_status(order.order_id, OrderStatus.UNKNOWN)

    result = service.apply_order_event(
        _event(
            order.order_id,
            previous_status=OrderStatus.UNKNOWN,
            new_status=OrderStatus.FILLED,
        )
    )

    assert result.status == EventApplicationStatus.RECOVERED_FROM_UNKNOWN
    recovered = result.order
    assert recovered.status == OrderStatus.FILLED
    assert uow.order_events.events[-1].previous_status == OrderStatus.UNKNOWN
    assert uow.order_events.events[-1].new_status == OrderStatus.FILLED


def test_unknown_requires_previous_status_unknown_for_explicit_recovery() -> None:
    uow = FakeUnitOfWork()
    service = _service(uow)
    order = service.create_order(_order_request(), client_order_id="client-1")
    uow.orders.update_status(order.order_id, OrderStatus.UNKNOWN)
    before_count = len(uow.order_events.events)

    result = service.apply_order_event(
        _event(
            order.order_id,
            previous_status=OrderStatus.ACKED,
            new_status=OrderStatus.FILLED,
        )
    )

    assert result.status == EventApplicationStatus.MISMATCH_REJECTED
    assert result.order.status == OrderStatus.UNKNOWN
    assert len(uow.order_events.events) == before_count


def test_raw_payload_is_not_source_of_truth_for_order_event_status() -> None:
    uow = FakeUnitOfWork()
    service = _service(uow)
    order = service.create_order(_order_request(), client_order_id="client-1")
    service.apply_risk_result(
        order.order_id,
        _risk_result(RiskDecision.ACCEPTED),
        external_event_id="risk-accepted-1",
    )
    event = _event(
        order.order_id,
        previous_status=OrderStatus.RISK_ACCEPTED,
        new_status=OrderStatus.SUBMITTING,
    )
    event = event.model_copy(
        update={"raw_payload": {"new_status": OrderStatus.FILLED.value}}
    )

    result = service.apply_order_event(event)

    assert result.status == EventApplicationStatus.APPLIED
    assert result.order.status == OrderStatus.SUBMITTING


def test_recover_order_consistent_event_stream_is_noop() -> None:
    uow = FakeUnitOfWork()
    service = _service(uow)
    order = service.create_order(_order_request(), client_order_id="client-1")
    before_count = len(uow.order_events.events)

    result = service.recover_order(order.order_id)

    assert result.status == EventApplicationStatus.APPLIED
    recovered = result.order
    assert recovered.status == OrderStatus.CREATED
    assert len(uow.order_events.events) == before_count


def test_recover_order_inconsistent_event_stream_enters_unknown() -> None:
    uow = FakeUnitOfWork()
    service = _service(uow)
    order = service.create_order(_order_request(), client_order_id="client-1")
    uow.order_events.events.clear()

    result = service.recover_order(order.order_id)

    assert result.status == EventApplicationStatus.ENTERED_UNKNOWN
    recovered = result.order
    assert recovered.status == OrderStatus.UNKNOWN
    assert uow.order_events.events[-1].new_status == OrderStatus.UNKNOWN
    assert uow.order_events.events[-1].raw_payload["reason"] == "replay_inconsistent"


def test_recover_order_unknown_recovers_to_replayed_allowed_status() -> None:
    uow = FakeUnitOfWork()
    service = _service(uow)
    order = service.create_order(_order_request(), client_order_id="client-1")
    uow.order_events.append_event(
        _event(
            order.order_id,
            previous_status=OrderStatus.CREATED,
            new_status=OrderStatus.UNKNOWN,
            external_event_id="unknown-diagnostic-1",
            event_source=EventSource.OMS,
        )
    )
    uow.order_events.append_event(
        _event(
            order.order_id,
            previous_status=OrderStatus.UNKNOWN,
            new_status=OrderStatus.FILLED,
            external_event_id="recovery-filled-1",
            event_source=EventSource.OMS,
        )
    )
    uow.orders.update_status(order.order_id, OrderStatus.UNKNOWN)

    result = service.recover_order(order.order_id)

    assert result.status == EventApplicationStatus.RECOVERED_FROM_UNKNOWN
    recovered = result.order
    assert recovered.status == OrderStatus.FILLED
    assert uow.order_events.events[-1].previous_status == OrderStatus.UNKNOWN
    assert uow.order_events.events[-1].new_status == OrderStatus.FILLED
    assert uow.order_events.events[-1].raw_payload["reason"] == "replay_recovered"


def test_recover_order_terminal_order_is_protected() -> None:
    uow = FakeUnitOfWork()
    service = _service(uow)
    order = service.create_order(_order_request(), client_order_id="client-1")
    uow.orders.update_status(order.order_id, OrderStatus.FILLED)
    before_count = len(uow.order_events.events)

    result = service.recover_order(order.order_id)

    assert result.status == EventApplicationStatus.IGNORED_TERMINAL
    recovered = result.order
    assert recovered.status == OrderStatus.FILLED
    assert len(uow.order_events.events) == before_count


def test_rollback_atomicity_when_order_event_append_fails_after_status_update() -> None:
    uow = FakeUnitOfWork()
    service = _service(uow)
    order = service.create_order(_order_request(), client_order_id="client-1")
    service.apply_risk_result(
        order.order_id,
        _risk_result(RiskDecision.ACCEPTED),
        external_event_id="risk-accepted-1",
    )
    uow.order_events.fail_next_append = True

    with pytest.raises(RuntimeError, match="append failed"):
        service.apply_order_event(
            _event(
                order.order_id,
                previous_status=OrderStatus.RISK_ACCEPTED,
                new_status=OrderStatus.SUBMITTING,
            )
        )

    assert uow.orders.get_by_id(order.order_id).status == OrderStatus.RISK_ACCEPTED  # type: ignore[union-attr]
    assert all(event.new_status != OrderStatus.SUBMITTING for event in uow.order_events.events)
    assert uow.rollback_count == 1


def test_optimistic_lock_failure_rolls_back_without_success_event() -> None:
    uow = FakeUnitOfWork()
    service = _service(uow)
    order = service.create_order(_order_request(), client_order_id="client-1")
    service.apply_risk_result(
        order.order_id,
        _risk_result(RiskDecision.ACCEPTED),
        external_event_id="risk-accepted-1",
    )
    uow.orders.force_stale_read = True

    with pytest.raises(OptimisticLockError):
        service.apply_order_event(
            _event(
                order.order_id,
                previous_status=OrderStatus.RISK_ACCEPTED,
                new_status=OrderStatus.SUBMITTING,
            )
        )

    assert uow.orders.orders_by_id[order.order_id].status == OrderStatus.RISK_ACCEPTED
    assert all(event.new_status != OrderStatus.SUBMITTING for event in uow.order_events.events)
    assert uow.rollback_count == 1


def test_service_does_not_use_external_engine_sentinels() -> None:
    class ForbiddenExternalEngine:
        def __getattr__(self, name: str) -> Any:
            raise AssertionError(f"external engine should not be used: {name}")

    del ForbiddenExternalEngine
    uow = FakeUnitOfWork()
    request = _order_request()

    order = _service(uow).create_order(request, client_order_id=request.client_order_id)

    assert order.status == OrderStatus.CREATED
