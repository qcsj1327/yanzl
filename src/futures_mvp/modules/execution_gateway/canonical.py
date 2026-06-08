from typing import Any

from futures_mvp.domain.models import ExecutionCommand, stable_json_sha256


def _decimal_value(value: object) -> str:
    return format(value.normalize(), "f") if hasattr(value, "normalize") else str(value)


def canonical_execution_command_payload(command: ExecutionCommand) -> dict[str, Any]:
    return {
        "account_id": command.account_id,
        "client_order_id": command.client_order_id,
        "command_type": command.command_type.value,
        "exchange": command.exchange,
        "execution_target": command.execution_target.value,
        "instrument_id": command.instrument_id,
        "offset": command.offset.value,
        "order_id": command.order_id,
        "order_type": command.order_type.value,
        "price": _decimal_value(command.price),
        "quantity": _decimal_value(command.quantity),
        "side": command.side.value,
        "symbol": command.symbol,
        "tif": command.tif,
        "trade_instrument_id": command.trade_instrument_id,
    }


def build_execution_command_payload_hash(command: ExecutionCommand) -> str:
    return stable_json_sha256(canonical_execution_command_payload(command))
