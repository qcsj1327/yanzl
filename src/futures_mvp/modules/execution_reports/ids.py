from futures_mvp.domain.models import RawExecutionReport, stable_json_sha256


def build_normalized_report_id(
    raw: RawExecutionReport,
    source_report_hash: str,
) -> str:
    payload = {
        "client_order_id": raw.client_order_id,
        "command_id": raw.command_id,
        "order_id": raw.order_id,
        "source_report_hash": source_report_hash,
    }
    return "er_" + stable_json_sha256(payload)
