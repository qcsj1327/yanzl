from collections.abc import Callable
from datetime import UTC, datetime

from futures_mvp.domain.enums import ExecutionReportNormalizeResultStatus
from futures_mvp.domain.models import (
    ExecutionReportNormalizeResult,
    NormalizedExecutionReport,
    RawExecutionReport,
)
from futures_mvp.interfaces.repositories import (
    ExecutionReportConflictError,
    ExecutionReportUnitOfWork,
)
from futures_mvp.modules.execution_reports.canonical import (
    build_source_report_hash,
    canonical_normalized_execution_report_payload,
)
from futures_mvp.modules.execution_reports.ids import build_normalized_report_id
from futures_mvp.modules.execution_reports.mapping import (
    build_order_event_candidate,
    map_report_type_to_execution_status,
)


class ExecutionReportNormalizer:
    def __init__(
        self,
        uow_factory: Callable[[], ExecutionReportUnitOfWork],
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def normalize(self, raw_report: RawExecutionReport) -> ExecutionReportNormalizeResult:
        invalid_reason = self._invalid_lineage_reason(raw_report)
        if invalid_reason is not None:
            return ExecutionReportNormalizeResult(
                status=ExecutionReportNormalizeResultStatus.REJECTED_INVALID_REPORT,
                reason=invalid_reason,
            )

        try:
            normalized_report = self.build_normalized_report(raw_report)
        except ValueError as exc:
            return ExecutionReportNormalizeResult(
                status=ExecutionReportNormalizeResultStatus.REJECTED_INVALID_REPORT,
                reason=str(exc),
            )

        candidate = build_order_event_candidate(normalized_report)
        with self._uow_factory() as uow:
            existing = uow.execution_reports.get_by_report_id(normalized_report.report_id)
            if existing is not None:
                if canonical_normalized_execution_report_payload(
                    existing
                ) != canonical_normalized_execution_report_payload(normalized_report):
                    uow.rollback()
                    return ExecutionReportNormalizeResult(
                        status=ExecutionReportNormalizeResultStatus.CONFLICT,
                        normalized_report=existing,
                        reason="normalized_execution_report_canonical_conflict",
                    )
                uow.commit()
                return ExecutionReportNormalizeResult(
                    status=ExecutionReportNormalizeResultStatus.DUPLICATE,
                    normalized_report=existing,
                    reason="duplicate",
                )
            try:
                persisted = uow.execution_reports.append_normalized_report(normalized_report)
            except ExecutionReportConflictError:
                uow.rollback()
                return ExecutionReportNormalizeResult(
                    status=ExecutionReportNormalizeResultStatus.CONFLICT,
                    normalized_report=normalized_report,
                    reason="normalized_execution_report_canonical_conflict",
                )
            uow.commit()
        return ExecutionReportNormalizeResult(
            status=ExecutionReportNormalizeResultStatus.NORMALIZED,
            normalized_report=persisted,
            order_event_candidate=candidate,
        )

    def build_normalized_report(self, raw_report: RawExecutionReport) -> NormalizedExecutionReport:
        execution_status = map_report_type_to_execution_status(raw_report.report_type)
        source_report_hash = build_source_report_hash(raw_report)
        report_id = build_normalized_report_id(raw_report, source_report_hash)
        reason = None
        if execution_status.value == "ERROR":
            reason = f"mapped_error_report_type:{raw_report.report_type}"
        return NormalizedExecutionReport(
            report_id=report_id,
            raw_report_id=raw_report.raw_report_id,
            adapter_name=raw_report.adapter_name,
            execution_target=raw_report.execution_target,
            command_id=raw_report.command_id,
            order_id=raw_report.order_id,
            client_order_id=raw_report.client_order_id,
            adapter_order_ref=raw_report.adapter_order_ref,
            exchange_order_id=raw_report.exchange_order_id,
            execution_status=execution_status,
            filled_qty=raw_report.filled_qty,
            fill_price=raw_report.fill_price,
            cumulative_filled_qty=raw_report.cumulative_filled_qty,
            remaining_qty=raw_report.remaining_qty,
            report_ts=raw_report.report_ts,
            normalized_at=self._clock(),
            reason=reason,
            source_report_hash=source_report_hash,
            raw_payload=raw_report.raw_payload,
        )

    def _invalid_lineage_reason(self, raw_report: RawExecutionReport) -> str | None:
        if not raw_report.command_id:
            return "command_id is required"
        if not raw_report.order_id:
            return "order_id is required"
        if not raw_report.client_order_id:
            return "client_order_id is required"
        if not raw_report.adapter_name:
            return "adapter_name is required"
        return None
