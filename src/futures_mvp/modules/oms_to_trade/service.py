from futures_mvp.domain.enums import (
    EventSource,
    ExecutionReportStatus,
    OrderStatus,
    TradeBridgeResultStatus,
)
from futures_mvp.domain.models import (
    NormalizedExecutionReport,
    OrderEvent,
    Trade,
    TradeBridgeContext,
    TradeBridgeResult,
)
from futures_mvp.interfaces.repositories import TradeIdempotencyConflictError, TradeRepository
from futures_mvp.modules.oms_to_trade.identity import build_trade_identity

_FILLED_REPORT_STATUSES = {
    ExecutionReportStatus.PARTIALLY_FILLED,
    ExecutionReportStatus.FILLED,
}

_REPORT_TO_ORDER_STATUS = {
    ExecutionReportStatus.PARTIALLY_FILLED: OrderStatus.PARTIALLY_FILLED,
    ExecutionReportStatus.FILLED: OrderStatus.FILLED,
}


class OMSToTradeBridgeService:
    def __init__(self, trade_repository: TradeRepository) -> None:
        self._trades = trade_repository

    def create_trade(self, context: TradeBridgeContext) -> TradeBridgeResult:
        report = context.normalized_report
        source_order_event_id = _source_order_event_id(context)

        reject_reason = self._reject_reason(context)
        if reject_reason is not None:
            status, reason = reject_reason
            return TradeBridgeResult(
                status=status,
                source_report_id=report.report_id,
                source_order_event_id=source_order_event_id,
                reason=reason,
            )

        assert report.fill_price is not None
        try:
            exchange_trade_id, identity_source = build_trade_identity(
                account_id=context.order_state.request.account_id,
                exchange=context.order_state.request.exchange,
                exchange_trade_id=report.exchange_trade_id,
                order_id=report.order_id,
                report_id=report.report_id,
                cumulative_filled_qty=report.cumulative_filled_qty,
                fill_price=report.fill_price,
                report_ts=report.report_ts,
            )
        except (TypeError, ValueError) as exc:
            return TradeBridgeResult(
                status=TradeBridgeResultStatus.REJECTED_MISSING_TRADE_IDENTITY,
                source_report_id=report.report_id,
                source_order_event_id=source_order_event_id,
                reason=str(exc),
            )

        trade = Trade(
            account_id=context.order_state.request.account_id,
            exchange=context.order_state.request.exchange,
            exchange_trade_id=exchange_trade_id,
            identity_source=identity_source,
            order_id=report.order_id,
            client_order_id=report.client_order_id,
            instrument_id=context.order_state.request.instrument_id,
            trade_instrument_id=context.trade_instrument_id,
            symbol=context.symbol,
            direction=context.order_state.request.direction,
            offset=context.order_state.request.offset,
            price=report.fill_price,
            quantity=report.filled_qty,
            fee_amount=report.fee_amount,
            fee_currency=report.fee_currency,
            fee_source=report.fee_source,
            trade_time=report.report_ts,
            trading_day=context.trading_day,
            source_report_id=report.report_id,
            source_exchange_report_id=report.report_id,
            source_order_event_id=source_order_event_id,
            raw_payload=context.raw_payload,
        )

        existing = self._trades.get_by_trade_identity(
            trade.account_id,
            trade.exchange,
            trade.exchange_trade_id,
        )
        try:
            persisted = self._trades.append_trade(trade)
        except TradeIdempotencyConflictError as exc:
            return TradeBridgeResult(
                status=TradeBridgeResultStatus.CONFLICT,
                source_report_id=report.report_id,
                source_order_event_id=source_order_event_id,
                reason=str(exc),
            )
        except Exception as exc:
            return TradeBridgeResult(
                status=TradeBridgeResultStatus.ERROR,
                source_report_id=report.report_id,
                source_order_event_id=source_order_event_id,
                reason=str(exc),
            )

        return TradeBridgeResult(
            status=(
                TradeBridgeResultStatus.DUPLICATE
                if existing is not None
                else TradeBridgeResultStatus.CREATED
            ),
            trade=persisted,
            source_report_id=report.report_id,
            source_order_event_id=source_order_event_id,
        )

    def _reject_reason(
        self,
        context: TradeBridgeContext,
    ) -> tuple[TradeBridgeResultStatus, str] | None:
        report = context.normalized_report
        order_state = context.order_state

        if report.execution_status not in _FILLED_REPORT_STATUSES:
            return TradeBridgeResultStatus.REJECTED_NOT_FILLED, "report is not filled"
        if context.applied_order_event is None:
            return (
                TradeBridgeResultStatus.REJECTED_OMS_NOT_APPLIED,
                "applied OMS event proof is required",
            )
        proof_reason = _applied_event_reject_reason(
            context.applied_order_event,
            report,
        )
        if proof_reason is not None:
            status, reason = proof_reason
            return status, reason
        source_event_reason = _source_order_event_id_reject_reason(context)
        if source_event_reason is not None:
            return (
                TradeBridgeResultStatus.REJECTED_LINEAGE_MISMATCH,
                source_event_reason,
            )
        if report.order_id != order_state.order_id:
            return TradeBridgeResultStatus.REJECTED_LINEAGE_MISMATCH, "order_id mismatch"
        if report.client_order_id != order_state.request.client_order_id:
            return (
                TradeBridgeResultStatus.REJECTED_LINEAGE_MISMATCH,
                "client_order_id mismatch",
            )
        if (
            context.applied_order_event is not None
            and report.order_id != context.applied_order_event.order_id
        ):
            return (
                TradeBridgeResultStatus.REJECTED_LINEAGE_MISMATCH,
                "order event order_id mismatch",
            )
        if report.filled_qty <= 0:
            return TradeBridgeResultStatus.REJECTED_NOT_FILLED, "filled_qty must be positive"
        if report.fill_price is None or report.fill_price <= 0:
            return TradeBridgeResultStatus.REJECTED_NOT_FILLED, "fill_price must be positive"
        return None


def _applied_event_reject_reason(
    event: OrderEvent,
    report: NormalizedExecutionReport,
) -> tuple[TradeBridgeResultStatus, str] | None:
    expected_status = _REPORT_TO_ORDER_STATUS[report.execution_status]
    if event.event_source is not EventSource.EXECUTION_REPORT_NORMALIZER:
        return (
            TradeBridgeResultStatus.REJECTED_OMS_NOT_APPLIED,
            "OMS proof source is not execution_report_normalizer",
        )
    if event.new_status is not expected_status:
        return (
            TradeBridgeResultStatus.REJECTED_LINEAGE_MISMATCH,
            "OMS proof status does not match report status",
        )
    if event.execution_status is None:
        return (
            TradeBridgeResultStatus.REJECTED_OMS_NOT_APPLIED,
            "OMS proof missing execution_status",
        )
    if event.execution_status is not report.execution_status:
        return (
            TradeBridgeResultStatus.REJECTED_LINEAGE_MISMATCH,
            "OMS proof execution_status mismatch",
        )
    if event.report_id is None:
        return TradeBridgeResultStatus.REJECTED_OMS_NOT_APPLIED, "OMS proof missing report_id"
    if event.report_id != report.report_id:
        return TradeBridgeResultStatus.REJECTED_LINEAGE_MISMATCH, "OMS proof report_id mismatch"
    if event.report_ts is None:
        return TradeBridgeResultStatus.REJECTED_OMS_NOT_APPLIED, "OMS proof missing report_ts"
    if event.report_ts != report.report_ts:
        return TradeBridgeResultStatus.REJECTED_LINEAGE_MISMATCH, "OMS proof report_ts mismatch"
    if event.filled_qty is None:
        return TradeBridgeResultStatus.REJECTED_OMS_NOT_APPLIED, "OMS proof missing filled_qty"
    if event.filled_qty != report.filled_qty:
        return TradeBridgeResultStatus.REJECTED_LINEAGE_MISMATCH, "OMS proof filled_qty mismatch"
    if event.fill_price is None:
        return TradeBridgeResultStatus.REJECTED_OMS_NOT_APPLIED, "OMS proof missing fill_price"
    if event.fill_price != report.fill_price:
        return TradeBridgeResultStatus.REJECTED_LINEAGE_MISMATCH, "OMS proof fill_price mismatch"
    if event.cumulative_filled_qty is None:
        return (
            TradeBridgeResultStatus.REJECTED_OMS_NOT_APPLIED,
            "OMS proof missing cumulative_filled_qty",
        )
    if event.cumulative_filled_qty != report.cumulative_filled_qty:
        return (
            TradeBridgeResultStatus.REJECTED_LINEAGE_MISMATCH,
            "OMS proof cumulative_filled_qty mismatch",
        )
    return None


def _source_order_event_id_reject_reason(context: TradeBridgeContext) -> str | None:
    if context.source_order_event_id is None:
        return None
    if context.applied_order_event is None:
        return "source_order_event_id requires applied OMS event proof"
    if context.source_order_event_id != context.applied_order_event.external_event_id:
        return "source_order_event_id does not match applied OMS event"
    return None


def _source_order_event_id(context: TradeBridgeContext) -> str | None:
    if context.applied_order_event is not None:
        return context.applied_order_event.external_event_id
    return None
