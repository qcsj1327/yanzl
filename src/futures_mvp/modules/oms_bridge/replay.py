from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from futures_mvp.domain.models import OMSBridgeContext, OMSBridgeResult
from futures_mvp.modules.oms_bridge.canonical import (
    build_bridge_payload_hash,
    canonical_oms_bridge_payload,
)
from futures_mvp.modules.oms_bridge.ids import build_client_order_id
from futures_mvp.modules.oms_bridge.service import OMSBridgeService

ReplayPreviewStatus = Literal["WOULD_CREATE", "DUPLICATE", "CONFLICT"]


@dataclass(frozen=True)
class OMSBridgeReplayPreview:
    status: ReplayPreviewStatus
    intent_id: str
    client_order_id: str
    bridge_payload_hash: str
    reason: str | None = None


def replay_oms_bridge(
    contexts: Iterable[OMSBridgeContext],
    *,
    service: OMSBridgeService | None = None,
    dry_run: bool = True,
    allow_live_oms: bool = False,
) -> list[OMSBridgeReplayPreview] | list[OMSBridgeResult]:
    ordered = sorted(
        contexts,
        key=lambda context: (
            context.order_intent.exchange,
            context.order_intent.instrument_id,
            context.order_intent.trading_day,
            context.order_intent.intent_id,
        ),
    )
    if dry_run:
        return _preview_replay(ordered)
    if not allow_live_oms:
        raise ValueError("live OMS bridge replay requires allow_live_oms=True")
    if service is None:
        raise ValueError("live OMS bridge replay requires service")
    return [service.create_order(context) for context in ordered]


def _preview_replay(contexts: list[OMSBridgeContext]) -> list[OMSBridgeReplayPreview]:
    seen: dict[str, str] = {}
    previews: list[OMSBridgeReplayPreview] = []
    for context in contexts:
        client_order_id = build_client_order_id(context.order_intent.intent_id)
        payload = canonical_oms_bridge_payload(context, client_order_id)
        bridge_payload_hash = build_bridge_payload_hash(payload)
        existing_hash = seen.get(client_order_id)
        if existing_hash is None:
            seen[client_order_id] = bridge_payload_hash
            previews.append(
                OMSBridgeReplayPreview(
                    status="WOULD_CREATE",
                    intent_id=context.order_intent.intent_id,
                    client_order_id=client_order_id,
                    bridge_payload_hash=bridge_payload_hash,
                )
            )
        elif existing_hash == bridge_payload_hash:
            previews.append(
                OMSBridgeReplayPreview(
                    status="DUPLICATE",
                    intent_id=context.order_intent.intent_id,
                    client_order_id=client_order_id,
                    bridge_payload_hash=bridge_payload_hash,
                    reason="duplicate",
                )
            )
        else:
            previews.append(
                OMSBridgeReplayPreview(
                    status="CONFLICT",
                    intent_id=context.order_intent.intent_id,
                    client_order_id=client_order_id,
                    bridge_payload_hash=bridge_payload_hash,
                    reason="bridge_payload_hash_conflict",
                )
            )
    return previews
