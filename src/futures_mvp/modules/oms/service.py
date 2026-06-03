from collections.abc import Callable, Sequence
from datetime import datetime

from futures_mvp.domain.enums import EventSource, OrderStatus, RiskDecision
from futures_mvp.domain.models import OrderEvent, OrderRequest, OrderState, RiskResult
from futures_mvp.interfaces.repositories import (
    EventAlreadyExistsError,
    OrderNotFoundError,
    UnitOfWork,
)
from futures_mvp.modules.oms.state_machine import (
    UNKNOWN_RECOVERY_TARGETS,
    can_transition,
    is_terminal,
    should_enter_unknown,
    validate_transition,
)

_STATUS_PRECEDENCE = {
    OrderStatus.CREATED: 0,
    OrderStatus.RISK_CHECKING: 1,
    OrderStatus.REJECTED_BY_RISK: 2,
    OrderStatus.RISK_ACCEPTED: 3,
    OrderStatus.SUBMITTING: 4,
    OrderStatus.SUBMIT_TIMEOUT: 5,
    OrderStatus.SUBMIT_FAILED: 6,
    OrderStatus.SUBMITTED: 7,
    OrderStatus.ACKED: 8,
    OrderStatus.PARTIALLY_FILLED: 9,
    OrderStatus.CANCEL_PENDING: 10,
    OrderStatus.CANCEL_FAILED: 11,
    OrderStatus.CANCELED: 12,
    OrderStatus.FILLED: 13,
    OrderStatus.REJECTED_BY_EXCHANGE: 14,
    OrderStatus.EXPIRED: 15,
    OrderStatus.UNKNOWN: 16,
}


class OMSService:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    def create_order(
        self,
        order_request: OrderRequest,
        *,
        client_order_id: str,
    ) -> OrderState:
        with self._uow_factory() as uow:
            existing = uow.orders.get_by_client_order_id(client_order_id)
            order = uow.orders.create_order(order_request, client_order_id=client_order_id)
            if existing is not None:
                return order

            initial_event_id = self._initial_event_id(order.order_id)
            if (
                uow.order_events.get_by_event_key(EventSource.OMS, initial_event_id)
                is not None
            ):
                return order

            try:
                uow.order_events.append_event(
                    self._event(
                        order_id=order.order_id,
                        previous_status=None,
                        new_status=OrderStatus.CREATED,
                        event_source=EventSource.OMS,
                        external_event_id=initial_event_id,
                        raw_payload={"reason": "order_created"},
                        occurred_at=self._clock(),
                    )
                )
            except EventAlreadyExistsError:
                return self._duplicate_after_rollback(
                    uow,
                    EventSource.OMS,
                    initial_event_id,
                )
            uow.commit()
            return order

    def apply_risk_result(
        self,
        order_id: str,
        risk_result: RiskResult,
        *,
        external_event_id: str,
        occurred_at: datetime | None = None,
    ) -> OrderState:
        with self._uow_factory() as uow:
            existing_event = uow.order_events.get_by_event_key(
                EventSource.RISK,
                external_event_id,
            )
            if existing_event is not None:
                return self._require_order(uow, existing_event.order_id)

            order = self._require_order(uow, order_id)
            event_time = occurred_at or self._clock()

            try:
                if risk_result.decision == RiskDecision.ACCEPTED:
                    return self._apply_risk_accepted(
                        uow,
                        order,
                        risk_result,
                        external_event_id,
                        event_time,
                    )
                if risk_result.decision == RiskDecision.REJECTED:
                    return self._apply_risk_rejected(
                        uow,
                        order,
                        risk_result,
                        external_event_id,
                        event_time,
                    )
            except EventAlreadyExistsError:
                return self._duplicate_after_rollback(
                    uow,
                    EventSource.RISK,
                    external_event_id,
                    fallback_external_event_ids=(f"{external_event_id}:risk_checking",),
                )
            raise ValueError(f"unsupported risk decision: {risk_result.decision}")

    def apply_order_event(self, event: OrderEvent) -> OrderState:
        with self._uow_factory() as uow:
            existing_event = uow.order_events.get_by_event_key(
                event.event_source,
                event.external_event_id,
            )
            if existing_event is not None:
                return self._require_order(uow, existing_event.order_id)

            order = self._require_order(uow, event.order_id)

            if order.status == OrderStatus.UNKNOWN:
                if self._is_unknown_recovery(order.status, event.new_status):
                    return self._apply_validated_event(uow, order, event)
                return order

            if event.previous_status == order.status:
                return self._apply_validated_event(uow, order, event)

            if self._is_obvious_old_event(order.status, event.new_status):
                return order

            if event.previous_status is None and self._is_unknown_recovery(
                order.status,
                event.new_status,
            ):
                return self._apply_validated_event(uow, order, event)

            return self._enter_unknown(
                uow,
                order,
                reason="previous_status_mismatch_unresolved",
                external_event_id=self._unknown_event_id(event),
                occurred_at=event.occurred_at,
                raw_payload={
                    "reason": "previous_status_mismatch_unresolved",
                    "event_source": event.event_source.value,
                    "external_event_id": event.external_event_id,
                    "previous_status": (
                        event.previous_status.value if event.previous_status else None
                    ),
                    "current_status": order.status.value,
                    "new_status": event.new_status.value,
                },
            )

    def recover_order(self, order_id: str) -> OrderState:
        with self._uow_factory() as uow:
            order = self._require_order(uow, order_id)
            if is_terminal(order.status):
                return order

            events = uow.order_events.list_by_order_id(order_id)
            replayed_status = self._replay_status(events)
            if replayed_status == order.status:
                return order
            if (
                order.status == OrderStatus.UNKNOWN
                and replayed_status in UNKNOWN_RECOVERY_TARGETS
            ):
                return self._recover_unknown(
                    uow,
                    order,
                    replayed_status,
                )
            if order.status == OrderStatus.UNKNOWN:
                return order

            return self._enter_unknown(
                uow,
                order,
                reason="replay_inconsistent",
                external_event_id=f"oms:recovery:unknown:{order.order_id}:{self._clock().isoformat()}",
                occurred_at=self._clock(),
                raw_payload={
                    "reason": "replay_inconsistent",
                    "order_id": order.order_id,
                    "current_status": order.status.value,
                    "replayed_status": replayed_status.value if replayed_status else None,
                },
            )

    def get_by_client_order_id(self, client_order_id: str) -> OrderState | None:
        with self._uow_factory() as uow:
            return uow.orders.get_by_client_order_id(client_order_id)

    def _apply_risk_accepted(
        self,
        uow: UnitOfWork,
        order: OrderState,
        risk_result: RiskResult,
        external_event_id: str,
        occurred_at: datetime,
    ) -> OrderState:
        current = order
        if current.status == OrderStatus.CREATED:
            validate_transition(OrderStatus.CREATED, OrderStatus.RISK_CHECKING)
            risk_checking_event_id = f"{external_event_id}:risk_checking"
            current = uow.orders.update_status(
                current.order_id,
                OrderStatus.RISK_CHECKING,
                expected_version=current.version,
            )
            uow.order_events.append_event(
                self._risk_event(
                    current,
                    previous_status=OrderStatus.CREATED,
                    new_status=OrderStatus.RISK_CHECKING,
                    risk_result=risk_result,
                    external_event_id=risk_checking_event_id,
                    occurred_at=occurred_at,
                )
            )

        validate_transition(current.status, OrderStatus.RISK_ACCEPTED)
        accepted = uow.orders.update_status(
            current.order_id,
            OrderStatus.RISK_ACCEPTED,
            expected_version=current.version,
        )
        uow.order_events.append_event(
            self._risk_event(
                accepted,
                previous_status=current.status,
                new_status=OrderStatus.RISK_ACCEPTED,
                risk_result=risk_result,
                external_event_id=external_event_id,
                occurred_at=occurred_at,
            )
        )
        uow.commit()
        return accepted

    def _apply_risk_rejected(
        self,
        uow: UnitOfWork,
        order: OrderState,
        risk_result: RiskResult,
        external_event_id: str,
        occurred_at: datetime,
    ) -> OrderState:
        validate_transition(order.status, OrderStatus.REJECTED_BY_RISK)
        rejected = uow.orders.update_status(
            order.order_id,
            OrderStatus.REJECTED_BY_RISK,
            expected_version=order.version,
        )
        uow.order_events.append_event(
            self._risk_event(
                rejected,
                previous_status=order.status,
                new_status=OrderStatus.REJECTED_BY_RISK,
                risk_result=risk_result,
                external_event_id=external_event_id,
                occurred_at=occurred_at,
            )
        )
        uow.commit()
        return rejected

    def _apply_validated_event(
        self,
        uow: UnitOfWork,
        order: OrderState,
        event: OrderEvent,
    ) -> OrderState:
        validate_transition(order.status, event.new_status)
        updated = uow.orders.update_status(
            order.order_id,
            event.new_status,
            expected_version=order.version,
        )
        try:
            uow.order_events.append_event(event)
        except EventAlreadyExistsError:
            return self._duplicate_after_rollback(
                uow,
                event.event_source,
                event.external_event_id,
            )
        uow.commit()
        return updated

    def _enter_unknown(
        self,
        uow: UnitOfWork,
        order: OrderState,
        *,
        reason: str,
        external_event_id: str,
        occurred_at: datetime,
        raw_payload: dict[str, object],
    ) -> OrderState:
        if order.status == OrderStatus.UNKNOWN:
            return order
        if not should_enter_unknown(reason, raw_payload):
            raise ValueError(f"unsupported UNKNOWN entry reason: {reason}")

        validate_transition(order.status, OrderStatus.UNKNOWN)
        existing = uow.order_events.get_by_event_key(EventSource.OMS, external_event_id)
        if existing is not None:
            return self._require_order(uow, existing.order_id)

        unknown = uow.orders.update_status(
            order.order_id,
            OrderStatus.UNKNOWN,
            expected_version=order.version,
        )
        try:
            uow.order_events.append_event(
                self._event(
                    order_id=order.order_id,
                    previous_status=order.status,
                    new_status=OrderStatus.UNKNOWN,
                    event_source=EventSource.OMS,
                    external_event_id=external_event_id,
                    raw_payload=raw_payload,
                    occurred_at=occurred_at,
                )
            )
        except EventAlreadyExistsError:
            return self._duplicate_after_rollback(
                uow,
                EventSource.OMS,
                external_event_id,
            )
        uow.commit()
        return unknown

    def _recover_unknown(
        self,
        uow: UnitOfWork,
        order: OrderState,
        recovered_status: OrderStatus,
    ) -> OrderState:
        validate_transition(OrderStatus.UNKNOWN, recovered_status)
        external_event_id = (
            f"oms:recovery:resolved:{order.order_id}:"
            f"{recovered_status.value}:{self._clock().isoformat()}"
        )
        recovered = uow.orders.update_status(
            order.order_id,
            recovered_status,
            expected_version=order.version,
        )
        try:
            uow.order_events.append_event(
                self._event(
                    order_id=order.order_id,
                    previous_status=OrderStatus.UNKNOWN,
                    new_status=recovered_status,
                    event_source=EventSource.OMS,
                    external_event_id=external_event_id,
                    raw_payload={
                        "reason": "replay_recovered",
                        "order_id": order.order_id,
                        "recovered_status": recovered_status.value,
                    },
                    occurred_at=self._clock(),
                )
            )
        except EventAlreadyExistsError:
            return self._duplicate_after_rollback(
                uow,
                EventSource.OMS,
                external_event_id,
            )
        uow.commit()
        return recovered

    def _duplicate_after_rollback(
        self,
        uow: UnitOfWork,
        event_source: EventSource,
        external_event_id: str,
        *,
        fallback_external_event_ids: Sequence[str] = (),
    ) -> OrderState:
        uow.rollback()
        for candidate_event_id in (external_event_id, *fallback_external_event_ids):
            existing_event = uow.order_events.get_by_event_key(
                event_source,
                candidate_event_id,
            )
            if existing_event is not None:
                return self._require_order(uow, existing_event.order_id)
        raise EventAlreadyExistsError(
            f"order event already exists but cannot be loaded: "
            f"{event_source}/{external_event_id}"
        )

    def _replay_status(self, events: Sequence[OrderEvent]) -> OrderStatus | None:
        if not events:
            return None

        first = events[0]
        if first.previous_status is not None or first.new_status != OrderStatus.CREATED:
            return None

        current = OrderStatus.CREATED
        for event in events[1:]:
            if event.previous_status != current:
                return None
            if not can_transition(current, event.new_status):
                return None
            current = event.new_status
        return current

    def _require_order(self, uow: UnitOfWork, order_id: str) -> OrderState:
        order = uow.orders.get_by_id(order_id)
        if order is None:
            raise OrderNotFoundError(f"order not found: {order_id}")
        return order

    def _risk_event(
        self,
        order: OrderState,
        *,
        previous_status: OrderStatus,
        new_status: OrderStatus,
        risk_result: RiskResult,
        external_event_id: str,
        occurred_at: datetime,
    ) -> OrderEvent:
        return self._event(
            order_id=order.order_id,
            previous_status=previous_status,
            new_status=new_status,
            event_source=EventSource.RISK,
            external_event_id=external_event_id,
            raw_payload={
                "decision": risk_result.decision.value,
                "rule_name": risk_result.rule_name,
                "reason": risk_result.reason,
            },
            occurred_at=occurred_at,
        )

    def _event(
        self,
        *,
        order_id: str,
        previous_status: OrderStatus | None,
        new_status: OrderStatus,
        event_source: EventSource,
        external_event_id: str,
        raw_payload: dict[str, object],
        occurred_at: datetime,
    ) -> OrderEvent:
        return OrderEvent(
            order_id=order_id,
            previous_status=previous_status,
            new_status=new_status,
            event_source=event_source,
            external_event_id=external_event_id,
            raw_payload=raw_payload,
            occurred_at=occurred_at,
        )

    def _initial_event_id(self, order_id: str) -> str:
        return f"oms:create:{order_id}"

    def _unknown_event_id(self, event: OrderEvent) -> str:
        return f"oms:unknown:{event.event_source.value}:{event.external_event_id}"

    def _is_obvious_old_event(
        self,
        current_status: OrderStatus,
        event_status: OrderStatus,
    ) -> bool:
        if is_terminal(current_status):
            return current_status != event_status
        return _STATUS_PRECEDENCE[current_status] > _STATUS_PRECEDENCE[event_status]

    def _is_unknown_recovery(
        self,
        current_status: OrderStatus,
        event_status: OrderStatus,
    ) -> bool:
        return current_status == OrderStatus.UNKNOWN and event_status in UNKNOWN_RECOVERY_TARGETS
