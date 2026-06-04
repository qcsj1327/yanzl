from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from futures_mvp.domain.enums import Direction, EventSource, Offset, OrderStatus
from futures_mvp.domain.models import FillEvent, OrderEvent, Trade


class ExchangeReportType(StrEnum):
    ACK = "ACK"
    REJECTED = "REJECTED"
    PARTIAL_FILL = "PARTIAL_FILL"
    FULL_FILL = "FULL_FILL"
    CANCELED = "CANCELED"
    CANCEL_REJECTED = "CANCEL_REJECTED"
    EXPIRED = "EXPIRED"
    TIMEOUT = "TIMEOUT"
    EXCHANGE_UNAVAILABLE = "EXCHANGE_UNAVAILABLE"
    UNKNOWN_REPORT = "UNKNOWN_REPORT"


class ExecutionOperation(StrEnum):
    SUBMIT = "SUBMIT"
    CANCEL = "CANCEL"


class DeliveryPhase(StrEnum):
    PRE_SEND = "PRE_SEND"
    POST_SEND_UNCERTAIN = "POST_SEND_UNCERTAIN"


class MappingResultStatus(StrEnum):
    MAPPED_ORDER_EVENT = "MAPPED_ORDER_EVENT"
    DUPLICATE_REPORT = "DUPLICATE_REPORT"
    IGNORED_REPORT = "IGNORED_REPORT"
    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"
    ENTER_UNKNOWN_CANDIDATE = "ENTER_UNKNOWN_CANDIDATE"
    MAPPING_ERROR = "MAPPING_ERROR"
    DOMAIN_FIELD_UNSUPPORTED = "DOMAIN_FIELD_UNSUPPORTED"


class MappingErrorReason(StrEnum):
    MISSING_REPORT_TYPE = "MISSING_REPORT_TYPE"
    MISSING_EXCHANGE_REPORT_ID = "MISSING_EXCHANGE_REPORT_ID"
    MISSING_OCCURRED_AT = "MISSING_OCCURRED_AT"
    MISSING_EVENT_SOURCE = "MISSING_EVENT_SOURCE"
    MISSING_ORDER_IDENTITY = "MISSING_ORDER_IDENTITY"
    MISSING_OPERATION = "MISSING_OPERATION"
    MISSING_DELIVERY_PHASE = "MISSING_DELIVERY_PHASE"
    UNSUPPORTED_REPORT_TYPE = "UNSUPPORTED_REPORT_TYPE"
    UNSUPPORTED_OPERATION = "UNSUPPORTED_OPERATION"
    UNSUPPORTED_DELIVERY_PHASE = "UNSUPPORTED_DELIVERY_PHASE"
    OPERATION_REPORT_TYPE_MISMATCH = "OPERATION_REPORT_TYPE_MISMATCH"
    MISSING_CURRENT_ORDER_STATUS = "MISSING_CURRENT_ORDER_STATUS"
    MISSING_EXPECTED_PREVIOUS_STATUS = "MISSING_EXPECTED_PREVIOUS_STATUS"
    ILLEGAL_SAME_STATUS_EVENT = "ILLEGAL_SAME_STATUS_EVENT"
    DOMAIN_FIELD_UNSUPPORTED = "DOMAIN_FIELD_UNSUPPORTED"
    RAW_PAYLOAD_ONLY_FACT_FORBIDDEN = "RAW_PAYLOAD_ONLY_FACT_FORBIDDEN"
    UNKNOWN_REPORT_REQUIRES_OMS_UNKNOWN_ENTRY = "UNKNOWN_REPORT_REQUIRES_OMS_UNKNOWN_ENTRY"


@dataclass(frozen=True)
class ExchangeReport:
    report_type: ExchangeReportType | str | None = None
    exchange_report_id: str | None = None
    occurred_at: datetime | None = None
    event_source: EventSource | str | None = None
    order_id: str | None = None
    client_order_id: str | None = None
    account_id: str | None = None
    exchange: str | None = None
    instrument_id: str | None = None
    direction: Direction | str | None = None
    offset: Offset | str | None = None
    operation: ExecutionOperation | str | None = None
    delivery_phase: DeliveryPhase | str | None = None
    exchange_trade_id: str | None = None
    fill_id: str | None = None
    fill_price: Decimal | None = None
    fill_quantity: Decimal | None = None
    fee_amount: Decimal | None = None
    fee_currency: str | None = None
    fee_source: str | None = None
    trade_time: datetime | None = None
    trading_day: date | None = None
    raw_payload: Mapping[str, object] | None = None


@dataclass(frozen=True)
class MappingContext:
    current_order_status: OrderStatus | None = None
    expected_previous_status: OrderStatus | None = None
    known_exchange_report_ids: set[str] | None = None
    operation: ExecutionOperation | str | None = None
    allow_status_only_fill: bool = True


@dataclass(frozen=True)
class MappingError:
    reason: MappingErrorReason
    message: str


@dataclass(frozen=True)
class MappingResult:
    status: MappingResultStatus
    order_event: OrderEvent | None = None
    fill_event: FillEvent | None = None
    trade: Trade | None = None
    error: MappingError | None = None
