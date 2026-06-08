from futures_mvp.domain.models import OrderEventCandidate, stable_json_sha256
from futures_mvp.modules.oms_event_application.canonical import canonical_event_id_payload


def build_oms_order_event_id(candidate: OrderEventCandidate) -> str:
    return "oe_" + stable_json_sha256(canonical_event_id_payload(candidate))[:40]
