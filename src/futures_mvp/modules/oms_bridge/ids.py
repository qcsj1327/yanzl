import hashlib


def build_client_order_id(intent_id: str) -> str:
    return "oi_" + hashlib.sha256(intent_id.encode()).hexdigest()[:40]
