from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from futures_mvp.domain.enums import EventSource
from futures_mvp.domain.models import OrderState
from futures_mvp.modules.execution.models import (
    DeliveryPhase,
    ExchangeReport,
    ExchangeReportType,
    ExecutionOperation,
)

if TYPE_CHECKING:
    from futures_mvp.interfaces.engines import ExecutionReportSink


class MockSubmitResult(StrEnum):
    ACK = "ACK"
    REJECTED = "REJECTED"
    TIMEOUT = "TIMEOUT"
    EXCHANGE_UNAVAILABLE_PRE_SEND = "EXCHANGE_UNAVAILABLE_PRE_SEND"
    EXCHANGE_UNAVAILABLE_POST_SEND_UNCERTAIN = "EXCHANGE_UNAVAILABLE_POST_SEND_UNCERTAIN"


class MockCancelResult(StrEnum):
    CANCELED = "CANCELED"
    CANCEL_REJECTED = "CANCEL_REJECTED"
    TIMEOUT = "TIMEOUT"
    EXCHANGE_UNAVAILABLE_PRE_SEND = "EXCHANGE_UNAVAILABLE_PRE_SEND"
    EXCHANGE_UNAVAILABLE_POST_SEND_UNCERTAIN = "EXCHANGE_UNAVAILABLE_POST_SEND_UNCERTAIN"


class DeterministicReportIdGenerator:
    def __init__(self, prefix: str = "exchange-report") -> None:
        self._prefix = prefix
        self._next_id = 1

    def __call__(self) -> str:
        report_id = f"{self._prefix}-{self._next_id}"
        self._next_id += 1
        return report_id


class ConfigurableMockFuturesExchange:
    def __init__(
        self,
        report_sink: ExecutionReportSink,
        *,
        id_generator: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
        submit_results: list[MockSubmitResult] | None = None,
        cancel_results: list[MockCancelResult] | None = None,
    ) -> None:
        self._report_sink = report_sink
        self._id_generator = id_generator or DeterministicReportIdGenerator()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._submit_results = list(submit_results or [MockSubmitResult.ACK])
        self._cancel_results = list(cancel_results or [MockCancelResult.CANCELED])
        self._submit_index = 0
        self._cancel_index = 0

    def submit_limit_order(self, order: OrderState) -> None:
        result = self._next_submit_result()
        self._report_sink.append(self._submit_report(order, result))

    def cancel_order(self, order: OrderState) -> None:
        result = self._next_cancel_result()
        self._report_sink.append(self._cancel_report(order, result))

    def _next_submit_result(self) -> MockSubmitResult:
        result = self._submit_results[min(self._submit_index, len(self._submit_results) - 1)]
        self._submit_index += 1
        return result

    def _next_cancel_result(self) -> MockCancelResult:
        result = self._cancel_results[min(self._cancel_index, len(self._cancel_results) - 1)]
        self._cancel_index += 1
        return result

    def _base_report(
        self,
        order: OrderState,
        *,
        report_type: ExchangeReportType,
        operation: ExecutionOperation,
        delivery_phase: DeliveryPhase | None = None,
    ) -> ExchangeReport:
        return ExchangeReport(
            report_type=report_type,
            exchange_report_id=self._id_generator(),
            occurred_at=self._clock(),
            event_source=EventSource.EXCHANGE,
            order_id=order.order_id,
            client_order_id=order.request.client_order_id,
            operation=operation,
            delivery_phase=delivery_phase,
        )

    def _submit_report(self, order: OrderState, result: MockSubmitResult) -> ExchangeReport:
        if result is MockSubmitResult.ACK:
            return self._base_report(
                order,
                report_type=ExchangeReportType.ACK,
                operation=ExecutionOperation.SUBMIT,
            )
        if result is MockSubmitResult.REJECTED:
            return self._base_report(
                order,
                report_type=ExchangeReportType.REJECTED,
                operation=ExecutionOperation.SUBMIT,
            )
        if result is MockSubmitResult.TIMEOUT:
            return self._base_report(
                order,
                report_type=ExchangeReportType.TIMEOUT,
                operation=ExecutionOperation.SUBMIT,
            )
        if result is MockSubmitResult.EXCHANGE_UNAVAILABLE_PRE_SEND:
            return self._base_report(
                order,
                report_type=ExchangeReportType.EXCHANGE_UNAVAILABLE,
                operation=ExecutionOperation.SUBMIT,
                delivery_phase=DeliveryPhase.PRE_SEND,
            )
        return self._base_report(
            order,
            report_type=ExchangeReportType.EXCHANGE_UNAVAILABLE,
            operation=ExecutionOperation.SUBMIT,
            delivery_phase=DeliveryPhase.POST_SEND_UNCERTAIN,
        )

    def _cancel_report(self, order: OrderState, result: MockCancelResult) -> ExchangeReport:
        if result is MockCancelResult.CANCELED:
            return self._base_report(
                order,
                report_type=ExchangeReportType.CANCELED,
                operation=ExecutionOperation.CANCEL,
            )
        if result is MockCancelResult.CANCEL_REJECTED:
            return self._base_report(
                order,
                report_type=ExchangeReportType.CANCEL_REJECTED,
                operation=ExecutionOperation.CANCEL,
            )
        if result is MockCancelResult.TIMEOUT:
            return self._base_report(
                order,
                report_type=ExchangeReportType.TIMEOUT,
                operation=ExecutionOperation.CANCEL,
            )
        if result is MockCancelResult.EXCHANGE_UNAVAILABLE_PRE_SEND:
            return self._base_report(
                order,
                report_type=ExchangeReportType.EXCHANGE_UNAVAILABLE,
                operation=ExecutionOperation.CANCEL,
                delivery_phase=DeliveryPhase.PRE_SEND,
            )
        return self._base_report(
            order,
            report_type=ExchangeReportType.EXCHANGE_UNAVAILABLE,
            operation=ExecutionOperation.CANCEL,
            delivery_phase=DeliveryPhase.POST_SEND_UNCERTAIN,
        )
