from collections.abc import Mapping

from futures_mvp.domain.enums import OrderStatus
from futures_mvp.modules.oms.errors import InvalidOrderTransition

TERMINAL_STATUSES = frozenset(
    {
        OrderStatus.REJECTED_BY_RISK,
        OrderStatus.SUBMIT_FAILED,
        OrderStatus.CANCELED,
        OrderStatus.FILLED,
        OrderStatus.REJECTED_BY_EXCHANGE,
        OrderStatus.EXPIRED,
    }
)

RECOVERABLE_STATUSES = frozenset(
    {
        OrderStatus.SUBMITTING,
        OrderStatus.SUBMIT_TIMEOUT,
        OrderStatus.SUBMITTED,
        OrderStatus.CANCEL_PENDING,
        OrderStatus.CANCEL_FAILED,
        OrderStatus.UNKNOWN,
    }
)

UNKNOWN_RECOVERY_TARGETS = frozenset(
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

UNKNOWN_ENTRY_REASONS = frozenset(
    {
        "unclassified_exchange_report",
        "contradictory_report",
        "incomplete_report_after_submit_timeout",
        "replay_inconsistent",
        "previous_status_mismatch_unresolved",
        "event_sequence_gap",
    }
)

ALLOWED_TRANSITIONS: Mapping[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.CREATED: frozenset(
        {
            OrderStatus.RISK_CHECKING,
            OrderStatus.REJECTED_BY_RISK,
            OrderStatus.UNKNOWN,
        }
    ),
    OrderStatus.RISK_CHECKING: frozenset(
        {
            OrderStatus.RISK_ACCEPTED,
            OrderStatus.REJECTED_BY_RISK,
            OrderStatus.UNKNOWN,
        }
    ),
    OrderStatus.REJECTED_BY_RISK: frozenset(),
    OrderStatus.RISK_ACCEPTED: frozenset(
        {
            OrderStatus.SUBMITTING,
            OrderStatus.SUBMIT_FAILED,
            OrderStatus.UNKNOWN,
        }
    ),
    OrderStatus.SUBMITTING: frozenset(
        {
            OrderStatus.SUBMITTED,
            OrderStatus.ACKED,
            OrderStatus.SUBMIT_TIMEOUT,
            OrderStatus.SUBMIT_FAILED,
            OrderStatus.REJECTED_BY_EXCHANGE,
            OrderStatus.UNKNOWN,
        }
    ),
    OrderStatus.SUBMIT_TIMEOUT: frozenset(
        {
            OrderStatus.SUBMITTED,
            OrderStatus.ACKED,
            OrderStatus.REJECTED_BY_EXCHANGE,
            OrderStatus.SUBMIT_FAILED,
            OrderStatus.UNKNOWN,
        }
    ),
    OrderStatus.SUBMIT_FAILED: frozenset(),
    OrderStatus.SUBMITTED: frozenset(
        {
            OrderStatus.ACKED,
            OrderStatus.REJECTED_BY_EXCHANGE,
            OrderStatus.CANCEL_PENDING,
            OrderStatus.EXPIRED,
            OrderStatus.UNKNOWN,
        }
    ),
    OrderStatus.ACKED: frozenset(
        {
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.CANCEL_PENDING,
            OrderStatus.CANCELED,
            OrderStatus.EXPIRED,
            OrderStatus.UNKNOWN,
        }
    ),
    OrderStatus.PARTIALLY_FILLED: frozenset(
        {
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.CANCEL_PENDING,
            OrderStatus.CANCELED,
            OrderStatus.EXPIRED,
            OrderStatus.UNKNOWN,
        }
    ),
    OrderStatus.CANCEL_PENDING: frozenset(
        {
            OrderStatus.CANCELED,
            OrderStatus.CANCEL_FAILED,
            OrderStatus.FILLED,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.UNKNOWN,
        }
    ),
    OrderStatus.CANCEL_FAILED: frozenset(
        {
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.CANCEL_PENDING,
            OrderStatus.CANCELED,
            OrderStatus.EXPIRED,
            OrderStatus.UNKNOWN,
        }
    ),
    OrderStatus.CANCELED: frozenset(),
    OrderStatus.FILLED: frozenset(),
    OrderStatus.REJECTED_BY_EXCHANGE: frozenset(),
    OrderStatus.EXPIRED: frozenset(),
    OrderStatus.UNKNOWN: UNKNOWN_RECOVERY_TARGETS,
}


def _assert_status_covered(status: OrderStatus) -> None:
    if status not in ALLOWED_TRANSITIONS:
        raise KeyError(f"missing transition table entry for {status.value}")


def can_transition(from_status: OrderStatus, to_status: OrderStatus) -> bool:
    _assert_status_covered(from_status)
    return to_status in ALLOWED_TRANSITIONS[from_status]


def validate_transition(from_status: OrderStatus, to_status: OrderStatus) -> None:
    if not can_transition(from_status, to_status):
        raise InvalidOrderTransition(from_status, to_status)


def is_terminal(status: OrderStatus) -> bool:
    return status in TERMINAL_STATUSES


def is_recoverable(status: OrderStatus) -> bool:
    return status in RECOVERABLE_STATUSES


def should_enter_unknown(
    reason: str,
    context: Mapping[str, object] | None = None,
) -> bool:
    _ = context
    return reason in UNKNOWN_ENTRY_REASONS
