from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum

from futures_mvp.domain.enums import ExecutionCommandResultStatus
from futures_mvp.domain.models import ExecutionCommand, ExecutionCommandResult, stable_json_sha256
from futures_mvp.modules.execution_gateway.canonical import canonical_execution_command_payload


class MockBrokerSubmitMode(StrEnum):
    ACCEPT = "ACCEPT"
    PRE_SEND_TIMEOUT = "PRE_SEND_TIMEOUT"
    POST_SEND_UNCERTAIN = "POST_SEND_UNCERTAIN"


class MockBrokerAdapter:
    """Deterministic broker adapter test double for the Stage N command boundary."""

    adapter_name = "mock_broker"

    def __init__(
        self,
        *,
        submit_modes: list[MockBrokerSubmitMode] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._submit_modes = list(submit_modes or [MockBrokerSubmitMode.ACCEPT])
        self._submit_index = 0
        self._clock = clock or (lambda: datetime.now(UTC))
        self.submitted_commands: list[ExecutionCommand] = []
        self._command_payloads: dict[str, dict[str, object]] = {}
        self._command_results: dict[str, ExecutionCommandResult] = {}

    def submit(self, command: ExecutionCommand) -> ExecutionCommandResult:
        canonical = canonical_execution_command_payload(command)
        existing_payload = self._command_payloads.get(command.command_id)
        if existing_payload is not None:
            if existing_payload != canonical:
                return ExecutionCommandResult(
                    command_id=command.command_id,
                    order_id=command.order_id,
                    status=ExecutionCommandResultStatus.CONFLICT,
                    reason="broker_command_canonical_conflict",
                    adapter_order_ref=_adapter_order_ref(command.command_id),
                    raw_payload=None,
                )
            existing = self._command_results[command.command_id]
            return existing.model_copy(
                update={
                    "status": ExecutionCommandResultStatus.DUPLICATE,
                    "reason": "duplicate",
                }
            )

        mode = self._next_submit_mode()
        self._command_payloads[command.command_id] = canonical
        self.submitted_commands.append(command)
        result = _result_for_mode(command, mode, self._clock())
        self._command_results[command.command_id] = result
        return result

    def _next_submit_mode(self) -> MockBrokerSubmitMode:
        mode = self._submit_modes[min(self._submit_index, len(self._submit_modes) - 1)]
        self._submit_index += 1
        return mode


def _result_for_mode(
    command: ExecutionCommand,
    mode: MockBrokerSubmitMode,
    submitted_at: datetime,
) -> ExecutionCommandResult:
    adapter_order_ref = _adapter_order_ref(command.command_id)
    if mode is MockBrokerSubmitMode.ACCEPT:
        return ExecutionCommandResult(
            command_id=command.command_id,
            order_id=command.order_id,
            status=ExecutionCommandResultStatus.ACCEPTED_BY_ADAPTER,
            reason="mock broker accepted command",
            adapter_order_ref=adapter_order_ref,
            submitted_at=submitted_at,
            raw_payload=None,
        )
    if mode is MockBrokerSubmitMode.PRE_SEND_TIMEOUT:
        return ExecutionCommandResult(
            command_id=command.command_id,
            order_id=command.order_id,
            status=ExecutionCommandResultStatus.ERROR,
            reason="pre_send_timeout",
            adapter_order_ref=None,
            submitted_at=None,
            raw_payload=None,
        )
    return ExecutionCommandResult(
        command_id=command.command_id,
        order_id=command.order_id,
        status=ExecutionCommandResultStatus.ERROR,
        reason="post_send_uncertain",
        adapter_order_ref=adapter_order_ref,
        submitted_at=submitted_at,
        raw_payload=None,
    )


def _adapter_order_ref(command_id: str) -> str:
    return "mock_broker_" + stable_json_sha256({"command_id": command_id})[:40]
