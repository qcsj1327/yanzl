from collections.abc import Iterable

from futures_mvp.domain.enums import OMSEventApplyResultStatus
from futures_mvp.domain.models import OMSEventApplyContext, OMSEventApplyResult
from futures_mvp.modules.oms_event_application.canonical import canonical_order_event_payload
from futures_mvp.modules.oms_event_application.service import OMSEventApplicationService


def replay_oms_order_events(
    contexts: Iterable[OMSEventApplyContext],
    *,
    service: OMSEventApplicationService,
    allow_live_apply: bool = False,
) -> list[OMSEventApplyResult]:
    ordered = sorted(
        contexts,
        key=lambda context: (
            context.order_event_candidate.occurred_at,
            context.order_event_candidate.normalized_report_id,
            context.order_event_candidate.order_id,
        ),
    )
    preflight = _dry_run_replay(service, ordered)
    if not allow_live_apply:
        return preflight
    if any(result.status is OMSEventApplyResultStatus.CONFLICT for result in preflight):
        return preflight

    applied_event_ids: set[str] = set()
    results: list[OMSEventApplyResult] = []
    for context, preflight_result in zip(ordered, preflight, strict=True):
        if (
            preflight_result.status is OMSEventApplyResultStatus.DUPLICATE
            and preflight_result.event_id in applied_event_ids
        ):
            results.append(preflight_result.model_copy(update={"dry_run": False}))
            continue
        result = service.apply_candidate(
            context.model_copy(update={"allow_live_apply": True}),
        )
        if result.event_id is not None and result.status in {
            OMSEventApplyResultStatus.APPLIED,
            OMSEventApplyResultStatus.DUPLICATE,
        }:
            applied_event_ids.add(result.event_id)
        results.append(result)
    return results


def _dry_run_replay(
    service: OMSEventApplicationService,
    contexts: list[OMSEventApplyContext],
) -> list[OMSEventApplyResult]:
    seen: dict[str, dict[str, object]] = {}
    results: list[OMSEventApplyResult] = []
    for context in contexts:
        result = service.apply_candidate(
            context.model_copy(update={"allow_live_apply": False}),
        )
        if result.event_id is not None and result.order_event is not None:
            event_id = result.event_id
            canonical = canonical_order_event_payload(result.order_event)
            if canonical is None:
                result = OMSEventApplyResult(
                    status=OMSEventApplyResultStatus.CONFLICT,
                    candidate=result.candidate,
                    order_event=result.order_event,
                    order_state=result.order_state,
                    event_id=event_id,
                    reason="order_event_canonical_missing",
                    dry_run=True,
                )
                results.append(result)
                continue
            existing = seen.get(event_id)
            if existing is None:
                seen[event_id] = canonical
            elif existing == canonical:
                result = OMSEventApplyResult(
                    status=OMSEventApplyResultStatus.DUPLICATE,
                    candidate=result.candidate,
                    order_event=result.order_event,
                    order_state=result.order_state,
                    event_id=event_id,
                    reason="order_event_duplicate",
                    dry_run=True,
                )
            else:
                result = OMSEventApplyResult(
                    status=OMSEventApplyResultStatus.CONFLICT,
                    candidate=result.candidate,
                    order_event=result.order_event,
                    order_state=result.order_state,
                    event_id=result.event_id,
                    reason="order_event_canonical_conflict",
                    dry_run=True,
                )
        results.append(result)
    return results
