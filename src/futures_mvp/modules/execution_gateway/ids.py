from futures_mvp.domain.enums import ExecutionCommandType, ExecutionTarget
from futures_mvp.domain.models import stable_json_sha256


def build_execution_command_id(
    order_id: str,
    command_type: ExecutionCommandType,
    execution_target: ExecutionTarget,
) -> str:
    payload = {
        "command_type": command_type.value,
        "execution_target": execution_target.value,
        "order_id": order_id,
    }
    return "ec_" + stable_json_sha256(payload)
