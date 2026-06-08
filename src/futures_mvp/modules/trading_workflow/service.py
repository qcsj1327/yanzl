from collections.abc import Callable

from futures_mvp.domain.enums import RiskResultStatus, TradingWorkflowResultStatus
from futures_mvp.domain.models import (
    TradingRiskResult,
    TradingWorkflowContext,
    TradingWorkflowResult,
)
from futures_mvp.interfaces.repositories import (
    OrderIntentConflictError,
    TradingRiskResultConflictError,
    TradingWorkflowUnitOfWork,
)
from futures_mvp.modules.trading_workflow.builder import (
    build_order_intent,
    build_trading_risk_result_id,
    normalize_reduce_result_if_needed,
)
from futures_mvp.modules.trading_workflow.canonical import (
    canonical_order_intent_payload,
    canonical_trading_risk_result_payload,
)
from futures_mvp.modules.trading_workflow.protocols import RiskEvaluator


class TradingWorkflowService:
    def __init__(
        self,
        uow_factory: Callable[[], TradingWorkflowUnitOfWork],
        risk_evaluator: RiskEvaluator,
    ) -> None:
        self._uow_factory = uow_factory
        self._risk_evaluator = risk_evaluator

    def run(self, context: TradingWorkflowContext) -> TradingWorkflowResult:
        evaluated = self._risk_evaluator.evaluate(context)
        try:
            risk_result = normalize_reduce_result_if_needed(
                evaluated,
                context.requested_quantity,
            )
        except ValueError as exc:
            return TradingWorkflowResult(
                status=TradingWorkflowResultStatus.ERROR,
                reason=str(exc),
            )
        invalid_reason = self._invalid_risk_result_reason(risk_result, context)
        if invalid_reason is not None:
            return TradingWorkflowResult(
                status=TradingWorkflowResultStatus.ERROR,
                risk_result=risk_result,
                reason=invalid_reason,
            )

        intent = None
        if risk_result.risk_status in {RiskResultStatus.ACCEPT, RiskResultStatus.REDUCE}:
            try:
                intent = build_order_intent(context.signal_decision, risk_result, context)
            except ValueError as exc:
                return TradingWorkflowResult(
                    status=TradingWorkflowResultStatus.ERROR,
                    risk_result=risk_result,
                    reason=str(exc),
                )

        with self._uow_factory() as uow:
            existing_intent = None
            intent_was_duplicate = False
            if intent is not None:
                existing_intent = uow.order_intents.get_by_intent_id(intent.intent_id)
                intent_was_duplicate = existing_intent is not None
                if existing_intent is not None:
                    existing_payload = canonical_order_intent_payload(existing_intent)
                    intent_payload = canonical_order_intent_payload(intent)
                    if existing_payload != intent_payload:
                        uow.rollback()
                        return TradingWorkflowResult(
                            status=TradingWorkflowResultStatus.CONFLICT,
                            risk_result=risk_result,
                            order_intent=existing_intent,
                            reason="order_intent_canonical_conflict",
                        )

            existing_risk = uow.trading_risk_results.get_by_risk_result_id(
                risk_result.risk_result_id
            )
            risk_was_duplicate = existing_risk is not None
            if existing_risk is not None:
                if canonical_trading_risk_result_payload(
                    existing_risk
                ) != canonical_trading_risk_result_payload(risk_result):
                    uow.rollback()
                    return TradingWorkflowResult(
                        status=TradingWorkflowResultStatus.CONFLICT,
                        risk_result=existing_risk,
                        reason="risk_result_canonical_conflict",
                    )
                persisted_risk = existing_risk
            else:
                try:
                    persisted_risk = uow.trading_risk_results.append_risk_result(risk_result)
                except TradingRiskResultConflictError:
                    uow.rollback()
                    return TradingWorkflowResult(
                        status=TradingWorkflowResultStatus.CONFLICT,
                        risk_result=risk_result,
                        reason="risk_result_canonical_conflict",
                    )

            if persisted_risk.risk_status in {
                RiskResultStatus.REJECT,
                RiskResultStatus.BLOCK,
                RiskResultStatus.UNKNOWN,
            }:
                uow.commit()
                return TradingWorkflowResult(
                    status=self._rejected_status(persisted_risk.risk_status),
                    risk_result=persisted_risk,
                    reason=persisted_risk.risk_reason,
                )

            if existing_intent is not None:
                persisted_intent = existing_intent
            else:
                assert intent is not None
                try:
                    persisted_intent = uow.order_intents.append_order_intent(intent)
                except OrderIntentConflictError:
                    uow.rollback()
                    return TradingWorkflowResult(
                        status=TradingWorkflowResultStatus.CONFLICT,
                        risk_result=persisted_risk,
                        order_intent=intent,
                        reason="order_intent_canonical_conflict",
                    )

            uow.commit()
            if risk_was_duplicate or intent_was_duplicate:
                return TradingWorkflowResult(
                    status=TradingWorkflowResultStatus.DUPLICATE,
                    risk_result=persisted_risk,
                    order_intent=persisted_intent,
                    reason="duplicate",
                )
            return TradingWorkflowResult(
                status=TradingWorkflowResultStatus.INTENT_CREATED,
                risk_result=persisted_risk,
                order_intent=persisted_intent,
            )

    def _invalid_risk_result_reason(
        self,
        result: TradingRiskResult,
        context: TradingWorkflowContext,
    ) -> str | None:
        if result.risk_result_id != build_trading_risk_result_id(result):
            return "risk_result_id mismatch"
        if result.signal_id != context.signal_decision.signal_id:
            return "signal_id mismatch"
        if result.config_hash != context.risk_config_hash:
            return "risk config hash mismatch"
        if result.evaluation_context_hash != context.evaluation_context_hash:
            return "evaluation_context_hash mismatch"
        if result.requested_quantity != context.requested_quantity:
            return "requested_quantity mismatch"
        if result.risk_status is RiskResultStatus.ACCEPT:
            if result.approved_quantity != context.requested_quantity:
                return "ACCEPT requires approved_quantity equal requested_quantity"
        if result.risk_status is RiskResultStatus.REDUCE and (
            result.approved_quantity <= 0
            or result.approved_quantity >= context.requested_quantity
        ):
            return "REDUCE requires approved_quantity between 0 and requested_quantity"
        if result.approved_quantity > context.requested_quantity:
            return "approved_quantity cannot exceed requested_quantity"
        return None

    def _rejected_status(self, status: RiskResultStatus) -> TradingWorkflowResultStatus:
        if status is RiskResultStatus.REJECT:
            return TradingWorkflowResultStatus.RISK_REJECTED
        if status is RiskResultStatus.BLOCK:
            return TradingWorkflowResultStatus.RISK_BLOCKED
        return TradingWorkflowResultStatus.RISK_UNKNOWN
