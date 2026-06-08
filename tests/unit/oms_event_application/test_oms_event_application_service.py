from datetime import UTC, datetime, timedelta
from decimal import Decimal

from futures_mvp.domain.enums import (
    Direction,
    EventApplicationStatus,
    EventSource,
    ExecutionReportStatus,
    Offset,
    OMSEventApplyResultStatus,
    OrderStatus,
    OrderType,
)
from futures_mvp.domain.models import (
    NormalizedExecutionReport,
    OMSEventApplyContext,
    OrderEvent,
    OrderEventApplicationResult,
    OrderEventCandidate,
    OrderRequest,
    OrderState,
)
from futures_mvp.modules.oms_event_application import (
    OMSEventApplicationService,
    build_application_candidate,
    build_oms_order_event_id,
    canonical_order_event_payload,
    map_candidate_to_order_event,
    replay_oms_order_events,
)

NOW = datetime(2026, 6, 8, 9, tzinfo=UTC)


class FakeOMSOrderEventApplier:
    def __init__(
        self,
        status: EventApplicationStatus = EventApplicationStatus.APPLIED,
        reason: str | None = None,
    ) -> None:
        self.status = status
        self.reason = reason
        self.applied_events: list[OrderEvent] = []
        self.existing_events: dict[tuple[EventSource, str], OrderEvent] = {}

    def apply_order_event(self, event: OrderEvent) -> OrderEventApplicationResult:
        self.applied_events.append(event)
        self.existing_events[(event.event_source, event.external_event_id)] = event
        return OrderEventApplicationResult(
            status=self.status,
            order=_order(status=event.new_status),
            reason=self.reason,
        )

    def get_by_event_key(
        self,
        event_source: EventSource,
        external_event_id: str,
    ) -> OrderEvent | None:
        return self.existing_events.get((event_source, external_event_id))

    def add_existing_event(self, event: OrderEvent) -> None:
        self.existing_events[(event.event_source, event.external_event_id)] = event


def _order(*, order_id: str = "order-1", status: OrderStatus = OrderStatus.SUBMITTED) -> OrderState:
    return OrderState(
        order_id=order_id,
        request=OrderRequest(
            client_order_id="client-1",
            account_id="acct-1",
            instrument_id="IF2606",
            exchange="CFFEX",
            direction=Direction.BUY,
            offset=Offset.OPEN,
            order_type=OrderType.LIMIT,
            limit_price=Decimal("500"),
            quantity=Decimal("2"),
        ),
        status=status,
    )


def _candidate(
    *,
    execution_status: ExecutionReportStatus = ExecutionReportStatus.ACKED,
    order_id: str = "order-1",
    report_id: str = "er-1",
    occurred_at: datetime = NOW,
    cumulative_filled_qty: Decimal = Decimal("0"),
    filled_qty: Decimal = Decimal("0"),
    fill_price: Decimal | None = None,
) -> OrderEventCandidate:
    status_map = {
        ExecutionReportStatus.SUBMITTED: OrderStatus.SUBMITTED,
        ExecutionReportStatus.ACKED: OrderStatus.ACKED,
        ExecutionReportStatus.PARTIALLY_FILLED: OrderStatus.PARTIALLY_FILLED,
        ExecutionReportStatus.FILLED: OrderStatus.FILLED,
        ExecutionReportStatus.REJECTED: OrderStatus.REJECTED_BY_EXCHANGE,
        ExecutionReportStatus.CANCELED: OrderStatus.CANCELED,
        ExecutionReportStatus.ERROR: OrderStatus.UNKNOWN,
    }
    return OrderEventCandidate(
        normalized_report_id=report_id,
        order_id=order_id,
        new_status=status_map[execution_status],
        event_source=EventSource.EXECUTION_REPORT_NORMALIZER,
        external_event_id=report_id,
        occurred_at=occurred_at,
        execution_status=execution_status,
        command_id="command-1",
        client_order_id="client-1",
        adapter_order_ref="adapter-order-1",
        exchange_order_id="exchange-order-1",
        filled_qty=filled_qty,
        fill_price=fill_price,
        cumulative_filled_qty=cumulative_filled_qty,
    )


def _context(
    candidate: OrderEventCandidate,
    *,
    order: OrderState | None = None,
    allow_live_apply: bool = False,
) -> OMSEventApplyContext:
    return OMSEventApplyContext(
        order_event_candidate=candidate,
        current_order_state=order or _order(order_id=candidate.order_id),
        allow_live_apply=allow_live_apply,
    )


def _normalized(**updates: object) -> NormalizedExecutionReport:
    values = {
        "report_id": "er-1",
        "raw_report_id": "raw-1",
        "adapter_name": "mock",
        "execution_target": "MOCK",
        "command_id": "command-1",
        "order_id": "order-1",
        "client_order_id": "client-1",
        "adapter_order_ref": "adapter-order-1",
        "exchange_order_id": "exchange-order-1",
        "execution_status": ExecutionReportStatus.PARTIALLY_FILLED,
        "filled_qty": Decimal("1"),
        "fill_price": Decimal("500"),
        "cumulative_filled_qty": Decimal("1"),
        "remaining_qty": Decimal("1"),
        "report_ts": NOW,
        "normalized_at": NOW + timedelta(seconds=1),
        "reason": None,
        "source_report_hash": "hash-1",
    }
    values.update(updates)
    return NormalizedExecutionReport(**values)


def test_deterministic_event_id_from_candidate_lineage() -> None:
    candidate = _candidate()
    same = candidate.model_copy(update={"raw_payload": {"diagnostic": "changed"}})
    changed = candidate.model_copy(update={"cumulative_filled_qty": Decimal("1")})

    assert build_oms_order_event_id(candidate).startswith("oe_")
    assert build_oms_order_event_id(candidate) == build_oms_order_event_id(same)
    assert build_oms_order_event_id(candidate) != build_oms_order_event_id(changed)


def test_deterministic_event_id_changes_for_each_identity_field() -> None:
    candidate = _candidate()
    baseline = build_oms_order_event_id(candidate)
    changes = [
        {"normalized_report_id": "er-2"},
        {"order_id": "order-2"},
        {
            "execution_status": ExecutionReportStatus.REJECTED,
            "new_status": OrderStatus.REJECTED_BY_EXCHANGE,
        },
        {"cumulative_filled_qty": Decimal("1")},
        {"occurred_at": NOW + timedelta(seconds=1)},
    ]

    for change in changes:
        assert build_oms_order_event_id(candidate.model_copy(update=change)) != baseline


def test_candidate_to_order_event_mapping_all_mappable_statuses() -> None:
    expected = {
        ExecutionReportStatus.ACKED: OrderStatus.ACKED,
        ExecutionReportStatus.PARTIALLY_FILLED: OrderStatus.PARTIALLY_FILLED,
        ExecutionReportStatus.FILLED: OrderStatus.FILLED,
        ExecutionReportStatus.REJECTED: OrderStatus.REJECTED_BY_EXCHANGE,
        ExecutionReportStatus.CANCELED: OrderStatus.CANCELED,
    }
    for execution_status, order_status in expected.items():
        fill_price = (
            Decimal("500")
            if execution_status
            in {ExecutionReportStatus.PARTIALLY_FILLED, ExecutionReportStatus.FILLED}
            else None
        )
        candidate = _candidate(
            execution_status=execution_status,
            filled_qty=Decimal("1") if fill_price else Decimal("0"),
            fill_price=fill_price,
            cumulative_filled_qty=Decimal("1") if fill_price else Decimal("0"),
        )

        event = map_candidate_to_order_event(candidate, _order())

        assert event.new_status is order_status
        assert event.previous_status is OrderStatus.SUBMITTED
        assert event.event_source is EventSource.EXECUTION_REPORT_NORMALIZER
        assert event.external_event_id == build_oms_order_event_id(candidate)


def test_order_event_payload_contains_lineage_and_no_trade_or_accounting_facts() -> None:
    candidate = _candidate(
        execution_status=ExecutionReportStatus.PARTIALLY_FILLED,
        filled_qty=Decimal("1"),
        fill_price=Decimal("500"),
        cumulative_filled_qty=Decimal("1"),
    )
    event = map_candidate_to_order_event(candidate, _order())

    assert event.raw_payload["report_id"] == candidate.normalized_report_id
    assert event.raw_payload["command_id"] == "command-1"
    assert event.raw_payload["client_order_id"] == "client-1"
    assert event.raw_payload["adapter_order_ref"] == "adapter-order-1"
    assert event.raw_payload["exchange_order_id"] == "exchange-order-1"
    assert event.raw_payload["filled_qty"] == "1"
    assert event.raw_payload["fill_price"] == "500"
    assert "trade_id" not in event.raw_payload
    assert "position" not in event.raw_payload
    assert "accounting" not in event.raw_payload


def test_submitted_and_error_candidates_do_not_call_oms() -> None:
    applier = FakeOMSOrderEventApplier()
    service = OMSEventApplicationService(applier)

    submitted = service.apply_candidate(
        _context(_candidate(execution_status=ExecutionReportStatus.SUBMITTED))
    )
    error = service.apply_candidate(
        _context(_candidate(execution_status=ExecutionReportStatus.ERROR))
    )

    assert submitted.status is OMSEventApplyResultStatus.NO_OP
    assert submitted.reason == "submitted_report_no_oms_event"
    assert error.status is OMSEventApplyResultStatus.REJECTED_NO_EVENT
    assert error.reason == "error_report_no_oms_event"
    assert applier.applied_events == []


def test_dry_run_returns_preview_and_does_not_call_oms() -> None:
    applier = FakeOMSOrderEventApplier()
    service = OMSEventApplicationService(applier, event_lookup=applier)

    result = service.apply_candidate(_context(_candidate()))

    assert result.status is OMSEventApplyResultStatus.DRY_RUN
    assert result.dry_run is True
    assert result.order_event is not None
    assert result.event_id == result.order_event.external_event_id
    assert applier.applied_events == []


def test_live_apply_calls_oms_applier_once() -> None:
    applier = FakeOMSOrderEventApplier()
    service = OMSEventApplicationService(applier, event_lookup=applier)

    result = service.apply_candidate(_context(_candidate(), allow_live_apply=True))

    assert result.status is OMSEventApplyResultStatus.APPLIED
    assert result.order_state is not None
    assert len(applier.applied_events) == 1


def test_live_apply_existing_same_canonical_returns_duplicate_without_oms_call() -> None:
    applier = FakeOMSOrderEventApplier()
    service = OMSEventApplicationService(applier, event_lookup=applier)
    candidate = _candidate()
    existing = map_candidate_to_order_event(candidate, _order())
    applier.add_existing_event(existing)

    result = service.apply_candidate(_context(candidate, allow_live_apply=True))

    assert result.status is OMSEventApplyResultStatus.DUPLICATE
    assert result.reason == "order_event_duplicate"
    assert applier.applied_events == []


def test_live_apply_existing_different_canonical_returns_conflict_without_oms_call() -> None:
    applier = FakeOMSOrderEventApplier()
    service = OMSEventApplicationService(applier, event_lookup=applier)
    candidate = _candidate(
        execution_status=ExecutionReportStatus.PARTIALLY_FILLED,
        filled_qty=Decimal("1"),
        fill_price=Decimal("500"),
        cumulative_filled_qty=Decimal("1"),
    )
    existing = map_candidate_to_order_event(candidate, _order()).model_copy(
        update={"fill_price": Decimal("501")}
    )
    applier.add_existing_event(existing)

    result = service.apply_candidate(_context(candidate, allow_live_apply=True))

    assert result.status is OMSEventApplyResultStatus.CONFLICT
    assert result.reason == "order_event_canonical_conflict"
    assert applier.applied_events == []


def test_dry_run_existing_different_canonical_returns_conflict_without_oms_call() -> None:
    applier = FakeOMSOrderEventApplier()
    service = OMSEventApplicationService(applier, event_lookup=applier)
    candidate = _candidate(
        execution_status=ExecutionReportStatus.PARTIALLY_FILLED,
        filled_qty=Decimal("1"),
        fill_price=Decimal("500"),
        cumulative_filled_qty=Decimal("1"),
    )
    existing = map_candidate_to_order_event(candidate, _order()).model_copy(
        update={"filled_qty": Decimal("2")}
    )
    applier.add_existing_event(existing)

    result = service.apply_candidate(_context(candidate))

    assert result.status is OMSEventApplyResultStatus.CONFLICT
    assert result.dry_run is True
    assert applier.applied_events == []


def test_candidate_order_mismatch_rejects_without_oms_call() -> None:
    applier = FakeOMSOrderEventApplier()
    service = OMSEventApplicationService(applier)
    context = _context(_candidate(order_id="order-1"), order=_order(order_id="order-2"))

    result = service.apply_candidate(context)

    assert result.status is OMSEventApplyResultStatus.REJECTED_INVALID_CANDIDATE
    assert result.reason == "candidate_order_id_mismatch"
    assert applier.applied_events == []


def test_duplicate_and_conflict_are_propagated_as_typed_results() -> None:
    duplicate_service = OMSEventApplicationService(
        FakeOMSOrderEventApplier(EventApplicationStatus.DUPLICATE),
        event_lookup=FakeOMSOrderEventApplier(),
    )
    conflict_service = OMSEventApplicationService(
        FakeOMSOrderEventApplier(EventApplicationStatus.EVENT_KEY_COLLISION),
        event_lookup=FakeOMSOrderEventApplier(),
    )

    duplicate = duplicate_service.apply_candidate(_context(_candidate(), allow_live_apply=True))
    conflict = conflict_service.apply_candidate(_context(_candidate(), allow_live_apply=True))

    assert duplicate.status is OMSEventApplyResultStatus.DUPLICATE
    assert conflict.status is OMSEventApplyResultStatus.CONFLICT


def test_terminal_protection_is_delegated_to_oms_result() -> None:
    applier = FakeOMSOrderEventApplier(
        EventApplicationStatus.IGNORED_TERMINAL,
        reason="terminal order cannot be changed",
    )
    service = OMSEventApplicationService(applier, event_lookup=applier)

    result = service.apply_candidate(
        _context(_candidate(), order=_order(status=OrderStatus.FILLED), allow_live_apply=True)
    )

    assert result.status is OMSEventApplyResultStatus.ERROR
    assert result.reason == "terminal order cannot be changed"
    assert len(applier.applied_events) == 1


def test_build_application_candidate_from_normalized_report() -> None:
    candidate = build_application_candidate(_normalized())

    assert candidate.normalized_report_id == "er-1"
    assert candidate.execution_status is ExecutionReportStatus.PARTIALLY_FILLED
    assert candidate.new_status is OrderStatus.PARTIALLY_FILLED
    assert candidate.cumulative_filled_qty == Decimal("1")


def test_canonical_order_event_excludes_diagnostics() -> None:
    candidate = _candidate()
    event = map_candidate_to_order_event(candidate, _order())
    changed = event.model_copy(update={"raw_payload": {**event.raw_payload, "other": "ignored"}})

    assert canonical_order_event_payload(event) == canonical_order_event_payload(changed)


def test_replay_defaults_to_dry_run_and_detects_conflict_without_oms_call() -> None:
    applier = FakeOMSOrderEventApplier()
    service = OMSEventApplicationService(applier, event_lookup=applier)
    candidate = _candidate()
    changed_previous_status_context = _context(
        candidate,
        order=_order(status=OrderStatus.ACKED),
    )

    results = replay_oms_order_events(
        [_context(candidate), changed_previous_status_context],
        service=service,
    )

    assert [result.status for result in results] == [
        OMSEventApplyResultStatus.DRY_RUN,
        OMSEventApplyResultStatus.CONFLICT,
    ]
    assert results[1].reason == "order_event_canonical_conflict"
    assert applier.applied_events == []


def test_live_replay_batch_conflict_returns_conflict_before_any_oms_call() -> None:
    applier = FakeOMSOrderEventApplier()
    service = OMSEventApplicationService(applier, event_lookup=applier)
    candidate = _candidate()
    changed_previous_status_context = _context(
        candidate,
        order=_order(status=OrderStatus.ACKED),
        allow_live_apply=True,
    )

    results = replay_oms_order_events(
        [_context(candidate, allow_live_apply=True), changed_previous_status_context],
        service=service,
        allow_live_apply=True,
    )

    assert [result.status for result in results] == [
        OMSEventApplyResultStatus.DRY_RUN,
        OMSEventApplyResultStatus.CONFLICT,
    ]
    assert applier.applied_events == []


def test_live_replay_requires_explicit_flag() -> None:
    applier = FakeOMSOrderEventApplier()
    service = OMSEventApplicationService(applier, event_lookup=applier)

    results = replay_oms_order_events(
        [
            _context(_candidate(report_id="er-1", occurred_at=NOW)),
            _context(_candidate(report_id="er-2", occurred_at=NOW + timedelta(seconds=1))),
        ],
        service=service,
        allow_live_apply=True,
    )

    assert [result.status for result in results] == [
        OMSEventApplyResultStatus.APPLIED,
        OMSEventApplyResultStatus.APPLIED,
    ]
    assert [event.report_id for event in applier.applied_events] == ["er-1", "er-2"]
