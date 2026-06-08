from collections.abc import Callable
from datetime import UTC, datetime

from futures_mvp.domain.enums import ExecutionCommandResultStatus
from futures_mvp.domain.models import ExecutionCommand, ExecutionCommandResult, stable_json_sha256


class MockExecutionAdapter:
    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self.submitted_commands: list[ExecutionCommand] = []

    def submit(self, command: ExecutionCommand) -> ExecutionCommandResult:
        self.submitted_commands.append(command)
        return ExecutionCommandResult(
            command_id=command.command_id,
            order_id=command.order_id,
            status=ExecutionCommandResultStatus.ACCEPTED_BY_ADAPTER,
            reason="mock adapter accepted command",
            adapter_order_ref=_adapter_order_ref(command.command_id),
            submitted_at=self._clock(),
            raw_payload=None,
        )


def _adapter_order_ref(command_id: str) -> str:
    return "mock_" + stable_json_sha256({"command_id": command_id})[:40]
