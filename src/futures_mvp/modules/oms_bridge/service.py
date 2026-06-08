import inspect
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

from futures_mvp.domain.enums import (
    Direction,
    OMSBridgeResultStatus,
    RiskResultStatus,
    SignalSide,
)
from futures_mvp.domain.models import (
    OMSBridgeContext,
    OMSBridgeResult,
    OrderRequest,
    OrderState,
)
from futures_mvp.modules.oms_bridge.canonical import (
    build_bridge_payload_hash,
    canonical_oms_bridge_payload,
)
from futures_mvp.modules.oms_bridge.ids import build_client_order_id
from futures_mvp.modules.oms_bridge.protocols import OMSOrderCreator, OMSOrderLookup


class OMSBridgeService:
    def __init__(
        self,
        order_creator: OMSOrderCreator,
        *,
        order_lookup: OMSOrderLookup | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._order_creator = order_creator
        inferred_lookup = (
            order_creator if hasattr(order_creator, "get_by_client_order_id") else None
        )
        self._order_lookup = order_lookup or cast(OMSOrderLookup | None, inferred_lookup)
        self._clock = clock or (lambda: datetime.now(UTC))

    def create_order(self, context: OMSBridgeContext) -> OMSBridgeResult:
        client_order_id = build_client_order_id(context.order_intent.intent_id)
        payload = canonical_oms_bridge_payload(context, client_order_id)
        bridge_payload_hash = build_bridge_payload_hash(payload)

        invalid_status, invalid_reason = self._invalid_context_reason(context)
        if invalid_status is not None:
            return self._result(
                invalid_status,
                context,
                client_order_id,
                bridge_payload_hash,
                reason=invalid_reason,
            )

        request = self.build_order_request(context, client_order_id)
        existing = self._lookup_existing(client_order_id)
        if existing is not None:
            if not self._is_duplicate(existing, request, context, bridge_payload_hash):
                return self._result(
                    OMSBridgeResultStatus.CONFLICT,
                    context,
                    client_order_id,
                    bridge_payload_hash,
                    order_id=existing.order_id,
                    reason="client_order_id_canonical_conflict",
                )
            return self._result(
                OMSBridgeResultStatus.DUPLICATE,
                context,
                client_order_id,
                bridge_payload_hash,
                order_id=existing.order_id,
                reason="duplicate",
            )

        try:
            order = self._create_order(
                request,
                client_order_id=client_order_id,
                context=context,
                bridge_payload_hash=bridge_payload_hash,
            )
        except Exception as exc:  # noqa: BLE001
            return self._result(
                OMSBridgeResultStatus.ERROR,
                context,
                client_order_id,
                bridge_payload_hash,
                reason=str(exc),
            )

        return self._result(
            OMSBridgeResultStatus.CREATED,
            context,
            client_order_id,
            bridge_payload_hash,
            order_id=order.order_id,
        )

    def build_order_request(
        self,
        context: OMSBridgeContext,
        client_order_id: str | None = None,
    ) -> OrderRequest:
        intent = context.order_intent
        return OrderRequest(
            client_order_id=client_order_id or build_client_order_id(intent.intent_id),
            account_id=context.account_id,
            instrument_id=intent.instrument_id,
            exchange=intent.exchange,
            direction=_direction_from_side(intent.side),
            offset=intent.offset,
            order_type=intent.order_type,
            limit_price=intent.price,
            quantity=intent.quantity,
        )

    def _invalid_context_reason(
        self,
        context: OMSBridgeContext,
    ) -> tuple[OMSBridgeResultStatus | None, str | None]:
        intent = context.order_intent
        risk_result = context.trading_risk_result
        if not intent.risk_result_id:
            return (
                OMSBridgeResultStatus.REJECTED_INVALID_INTENT,
                "risk_result_id is required",
            )
        if intent.risk_result_id != risk_result.risk_result_id:
            return (
                OMSBridgeResultStatus.REJECTED_INVALID_INTENT,
                "risk_result_id mismatch",
            )
        if risk_result.risk_status not in {RiskResultStatus.ACCEPT, RiskResultStatus.REDUCE}:
            return (
                OMSBridgeResultStatus.REJECTED_RISK_NOT_ACCEPTED,
                "risk result is not accepted or reduced",
            )
        if intent.quantity <= Decimal("0"):
            return (
                OMSBridgeResultStatus.REJECTED_INVALID_INTENT,
                "order intent quantity must be greater than 0",
            )
        if intent.quantity != risk_result.approved_quantity:
            return (
                OMSBridgeResultStatus.REJECTED_INVALID_INTENT,
                "order intent quantity must equal approved_quantity",
            )
        return None, None

    def _lookup_existing(self, client_order_id: str) -> OrderState | None:
        if self._order_lookup is None:
            return None
        return self._order_lookup.get_by_client_order_id(client_order_id)

    def _create_order(
        self,
        request: OrderRequest,
        *,
        client_order_id: str,
        context: OMSBridgeContext,
        bridge_payload_hash: str,
    ) -> OrderState:
        if self._creator_accepts_bridge_metadata():
            creator = cast(Any, self._order_creator)
            return cast(
                OrderState,
                creator.create_order(
                    request,
                    client_order_id=client_order_id,
                    bridge_payload_hash=bridge_payload_hash,
                    intent_id=context.order_intent.intent_id,
                    risk_result_id=context.order_intent.risk_result_id,
                    signal_id=context.order_intent.signal_id,
                ),
            )
        return self._order_creator.create_order(
            request,
            client_order_id=client_order_id,
        )

    def _creator_accepts_bridge_metadata(self) -> bool:
        try:
            signature = inspect.signature(self._order_creator.create_order)
        except (TypeError, ValueError):
            return False
        parameters = signature.parameters
        return (
            "bridge_payload_hash" in parameters
            or any(
                parameter.kind is inspect.Parameter.VAR_KEYWORD
                for parameter in parameters.values()
            )
        )

    def _result(
        self,
        status: OMSBridgeResultStatus,
        context: OMSBridgeContext,
        client_order_id: str,
        bridge_payload_hash: str,
        *,
        order_id: str | None = None,
        reason: str | None = None,
    ) -> OMSBridgeResult:
        return OMSBridgeResult(
            status=status,
            intent_id=context.order_intent.intent_id,
            client_order_id=client_order_id,
            order_id=order_id,
            bridge_payload_hash=bridge_payload_hash,
            reason=reason,
            bridge_ts=self._clock(),
        )

    def _is_duplicate(
        self,
        existing: OrderState,
        requested: OrderRequest,
        context: OMSBridgeContext,
        bridge_payload_hash: str,
    ) -> bool:
        if existing.bridge_payload_hash is not None:
            return existing.bridge_payload_hash == bridge_payload_hash
        if not self._same_bridge_lineage(existing, context, requested.client_order_id):
            return False
        return self._same_oms_request(existing.request, requested)

    def _same_bridge_lineage(
        self,
        existing: OrderState,
        context: OMSBridgeContext,
        client_order_id: str,
    ) -> bool:
        return (
            existing.request.client_order_id == client_order_id
            and existing.intent_id == context.order_intent.intent_id
            and existing.risk_result_id == context.order_intent.risk_result_id
        )

    def _same_oms_request(self, existing: OrderRequest, requested: OrderRequest) -> bool:
        return existing == requested


def _direction_from_side(side: SignalSide) -> Direction:
    if side is SignalSide.BUY:
        return Direction.BUY
    if side is SignalSide.SELL:
        return Direction.SELL
    raise ValueError("OrderIntent side must be BUY or SELL")
