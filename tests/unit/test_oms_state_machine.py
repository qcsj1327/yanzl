import pytest

from futures_mvp.domain.enums import OrderStatus
from futures_mvp.modules.oms.errors import InvalidOrderTransition
from futures_mvp.modules.oms.state_machine import (
    ALLOWED_TRANSITIONS,
    RECOVERABLE_STATUSES,
    TERMINAL_STATUSES,
    UNKNOWN_ENTRY_REASONS,
    UNKNOWN_RECOVERY_TARGETS,
    can_transition,
    is_recoverable,
    is_terminal,
    should_enter_unknown,
    validate_transition,
)


def test_allowed_transitions_explicitly_cover_all_order_statuses() -> None:
    assert set(ALLOWED_TRANSITIONS) == set(OrderStatus)


def test_all_allowed_transitions_validate_successfully() -> None:
    for from_status, next_statuses in ALLOWED_TRANSITIONS.items():
        for to_status in next_statuses:
            assert can_transition(from_status, to_status) is True
            validate_transition(from_status, to_status)


@pytest.mark.parametrize(
    ("from_status", "to_status"),
    [
        (OrderStatus.REJECTED_BY_RISK, OrderStatus.SUBMITTING),
        (OrderStatus.SUBMIT_FAILED, OrderStatus.SUBMITTED),
        (OrderStatus.CANCELED, OrderStatus.FILLED),
        (OrderStatus.FILLED, OrderStatus.CANCELED),
        (OrderStatus.REJECTED_BY_EXCHANGE, OrderStatus.ACKED),
        (OrderStatus.EXPIRED, OrderStatus.PARTIALLY_FILLED),
        (OrderStatus.CREATED, OrderStatus.FILLED),
    ],
)
def test_invalid_transitions_raise_clear_error(
    from_status: OrderStatus,
    to_status: OrderStatus,
) -> None:
    assert can_transition(from_status, to_status) is False

    with pytest.raises(InvalidOrderTransition) as exc_info:
        validate_transition(from_status, to_status)

    message = str(exc_info.value)
    assert from_status.value in message
    assert to_status.value in message


def test_terminal_statuses_have_no_allowed_next_states() -> None:
    for status in TERMINAL_STATUSES:
        assert ALLOWED_TRANSITIONS[status] == frozenset()
        assert is_terminal(status) is True


def test_terminal_statuses_match_empty_transition_states() -> None:
    empty_transition_statuses = {
        status for status, next_statuses in ALLOWED_TRANSITIONS.items() if not next_statuses
    }

    assert TERMINAL_STATUSES == empty_transition_statuses


def test_recoverable_statuses_are_not_terminal() -> None:
    for status in RECOVERABLE_STATUSES:
        assert is_recoverable(status) is True
        assert is_terminal(status) is False

    for status in TERMINAL_STATUSES:
        assert is_recoverable(status) is False


def test_unknown_recovery_targets_match_phase_2_1_constraint() -> None:
    assert UNKNOWN_RECOVERY_TARGETS == frozenset(
        {
            OrderStatus.SUBMITTED,
            OrderStatus.ACKED,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.CANCELED,
            OrderStatus.FILLED,
            OrderStatus.REJECTED_BY_EXCHANGE,
            OrderStatus.EXPIRED,
        }
    )
    assert ALLOWED_TRANSITIONS[OrderStatus.UNKNOWN] == UNKNOWN_RECOVERY_TARGETS


@pytest.mark.parametrize(
    "to_status",
    [
        OrderStatus.SUBMITTED,
        OrderStatus.ACKED,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.CANCELED,
        OrderStatus.FILLED,
        OrderStatus.REJECTED_BY_EXCHANGE,
        OrderStatus.EXPIRED,
    ],
)
def test_unknown_can_only_recover_to_allowed_verified_states(to_status: OrderStatus) -> None:
    assert can_transition(OrderStatus.UNKNOWN, to_status) is True
    validate_transition(OrderStatus.UNKNOWN, to_status)


@pytest.mark.parametrize(
    "to_status",
    [
        OrderStatus.CREATED,
        OrderStatus.RISK_CHECKING,
        OrderStatus.REJECTED_BY_RISK,
        OrderStatus.RISK_ACCEPTED,
        OrderStatus.SUBMITTING,
        OrderStatus.SUBMIT_TIMEOUT,
        OrderStatus.SUBMIT_FAILED,
        OrderStatus.CANCEL_PENDING,
        OrderStatus.CANCEL_FAILED,
        OrderStatus.UNKNOWN,
    ],
)
def test_unknown_cannot_transition_to_forbidden_targets(to_status: OrderStatus) -> None:
    assert can_transition(OrderStatus.UNKNOWN, to_status) is False

    with pytest.raises(InvalidOrderTransition):
        validate_transition(OrderStatus.UNKNOWN, to_status)


def test_should_enter_unknown_for_known_reasons_only() -> None:
    for reason in UNKNOWN_ENTRY_REASONS:
        assert should_enter_unknown(reason) is True

    assert should_enter_unknown("unexpected_test_reason") is False
    assert should_enter_unknown("unexpected_test_reason", {"ignored": True}) is False
