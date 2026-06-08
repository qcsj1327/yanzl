"""Stage K Execution Gateway core."""

from futures_mvp.modules.execution_gateway.adapters import MockExecutionAdapter
from futures_mvp.modules.execution_gateway.canonical import (
    build_execution_command_payload_hash,
    canonical_execution_command_payload,
)
from futures_mvp.modules.execution_gateway.ids import build_execution_command_id
from futures_mvp.modules.execution_gateway.replay import replay_execution_gateway
from futures_mvp.modules.execution_gateway.service import ExecutionGatewayService

__all__ = [
    "ExecutionGatewayService",
    "MockExecutionAdapter",
    "build_execution_command_id",
    "build_execution_command_payload_hash",
    "canonical_execution_command_payload",
    "replay_execution_gateway",
]
