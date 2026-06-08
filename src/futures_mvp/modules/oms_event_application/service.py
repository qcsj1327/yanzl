from futures_mvp.domain.enums import (
    EventApplicationStatus,
    ExecutionReportStatus,
    OMSEventApplyResultStatus,
)
from futures_mvp.domain.models import (
    OMSEventApplyContext,
    OMSEventApplyResult,
    OrderEvent,
    OrderEventCandidate,
    OrderState,
)
from futures_mvp.modules.oms_event_application.canonical import canonical_order_event_payload
from futures_mvp.modules.oms_event_application.ids import build_oms_order_event_id
from futures_mvp.modules.oms_event_application.mapping import (
    candidate_no_event_reason,
    map_candidate_to_order_event,
)
from futures_mvp.modules.oms_event_application.protocols import (
    OMSOrderEventApplier,
    OMSOrderEventLookup,
)


class OMSEventApplicationService:
    def __init__(
        self,
        oms_applier: OMSOrderEventApplier | None = None,
        *,
        event_lookup: OMSOrderEventLookup | None = None,
    ) -> None:
        self._oms_applier = oms_applier
        self._event_lookup = event_lookup

    def apply_candidate(self, context: OMSEventApplyContext) -> OMSEventApplyResult:
        candidate = context.order_event_candidate
        event_id = self._safe_event_id(candidate)
        invalid_reason = self._invalid_context_reason(context)
        if invalid_reason is not None:
            return self._result(
                OMSEventApplyResultStatus.REJECTED_INVALID_CANDIDATE,
                candidate,
                event_id=event_id,
                reason=invalid_reason,
                dry_run=not context.allow_live_apply,
            )

        no_event = candidate_no_event_reason(candidate)
        if no_event is not None:
            status_value, reason = no_event
            return self._result(
                OMSEventApplyResultStatus(status_value),
                candidate,
                event_id=event_id,
                reason=reason,
                dry_run=not context.allow_live_apply,
            )

        try:
            event = map_candidate_to_order_event(candidate, context.current_order_state)
        except ValueError as exc:
            return self._result(
                OMSEventApplyResultStatus.REJECTED_INVALID_CANDIDATE,
                candidate,
                event_id=event_id,
                reason=str(exc),
                dry_run=not context.allow_live_apply,
            )

        precheck = self._precheck_existing_event(event, candidate, context.allow_live_apply)
        if precheck is not None:
            return precheck

        if not context.allow_live_apply:
            return self._result(
                OMSEventApplyResultStatus.DRY_RUN,
                candidate,
                order_event=event,
                event_id=event.external_event_id,
                dry_run=True,
            )

        if self._oms_applier is None:
            return self._result(
                OMSEventApplyResultStatus.ERROR,
                candidate,
                order_event=event,
                event_id=event.external_event_id,
                reason="live OMS apply requires OMSOrderEventApplier",
                dry_run=False,
            )

        try:
            oms_result = self._oms_applier.apply_order_event(event)
        except Exception as exc:  # noqa: BLE001
            return self._result(
                OMSEventApplyResultStatus.ERROR,
                candidate,
                order_event=event,
                event_id=event.external_event_id,
                reason=str(exc),
                dry_run=False,
            )
        return self._result(
            _map_oms_result_status(oms_result.status),
            candidate,
            order_event=event,
            order_state=oms_result.order,
            event_id=event.external_event_id,
            reason=oms_result.reason,
            dry_run=False,
        )

    def _invalid_context_reason(self, context: OMSEventApplyContext) -> str | None:
        candidate = context.order_event_candidate
        if candidate.order_id != context.current_order_state.order_id:
            return "candidate_order_id_mismatch"
        if not candidate.normalized_report_id:
            return "normalized_report_id is required"
        if candidate.execution_status is None:
            return "execution_status is required"
        if candidate.cumulative_filled_qty is None:
            return "cumulative_filled_qty is required"
        if candidate.execution_status in {
            ExecutionReportStatus.PARTIALLY_FILLED,
            ExecutionReportStatus.FILLED,
        }:
            if candidate.fill_price is None:
                return "fill_price is required for fill execution statuses"
            if candidate.filled_qty is None:
                return "filled_qty is required for fill execution statuses"
        return None

    def _safe_event_id(self, candidate: OrderEventCandidate) -> str | None:
        try:
            if candidate.execution_status is None or candidate.cumulative_filled_qty is None:
                return None
            return build_oms_order_event_id(candidate)
        except Exception:  # noqa: BLE001
            return None

    def _result(
        self,
        status: OMSEventApplyResultStatus,
        candidate: OrderEventCandidate,
        *,
        order_event: OrderEvent | None = None,
        order_state: OrderState | None = None,
        event_id: str | None = None,
        reason: str | None = None,
        dry_run: bool,
    ) -> OMSEventApplyResult:
        return OMSEventApplyResult(
            status=status,
            candidate=candidate,
            order_event=order_event,
            order_state=order_state,
            event_id=event_id,
            reason=reason,
            dry_run=dry_run,
        )

    def _precheck_existing_event(
        self,
        event: OrderEvent,
        candidate: OrderEventCandidate,
        allow_live_apply: bool,
    ) -> OMSEventApplyResult | None:
        if self._event_lookup is None:
            if allow_live_apply:
                return self._result(
                    OMSEventApplyResultStatus.ERROR,
                    candidate,
                    order_event=event,
                    event_id=event.external_event_id,
                    reason="live OMS apply requires OMSOrderEventLookup",
                    dry_run=False,
                )
            return None
        try:
            existing = self._event_lookup.get_by_event_key(
                event.event_source,
                event.external_event_id,
            )
        except Exception as exc:  # noqa: BLE001
            return self._result(
                OMSEventApplyResultStatus.ERROR,
                candidate,
                order_event=event,
                event_id=event.external_event_id,
                reason=str(exc),
                dry_run=not allow_live_apply,
            )
        if existing is None:
            return None

        current_canonical = canonical_order_event_payload(event)
        existing_canonical = canonical_order_event_payload(existing)
        if current_canonical is not None and existing_canonical == current_canonical:
            return self._result(
                OMSEventApplyResultStatus.DUPLICATE,
                candidate,
                order_event=event,
                event_id=event.external_event_id,
                reason="order_event_duplicate",
                dry_run=not allow_live_apply,
            )
        return self._result(
            OMSEventApplyResultStatus.CONFLICT,
            candidate,
            order_event=event,
            event_id=event.external_event_id,
            reason="order_event_canonical_conflict",
            dry_run=not allow_live_apply,
        )


def _map_oms_result_status(status: EventApplicationStatus) -> OMSEventApplyResultStatus:
    if status is EventApplicationStatus.APPLIED:
        return OMSEventApplyResultStatus.APPLIED
    if status is EventApplicationStatus.DUPLICATE:
        return OMSEventApplyResultStatus.DUPLICATE
    if status in {
        EventApplicationStatus.EVENT_KEY_COLLISION,
        EventApplicationStatus.MISMATCH_REJECTED,
    }:
        return OMSEventApplyResultStatus.CONFLICT
    return OMSEventApplyResultStatus.ERROR
