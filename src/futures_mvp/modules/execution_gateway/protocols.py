from typing import Protocol, runtime_checkable

from futures_mvp.domain.models import ExecutionCommand, ExecutionCommandResult


@runtime_checkable
class ExecutionAdapter(Protocol):
    def submit(self, command: ExecutionCommand) -> ExecutionCommandResult: ...
